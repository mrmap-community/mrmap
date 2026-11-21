import os
import tempfile
from unittest.mock import patch

from accounts.models.users import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.db.models.query_utils import Q
from django.test import TestCase
from epsg_cache.registry import Registry
from lxml import etree
from MrMap.settings import BASE_DIR
from registry.models.security import (AllowedWebMapServiceOperation,
                                      WebMapServiceProxySetting)
from registry.models.service import Layer, WebMapService
from registry.ows_lib.wms.wms import WebMapServiceClient
from registry.proxy.wms_proxy import WebMapServiceProxy
from rest_framework import status
from rest_framework.test import APIClient

# what the mocked upstream answers, in the order it is asked
ANSWERS = []

# the requests the mocked upstream was asked to send
SENT_REQUESTS = []

XMLNS_GML = "http://www.opengis.net/gml"
XMLNS_WFS = "http://www.opengis.net/wfs"


class MockResponse:
    def __init__(self, content, content_type="text/xml"):
        self.status_code = status.HTTP_200_OK
        self.content = content
        self.reason = "OK"
        self.headers = {"content-type": content_type}
        self.url = ""
        self.content_type = content_type

    @property
    def text(self):
        return self.content.decode()


def answer_as_upstream(*args, **kwargs):
    """Answer as the remote WMS does, after recording the request it is sent."""
    SENT_REQUESTS.append(args[0])
    return ANSWERS.pop(0)


def xml_feature(identifier: str, east: float, north: float, srs: str) -> bytes:
    """One wfs:FeatureMember of the text/xml GetFeatureInfo answer."""
    feature = etree.Element(f"{{{XMLNS_WFS}}}FeatureMember")
    member = etree.SubElement(feature, f"{{{XMLNS_WFS}}}member")
    member.set("fid", identifier)
    bounded_by = etree.SubElement(
        member, f"{{{XMLNS_GML}}}boundedByOfPolygon")
    envelope = etree.SubElement(
        bounded_by, f"{{{XMLNS_GML}}}Envelope", srsName=srs)
    lower = etree.SubElement(envelope, f"{{{XMLNS_GML}}}lowerCorner")
    lower.text = f"{east} {north}"
    upper = etree.SubElement(envelope, f"{{{XMLNS_GML}}}upperCorner")
    upper.text = f"{east + 10} {north + 10}"
    return etree.tostring(feature)


def xml_response(*features: bytes) -> bytes:
    root = etree.Element(f"{{{XMLNS_WFS}}}FeatureCollection")
    for feature in features:
        root.append(etree.fromstring(feature))
    return etree.tostring(root)


def exception_report() -> MockResponse:
    """The ServiceExceptionsReport of a remote which refused the request."""
    return MockResponse(
        content=(
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<ogc:ServiceExceptionReport xmlns:ogc="http://www.opengis.net/ogc"'
            ' version="1.3.0">'
            '<ogc:ServiceException code="LayerNotDefined">no such layer</ogc:ServiceException>'
            '</ogc:ServiceExceptionReport>'
        ).encode(),
        content_type="application/xml")


# the koblenz polygons of the fixture, as projected coordinates: what the
# allowed area of a request in EPSG:25832 is compared against
KOBLENZ_1 = "SRID=25832;POLYGON ((393340 5574710, 405660 5574710, 405660 5581190, 393340 5581190, 393340 5574710))"
KOBLENZ_2 = "SRID=25832;POLYGON ((530130 5925390, 550130 5925390, 550130 5935390, 530130 5935390, 530130 5925390))"
# inside the first allowed area but outside the second
NORTH_INSIDE_1 = (395340, 5576710)
NORTH_INSIDE_2 = (532130, 5927390)


class WebMapServiceProxyFeatureInfoTest(TestCase):
    """The GetFeatureInfo promises of the security proxy (#1471)."""

    @classmethod
    def setUpClass(cls):
        # see WebMapServiceProxyTest: the fixtures are loaded before the test
        # transaction, cause the mapserver reads committed rows
        call_command("loaddata", "test_users.json", verbosity=0)
        call_command("loaddata", "test_keywords.json", verbosity=0)
        call_command("loaddata", "test_wms.json", verbosity=0)
        call_command(
            "loaddata", "test_allowed_wms_operation.json", verbosity=0)
        cls.wms = WebMapService.objects.get(
            pk="cd16cc1f-3abb-4625-bb96-fbe80dbe23e3")

        cap_file = open(
            f"{BASE_DIR}/tests/django/test_data/capabilities/wms/1.3.0.xml",
            mode="rb")
        cls.wms.xml_backup_file = SimpleUploadedFile(
            "capabilitites.xml", cap_file.read())
        cls.wms.save()

    @classmethod
    def tearDownClass(cls):
        User.objects.filter(~Q(username="mrmap")).delete()
        WebMapService.objects.all().delete()
        AllowedWebMapServiceOperation.objects.all().delete()

    def setUp(self):
        ANSWERS.clear()
        SENT_REQUESTS.clear()
        self.client = APIClient()
        self.wms_url = "/mrmap-proxy/wms/cd16cc1f-3abb-4625-bb96-fbe80dbe23e3"
        self.node1 = Layer.objects.get(
            identifier="node1", service=self.wms, parent__isnull=True)
        self.node11 = Layer.objects.get(
            identifier="node1.1", service=self.wms)
        self.node111 = Layer.objects.get(
            identifier="node1.1.1", service=self.wms)
        self.rule = AllowedWebMapServiceOperation.objects.create(
            description="#1471 rule",
            allowed_area=KOBLENZ_1)
        self.rule.operations.set([20, 21])
        self.rule.secured_service.set([self.wms])
        self.rule.secured_layers.set([self.node1, self.node11, self.node111])
        self.rule.allowed_groups.set([User.objects.get(username="User1").groups.first().pk])
        self.client.login(username="User1", password="User1")
        media_root = tempfile.TemporaryDirectory(prefix="mrmap-featureinfo-")
        self.addCleanup(media_root.cleanup)
        override = self.settings(MEDIA_ROOT=media_root.name)
        override.enable()
        self.addCleanup(override.disable)

    def tearDown(self):
        self.rule.delete()

    def feature_info_params(self, **overrides) -> dict:
        params = {
            "SERVICE": "WMS",
            "VERSION": "1.3.0",
            "REQUEST": "GetFeatureInfo",
            "LAYERS": "node1",
            "QUERY_LAYERS": "node1",
            "CRS": "EPSG:25832",
            "BBOX": "393340,5574710,405660,5581190",
            "WIDTH": "1563",
            "HEIGHT": "920",
            "FORMAT": "image/png",
            "STYLES": "",
            "INFO_FORMAT": "application/json",
            "I": "500",
            "J": "500",
        }
        params.update(overrides)
        return params

    def ask(self, mocked_send, **overrides):
        return self.client.get(
            self.wms_url, self.feature_info_params(**overrides))

    def query_layers_of(self, index: int) -> list:
        from urllib.parse import parse_qs, urlparse
        query = urlparse(SENT_REQUESTS[index].url).query
        return parse_qs(query).get("QUERY_LAYERS", [""])[0].split(",")

    def assertRefusedWithTheCodeOfTheRequest(self, response, code: str):
        self.assertEqual(status.HTTP_403_FORBIDDEN, response.status_code)
        self.assertXmlSchema(
            response.content,
            "registry.ows_lib.xml.schemas",
            "wmsExceptionReport130.xsd")
        tree = etree.fromstring(response.content)
        exception = tree.find(
            "{http://www.opengis.net/ogc}ServiceException")
        self.assertIsNotNone(exception)
        self.assertEqual(code, exception.get("code"))

    @patch.object(
        target=Registry, attribute="_fetch_coord_ref_system",
        side_effect=lambda *args, **kwargs: None)
    @patch.object(
        target=WebMapServiceClient, attribute="send_request",
        side_effect=answer_as_upstream)
    def test_a_layer_which_is_asked_by_name_but_not_allowed_refuses(
            self, mocked_send, mocked_registry):
        # the request asks node1 and node1.2. QUERY_LAYERS is only narrowed to
        # the permitted one when the permitted layers were asked by name -- if
        # a forbidden one was named too, the whole set was not permitted (#1471)
        self.rule.secured_layers.set([self.node1, self.node11])
        ANSWERS.append(exception_report())

        response = self.ask(mocked_send, **{"QUERY_LAYERS": "node1,node1.1"})

        self.assertEqual(0, len(SENT_REQUESTS), "upstream was asked anyway")
        self.assertRefusedWithTheCodeOfTheRequest(response, "LayerNotDefined")

    @patch.object(
        target=Registry, attribute="_fetch_coord_ref_system",
        side_effect=lambda *args, **kwargs: None)
    @patch.object(
        target=WebMapServiceClient, attribute="send_request",
        side_effect=answer_as_upstream)
    def test_query_layers_is_carried_over_from_the_layers_of_the_request(
            self, mocked_send, mocked_registry):
        # a standard client names the queried layers; the proxy must forward
        # them unchanged so upstream answers the layer it was told to query
        ANSWERS.append(xml_response(
            xml_feature("f1", *NORTH_INSIDE_1, srs="EPSG:25832")))

        response = self.ask(mocked_send)

        self.assertEqual(status.HTTP_200_OK, response.status_code)
        self.assertEqual(["node1"], self.query_layers_of(0))

    @patch.object(
        target=Registry, attribute="_fetch_coord_ref_system",
        side_effect=lambda *args, **kwargs: None)
    @patch.object(
        target=WebMapServiceClient, attribute="send_request",
        side_effect=answer_as_upstream)
    def test_query_layers_without_layers_refuses_instead_of_narrowing(
            self, mocked_send, mocked_registry):
        # without LAYERS there is no drawn subtree to compare the query against
        ANSWERS.append(exception_report())

        response = self.ask(mocked_send, **{"LAYERS": ""})

        self.assertEqual(0, len(SENT_REQUESTS))
        self.assertRefusedWithTheCodeOfTheRequest(response, "LayerNotDefined")

    @patch.object(
        target=Registry, attribute="_fetch_coord_ref_system",
        side_effect=lambda *args, **kwargs: None)
    @patch.object(
        target=WebMapServiceClient, attribute="send_request",
        side_effect=answer_as_upstream)
    def test_query_layers_are_allowed_through_a_permitted_parent(
            self, mocked_send, mocked_registry):
        # the caller names only the child it wants information about, and the
        # permission for it comes from the permitted parent in the same request
        ANSWERS.append(xml_response(
            xml_feature("f1", *NORTH_INSIDE_1, srs="EPSG:25832")))

        response = self.ask(mocked_send, **{"QUERY_LAYERS": "node1.1.1"})

        self.assertEqual(status.HTTP_200_OK, response.status_code,
                         response.content)
        self.assertEqual(["node1.1.1"], self.query_layers_of(0))

    @patch.object(
        target=Registry, attribute="_fetch_coord_ref_system",
        side_effect=lambda *args, **kwargs: None)
    @patch.object(
        target=WebMapServiceClient, attribute="send_request",
        side_effect=answer_as_upstream)
    def test_a_query_layer_without_a_drawn_layer_is_not_permitted(
            self, mocked_send, mocked_registry):
        # the permission is inherited through the drawn layers: node1.2 is
        # secured but its parent is not asked for, so the proxy may not answer
        ANSWERS.append(exception_report())

        response = self.ask(
            mocked_send, **{"LAYERS": "node1", "QUERY_LAYERS": "node1.2"})

        self.assertEqual(0, len(SENT_REQUESTS))
        self.assertRefusedWithTheCodeOfTheRequest(response, "LayerNotDefined")

    @patch.object(
        target=Registry, attribute="_fetch_coord_ref_system",
        side_effect=lambda *args, **kwargs: None)
    @patch.object(
        target=WebMapServiceClient, attribute="send_request",
        side_effect=answer_as_upstream)
    def test_a_layer_secured_for_another_rule_is_only_permitted_by_its_rule(
            self, mocked_send, mocked_registry):
        # two rules, one with node1 in a different area: a request for both
        # areas narrows the query to what the union of the areas covers
        node12 = Layer.objects.get(identifier="node1.2", service=self.wms)
        other = AllowedWebMapServiceOperation.objects.create(
            description="#1471 other rule", allowed_area=KOBLENZ_2)
        self.addCleanup(other.delete)
        other.operations.set([20, 21])
        other.secured_service.set([self.wms])
        other.secured_layers.set([node12])
        other.allowed_groups.set(
            [User.objects.get(username="User1").groups.first().pk])
        ANSWERS.append(xml_response(
            xml_feature("f1", *NORTH_INSIDE_1, srs="EPSG:25832")))

        response = self.ask(
            mocked_send,
            **{"LAYERS": "node1,node1.2", "QUERY_LAYERS": "node1,node1.2"})

        self.assertEqual(status.HTTP_200_OK, response.status_code,
                         response.content)
        self.assertEqual(["node1", "node1.2"], self.query_layers_of(0))

    @patch.object(
        target=Registry, attribute="_fetch_coord_ref_system",
        side_effect=lambda *args, **kwargs: None)
    @patch.object(
        target=WebMapServiceClient, attribute="send_request",
        side_effect=answer_as_upstream)
    def test_a_request_which_covers_the_area_answers_the_requested_format(
            self, mocked_send, mocked_registry):
        # the bbox is within the allowed area, so everything upstream may
        # answer there is publishable: no extra xml check is paid for
        geojson = b'{"type": "FeatureCollection", "features": []}'
        ANSWERS.append(MockResponse(geojson, content_type="application/json"))

        response = self.ask(mocked_send)

        self.assertEqual(status.HTTP_200_OK, response.status_code)
        self.assertEqual(geojson, response.content)
        self.assertEqual(1, len(SENT_REQUESTS))
        from urllib.parse import parse_qs, urlparse
        params = parse_qs(urlparse(SENT_REQUESTS[0].url).query)
        self.assertEqual(["application/json"], params["INFO_FORMAT"])

    @patch.object(
        target=Registry, attribute="_fetch_coord_ref_system",
        side_effect=lambda *args, **kwargs: None)
    @patch.object(
        target=WebMapServiceClient, attribute="send_request",
        side_effect=answer_as_upstream)
    def test_a_second_feature_outside_the_area_keeps_the_answer_private(
            self, mocked_send, mocked_registry):
        # the bounding box of the FIRST feature passed the check of the
        # previous implementation and the whole answer went out with it (#1471)
        ANSWERS.append(xml_response(
            xml_feature("f1", *NORTH_INSIDE_1, srs="EPSG:25832"),
            xml_feature("f2", *NORTH_INSIDE_2, srs="EPSG:25832")))
        ANSWERS.append(exception_report())

        response = self.ask(mocked_send)

        self.assertRefusedWithTheCodeOfTheRequest(response, "LayerNotDefined")
        self.assertNotIn(b"f2", response.content)

    @patch.object(
        target=Registry, attribute="_fetch_coord_ref_system",
        side_effect=lambda *args, **kwargs: None)
    @patch.object(
        target=WebMapServiceClient, attribute="send_request",
        side_effect=answer_as_upstream)
    def test_all_features_within_the_area_are_answered_in_the_requested_format(
            self, mocked_send, mocked_registry):
        ANSWERS.append(xml_response(
            xml_feature("f1", *NORTH_INSIDE_1, srs="EPSG:25832"),
            xml_feature("f2", 395400, 5576800, srs="EPSG:25832")))
        ANSWERS.append(MockResponse(
            b'{"type": "FeatureCollection", "features": []}',
            content_type="application/json"))

        response = self.ask(mocked_send)

        self.assertEqual(status.HTTP_200_OK, response.status_code)
        self.assertEqual(2, len(SENT_REQUESTS))
        from urllib.parse import parse_qs, urlparse
        self.assertEqual(
            ["text/xml"],
            parse_qs(urlparse(SENT_REQUESTS[0].url).query)["INFO_FORMAT"])
        self.assertEqual(
            ["application/json"],
            parse_qs(urlparse(SENT_REQUESTS[1].url).query)["INFO_FORMAT"])

    @patch.object(
        target=Registry, attribute="_fetch_coord_ref_system",
        side_effect=lambda *args, **kwargs: None)
    @patch.object(
        target=WebMapServiceClient, attribute="send_request",
        side_effect=answer_as_upstream)
    def test_an_unparseable_answer_does_not_authorize_itself(
            self, mocked_send, mocked_registry):
        ANSWERS.append(MockResponse(b"this is not a GetFeatureInfo document"))
        ANSWERS.append(exception_report())

        response = self.ask(mocked_send)

        self.assertRefusedWithTheCodeOfTheRequest(response, "LayerNotDefined")

    @patch.object(
        target=Registry, attribute="_fetch_coord_ref_system",
        side_effect=lambda *args, **kwargs: None)
    @patch.object(
        target=WebMapServiceClient, attribute="send_request",
        side_effect=answer_as_upstream)
    def test_a_remote_exception_report_is_forwarded_not_answered_as_info(
            self, mocked_send, mocked_registry):
        ANSWERS.append(exception_report())
        ANSWERS.append(exception_report())

        response = self.ask(mocked_send)

        self.assertRefusedWithTheCodeOfTheRequest(response, "LayerNotDefined")

    @patch.object(
        target=Registry, attribute="_fetch_coord_ref_system",
        side_effect=lambda *args, **kwargs: None)
    @patch.object(
        target=WebMapServiceClient, attribute="send_request",
        side_effect=answer_as_upstream)
    def test_a_feature_without_a_geometry_keeps_the_answer_private(
            self, mocked_send, mocked_registry):
        member = etree.Element(f"{{{XMLNS_WFS}}}FeatureMember")
        etree.SubElement(member, "name").text = "no geometry here"
        ANSWERS.append(xml_response(etree.tostring(member)))
        ANSWERS.append(exception_report())

        response = self.ask(mocked_send)

        self.assertRefusedWithTheCodeOfTheRequest(response, "LayerNotDefined")

    @patch.object(
        target=Registry, attribute="_fetch_coord_ref_system",
        side_effect=lambda *args, **kwargs: None)
    @patch.object(
        target=WebMapServiceClient, attribute="send_request",
        side_effect=answer_as_upstream)
    def test_a_feature_in_another_crs_is_not_assumed_to_be_the_area_of_the_request(
            self, mocked_send, mocked_registry):
        # a degree-bounded feature is not comparable with a metric request, so
        # the answer of that request stays private instead of being published
        ANSWERS.append(xml_response(
            xml_feature("f1", 7.59, 50.36, srs="EPSG:4326")))
        ANSWERS.append(exception_report())

        response = self.ask(mocked_send)

        self.assertRefusedWithTheCodeOfTheRequest(response, "LayerNotDefined")

    @patch.object(
        target=Registry, attribute="_fetch_coord_ref_system",
        side_effect=lambda *args, **kwargs: None)
    @patch.object(
        target=WebMapServiceClient, attribute="send_request",
        side_effect=answer_as_upstream)
    def test_a_logged_feature_info_response_never_carries_the_callers_credentials(
            self, mocked_send, mocked_registry):
        WebMapServiceProxySetting.objects.create(
            secured_service=self.wms, camouflage=True, log_response=True)
        ANSWERS.append(xml_response(
            xml_feature("f1", *NORTH_INSIDE_1, srs="EPSG:25832")))
        ANSWERS.append(MockResponse(
            b'{"type": "FeatureCollection", "features": []}',
            content_type="application/json"))

        response = self.client.get(
            self.wms_url,
            self.feature_info_params(**{"SECRET_TOKEN": "a-secret-of-the-caller"}))

        self.assertEqual(status.HTTP_200_OK, response.status_code)
        from registry.models.security import WebMapServiceHttpResponseLog
        rows = list(WebMapServiceHttpResponseLog.objects.all())
        self.assertTrue(rows, "the logged exchange was not written")
        for row in rows:
            dumped = vars(row)
            self.assertNotIn("a-secret-of-the-caller", str(dumped))
