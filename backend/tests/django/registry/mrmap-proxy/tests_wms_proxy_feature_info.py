"""The GetFeatureInfo promises of the security proxy (#1471).

The operation is answered by the proxy in the name of the caller, so two things
have to hold before an answer travels: the caller has to be entitled to every
layer the answer is about -- which is what ``QUERY_LAYERS`` names, not what
``LAYERS`` drew -- and no feature of the answer may lie outside the area the
caller is allowed to see. Both were decided by the drawn layers and by the first
feature of the answer alone.
"""
from datetime import timedelta
from urllib.parse import parse_qs, urlparse
from unittest.mock import patch

from accounts.models.users import User
from django.contrib.gis.geos import GEOSGeometry
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.db.models.query_utils import Q
from django.test import TestCase
from lxml import etree
from MrMap.settings import BASE_DIR
from registry.models.security import AllowedWebMapServiceOperation
from registry.models.service import Layer, WebMapService
from registry.ows_lib.wms.wms import WebMapServiceClient
from registry.proxy.wms_proxy import WebMapServiceProxy
from rest_framework import status
from rest_framework.test import APIClient

WFS_NS = "http://www.opengis.net/wfs"
GML_NS = "http://www.opengis.net/gml"
# the spelling the WFS 2.0 / GML 3.2 readers of this repository use
# (registry/ows_lib/wfs/gml.py); an answer of a service may carry its areas in
# either of them, or in none of them at all
GML_3_2_NS = "http://www.opengis.net/gml/3.2"
OGC_NS = "http://www.opengis.net/ogc"
OWS_NS = "http://www.opengis.net/ows/1.1"

# the upstream answers, in the order the proxy asks them, and the requests it
# was asked to send
ANSWERS = []
SENT_REQUESTS = []

# The Koblenz area of the secured rules and the extent of a request which is
# covered by it. WMS 1.3.0 reads the values of a geographic bbox in the axis
# order of the CRS -- latitude, longitude (OGC 05-008, 6.7.3.3).
KOBLENZ = ("SRID=4326;MULTIPOLYGON (((7.57 50.35, 7.61 50.35, 7.61 50.39, "
           "7.57 50.39, 7.57 50.35)))")
COVERED_BBOX = "50.35,7.57,50.39,7.61"
# the request of the wider extent is not covered, so its answer is decided
# feature by feature
WIDER_BBOX = "50.30,7.50,50.40,7.70"
# the corner of a feature envelope, once within the area and once outside it
INSIDE = (7.58, 50.36)
OUTSIDE = (8.58, 51.36)


class MockResponse:
    """The answer of the remote service, as ``requests`` reports it."""

    def __init__(self, content, content_type="text/xml", status_code=200):
        self.status_code = status_code
        self.content = content
        self.reason = "OK"
        self.elapsed = timedelta(seconds=1)
        self.headers = {"content-type": content_type}
        self.url = "http://remote.example/wms"

    @property
    def text(self):
        return self.content.decode()


def answer_as_upstream(*args, **kwargs):
    """Answer as the remote WMS does, after recording the request it is sent."""
    SENT_REQUESTS.append(args[0])
    return ANSWERS.pop(0)


def feature(identifier: str, north: float, east: float,
            srs: str = "EPSG:4326", gml_ns: str = GML_NS,
            name: str = None) -> bytes:
    """One member of the text/xml answer, bounded by an envelope at the corner.

    ``gml_ns`` spells the GML namespace of the areas the way the answering
    service does, and ``name`` adds a value of a feature the service chose --
    an answer does not become a report by mentioning one.
    """
    member = etree.Element(f"{{{WFS_NS}}}member", fid=identifier)
    bounded_by = etree.SubElement(member, f"{{{gml_ns}}}boundedBy")
    envelope = etree.SubElement(
        bounded_by, f"{{{gml_ns}}}Envelope", srsName=srs)
    etree.SubElement(
        envelope, f"{{{gml_ns}}}lowerCorner").text = f"{north} {east}"
    etree.SubElement(
        envelope, f"{{{gml_ns}}}upperCorner").text = f"{north + 0.001} {east + 0.001}"
    if name is not None:
        etree.SubElement(member, f"{{{WFS_NS}}}name").text = name
    return etree.tostring(member)


def answer(*members: bytes) -> MockResponse:
    """The text/xml answer of a GetFeatureInfo, carrying the given members."""
    root = etree.Element(f"{{{WFS_NS}}}FeatureCollection")
    for member in members:
        root.append(etree.fromstring(member))
    return MockResponse(etree.tostring(root))


def exception_report() -> MockResponse:
    """The ServiceExceptionReport of a remote which refused the request."""
    return MockResponse(
        content=(
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<ServiceExceptionReport version="1.3.0"'
            ' xmlns="http://www.opengis.net/ogc">'
            '<ServiceException code="LayerNotDefined">no such layer</ServiceException>'
            '</ServiceExceptionReport>'
        ).encode(),
        content_type="application/xml",
        status_code=status.HTTP_400_BAD_REQUEST)


def geojson_answer() -> MockResponse:
    return MockResponse(
        b'{"type": "FeatureCollection", "features": []}',
        content_type="application/json")


def ows_exception_report() -> MockResponse:
    """The OWS Common ExceptionReport a service of the OWS shape refuses with."""
    return MockResponse(
        content=(
            '<?xml version="1.0" encoding="UTF-8"?>'
            f'<ows:ExceptionReport version="1.2.1" xmlns:ows="{OWS_NS}">'
            '<ows:Exception exceptionCode="OperationNotSupported">'
            '<ows:ExceptionText>no such operation</ows:ExceptionText>'
            '</ows:Exception></ows:ExceptionReport>'
        ).encode(),
        content_type="text/xml",
        status_code=status.HTTP_400_BAD_REQUEST)


def upstream_param(index: int, name: str) -> list:
    """The values of one parameter of the ``index``-th request sent upstream."""
    return parse_qs(urlparse(SENT_REQUESTS[index].url).query).get(name, [])


class WebMapServiceProxyFeatureInfoTest(TestCase):
    """The GetFeatureInfo promises of the security proxy (#1471)."""

    @classmethod
    def setUpClass(cls):
        # see WebMapServiceProxyTest: the fixtures are loaded before the test
        # transaction, cause the mapserver reads committed rows
        call_command("loaddata", "test_users.json", verbosity=0)
        call_command("loaddata", "test_keywords.json", verbosity=0)
        call_command("loaddata", "test_wms.json", verbosity=0)
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
        # Custom clean up... see setUpClass method above for explanations
        User.objects.filter(~Q(username="mrmap")).delete()
        WebMapService.objects.all().delete()
        AllowedWebMapServiceOperation.objects.all().delete()

    def setUp(self):
        ANSWERS.clear()
        SENT_REQUESTS.clear()
        self.client = APIClient()
        self.wms_url = "/mrmap-proxy/wms/cd16cc1f-3abb-4625-bb96-fbe80dbe23e3"
        self.layers = {
            layer.identifier: layer
            for layer in Layer.objects.filter(service=self.wms)}
        self.group1 = User.objects.get(
            username="User1").groups.get(name="Group1")
        self.group2 = User.objects.get(
            username="User2").groups.get(name="Group2")
        # two rules of two groups over one service: the caller of the first may
        # ask the subtree of node1.1, the caller of the second the subtree of
        # node1.3 -- which of them decides has to be seen by the queried layers
        self.rule = self.secured_rule(
            "group1 rule", self.group1,
            ["node1.1", "node1.1.1", "node1.1.2", "node1.1.3"])
        self.other_rule = self.secured_rule(
            "group2 rule", self.group2, ["node1.3", "node1.3.1"])
        self.client.login(username="User1", password="User1")

    def tearDown(self):
        AllowedWebMapServiceOperation.objects.all().delete()

    def secured_rule(self, description, group, identifiers):
        """A GetMap and GetFeatureInfo rule of one group over some layers."""
        rule = AllowedWebMapServiceOperation.objects.create(
            description=description,
            allowed_area=GEOSGeometry(KOBLENZ),
            secured_service=self.wms)
        rule.operations.set([20, 21])
        rule.secured_layers.set(
            [self.layers[identifier] for identifier in identifiers])
        rule.allowed_groups.set([group.pk])
        return rule

    def feature_info_params(self, **overrides) -> dict:
        params = {
            "SERVICE": "WMS",
            "VERSION": "1.3.0",
            "REQUEST": "GetFeatureInfo",
            "LAYERS": "node1.1",
            "QUERY_LAYERS": "node1.1",
            "CRS": "EPSG:4326",
            # wider than the allowed area, so the answer is decided feature by
            # feature instead of by the extent of the request
            "BBOX": WIDER_BBOX,
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

    def ask(self, **overrides):
        """Ask a GetFeatureInfo of the proxy, with the parameters overridden."""
        return self.client.get(self.wms_url, self.feature_info_params(**overrides))

    def assertRefused(self, response):
        """The proxy refused the request with its own permissions report.

        The security proxy answers the refusal of a WMS with the
        ``ServiceExceptionReport`` of the service, which carries its refusal in
        the code of the report; see the report promise of
        :class:`registry.ows_lib.response.exceptions.OGCServiceException`.
        """
        tree = etree.fromstring(response.content)
        exception = tree.find(f".//{{{OGC_NS}}}ServiceException")
        self.assertIsNotNone(
            exception, f"no refusal report: {response.content[:500]!r}")
        self.assertEqual("Forbidden", exception.get("code"))

    @patch.object(
        target=WebMapServiceClient, attribute="send_request",
        side_effect=answer_as_upstream)
    def test_a_queried_layer_the_caller_may_not_request_is_never_asked(
            self, mocked_send):
        # node1.3 is secured for the other group only: the drawn layers of the
        # request carry no permission for it and upstream is asked nothing at
        # all (#1471)
        response = self.ask(**{"QUERY_LAYERS": "node1.3"})

        self.assertRefused(response)
        self.assertEqual(0, len(SENT_REQUESTS))

    @patch.object(
        target=WebMapServiceClient, attribute="send_request",
        side_effect=answer_as_upstream)
    def test_one_queried_layer_outside_the_permission_refuses_the_whole_request(
            self, mocked_send):
        # the answer of a request carries the features of all queried layers, so
        # the caller has to be entitled to each of them; the permitted one does
        # not carry the answer of the other (#1471)
        response = self.ask(**{"QUERY_LAYERS": "node1.1,node1.3"})

        self.assertRefused(response)
        self.assertEqual(0, len(SENT_REQUESTS))

    @patch.object(
        target=WebMapServiceClient, attribute="send_request",
        side_effect=answer_as_upstream)
    def test_a_queried_layer_of_the_permitted_subtree_is_asked(self, mocked_send):
        # the caller names the child it wants the information of; it is permitted
        # by the rule which secures that subtree, whatever the request drew
        ANSWERS.append(answer(feature("f1", *INSIDE)))
        ANSWERS.append(geojson_answer())

        response = self.ask(**{"LAYERS": "node1.1", "QUERY_LAYERS": "node1.1.1"})

        self.assertEqual(status.HTTP_200_OK, response.status_code, response.content)
        self.assertEqual(["node1.1.1"], upstream_param(0, "QUERY_LAYERS"))

    @patch.object(
        target=WebMapServiceClient, attribute="send_request",
        side_effect=answer_as_upstream)
    def test_queried_layers_without_drawn_layers_are_answered_for_an_entitled_caller(
            self, mocked_send):
        # a caller which names no drawn layer is not entitled to everything, but
        # neither is it refused out of hand: its entitlement is decided by the
        # layers it does name (#1471)
        ANSWERS.append(answer(feature("f1", *INSIDE)))
        ANSWERS.append(geojson_answer())

        response = self.ask(**{"LAYERS": ""})

        self.assertEqual(status.HTTP_200_OK, response.status_code, response.content)
        self.assertEqual(["node1.1"], upstream_param(0, "QUERY_LAYERS"))

    @patch.object(
        target=WebMapServiceClient, attribute="send_request",
        side_effect=answer_as_upstream)
    def test_a_request_naming_no_layer_at_all_is_refused(self, mocked_send):
        # neither a drawn nor a queried layer is named, so there is nothing the
        # caller could be entitled to and nothing to answer about
        response = self.ask(**{"LAYERS": "", "QUERY_LAYERS": ""})

        self.assertRefused(response)
        self.assertEqual(0, len(SENT_REQUESTS))

    @patch.object(
        target=WebMapServiceClient, attribute="send_request",
        side_effect=answer_as_upstream)
    def test_a_covered_extent_answers_the_requested_format_at_once(self, mocked_send):
        # whatever upstream answers within an allowed extent is publishable, so
        # the answer is asked once and forwarded as it is
        ANSWERS.append(MockResponse(
            b'{"type": "FeatureCollection", "features": []}',
            content_type="application/json"))

        response = self.ask(**{"BBOX": COVERED_BBOX})

        self.assertEqual(status.HTTP_200_OK, response.status_code,
                         response.content[:500])
        self.assertEqual(1, len(SENT_REQUESTS))
        self.assertEqual(["application/json"], upstream_param(0, "INFO_FORMAT"))

    @patch.object(
        target=WebMapServiceClient, attribute="send_request",
        side_effect=answer_as_upstream)
    def test_a_second_feature_outside_the_area_keeps_the_whole_answer_private(
            self, mocked_send):
        # the bounding box of the FIRST feature passed the check of the previous
        # implementation and the whole answer went out with it (#1471)
        ANSWERS.append(answer(
            feature("f1", *INSIDE),
            feature("f2", *OUTSIDE)))
        ANSWERS.append(MockResponse(
            b'{"type": "FeatureCollection", "features": [{"fid": "f2"}]}',
            content_type="application/json"))

        response = self.ask()

        self.assertRefused(response)
        self.assertNotIn(b"f2", response.content)

    @patch.object(
        target=WebMapServiceClient, attribute="send_request",
        side_effect=answer_as_upstream)
    def test_a_first_feature_outside_the_area_keeps_the_whole_answer_private(
            self, mocked_send):
        # no feature of the answer may lie outside the allowed area, whichever
        # position it has in the document (#1471)
        ANSWERS.append(answer(
            feature("f1", *OUTSIDE),
            feature("f2", *INSIDE)))
        ANSWERS.append(geojson_answer())

        response = self.ask()

        self.assertRefused(response)

    @patch.object(
        target=WebMapServiceClient, attribute="send_request",
        side_effect=answer_as_upstream)
    def test_all_features_within_the_area_are_answered_in_the_requested_format(
            self, mocked_send):
        # the features can only be read out of an answer of text/xml, so that
        # one is asked for the check and the answer of the caller is forwarded
        # unchanged afterwards
        ANSWERS.append(answer(
            feature("f1", *INSIDE),
            feature("f2", 50.361, 7.581)))
        ANSWERS.append(geojson_answer())

        response = self.ask()

        self.assertEqual(status.HTTP_200_OK, response.status_code, response.content)
        self.assertEqual(2, len(SENT_REQUESTS))
        self.assertEqual(["text/xml"], upstream_param(0, "INFO_FORMAT"))
        self.assertEqual(["application/json"], upstream_param(1, "INFO_FORMAT"))
        self.assertEqual(
            ["node1.1"], upstream_param(0, "QUERY_LAYERS"),
            "the check must not change the request of the caller")

    @patch.object(
        target=WebMapServiceClient, attribute="send_request",
        side_effect=answer_as_upstream)
    def test_an_answer_in_the_requested_format_is_checked_itself(self, mocked_send):
        # a caller who asks text/xml gets the answer which was checked, without
        # paying for a second one
        ANSWERS.append(answer(feature("f1", *INSIDE)))

        response = self.ask(**{"INFO_FORMAT": "text/xml"})

        self.assertEqual(status.HTTP_200_OK, response.status_code, response.content)
        self.assertEqual(1, len(SENT_REQUESTS))
        self.assertEqual(["text/xml"], upstream_param(0, "INFO_FORMAT"))

    @patch.object(
        target=WebMapServiceClient, attribute="send_request",
        side_effect=answer_as_upstream)
    def test_an_answer_which_is_no_xml_keeps_the_answer_private(self, mocked_send):
        # a body which is no well-formed XML proves nothing about the features it
        # carries and is not answered because nothing can be read out of it
        ANSWERS.append(MockResponse(b"this is not a GetFeatureInfo document"))
        ANSWERS.append(geojson_answer())

        response = self.ask()

        self.assertRefused(response)

    @patch.object(
        target=WebMapServiceClient, attribute="send_request",
        side_effect=answer_as_upstream)
    def test_a_feature_without_an_area_keeps_the_answer_private(self, mocked_send):
        # an answer whose features carry no area can not be checked, and an
        # unchecked answer of a secured service is private
        ANSWERS.append(answer(
            ('<wfs:member xmlns:wfs="%s" fid="f1"><name>x</name></wfs:member>'
             % WFS_NS).encode()))
        ANSWERS.append(geojson_answer())

        response = self.ask()

        self.assertRefused(response)

    @patch.object(
        target=WebMapServiceClient, attribute="send_request",
        side_effect=answer_as_upstream)
    def test_an_answer_without_features_is_answered(self, mocked_send):
        # nothing private travels with an answer which carries no feature at all
        ANSWERS.append(answer())
        ANSWERS.append(geojson_answer())

        response = self.ask()

        self.assertEqual(status.HTTP_200_OK, response.status_code, response.content)

    @patch.object(
        target=WebMapServiceClient, attribute="send_request",
        side_effect=answer_as_upstream)
    def test_a_feature_of_a_foreign_area_is_not_assumed_to_be_within_the_allowed_area(
            self, mocked_send):
        # an area which is not comparable with the allowed area of the request
        # proves nothing, so the answer stays private instead of being published
        # on the strength of a number nobody compared
        ANSWERS.append(answer(feature("f1", 395340, 5576710, srs="EPSG:25832")))
        ANSWERS.append(geojson_answer())

        response = self.ask()

        self.assertRefused(response)

    @patch.object(
        target=WebMapServiceClient, attribute="send_request",
        side_effect=answer_as_upstream)
    def test_a_refusal_of_the_remote_service_is_forwarded_as_its_own(
            self, mocked_send):
        # the remote service refused the request of the caller; answering that
        # refusal as a permission problem of the proxy would tell the caller
        # about a permission which was never the cause
        ANSWERS.append(exception_report())
        ANSWERS.append(exception_report())

        response = self.ask()

        self.assertEqual(status.HTTP_400_BAD_REQUEST, response.status_code)
        self.assertIn(b"LayerNotDefined", response.content)

    @patch.object(
        target=WebMapServiceProxy, attribute="get_remote_response",
        side_effect=lambda *args, **kwargs: {
            "status_code": status.HTTP_502_BAD_GATEWAY,
            "code": "MaxRetriesExceeded",
            "content": "can't reach remote service.",
        })
    def test_a_remote_service_which_never_answers_is_not_answered_as_a_permission(
            self, mocked_answer):
        # an upstream which is unreachable is a failure of the proxy, not a
        # refusal of the permissions of the caller (#1153, #1471)
        response = self.ask()

        self.assertEqual(status.HTTP_502_BAD_GATEWAY, response.status_code)
        self.assertIn(b"reach remote service", response.content)

    @patch.object(
        target=WebMapServiceClient, attribute="send_request",
        side_effect=answer_as_upstream)
    def test_a_feature_of_an_answer_written_in_gml_3_2_is_checked(self, mocked_send):
        # the areas of an answer are read namespace-agnostically, so a service
        # which spells its GML the way the WFS 2.0 readers of this repository do
        # is compared like any other: an answer of the GML 3.2 spelling whose
        # features all lie within the allowed area is answered (#1471)
        ANSWERS.append(answer(
            feature("f1", *INSIDE, gml_ns=GML_3_2_NS),
            feature("f2", *INSIDE, gml_ns=GML_3_2_NS)))
        ANSWERS.append(geojson_answer())

        response = self.ask()

        self.assertEqual(status.HTTP_200_OK, response.status_code, response.content)

    @patch.object(
        target=WebMapServiceClient, attribute="send_request",
        side_effect=answer_as_upstream)
    def test_a_feature_outside_the_allowed_area_of_a_gml_3_2_answer_refuses_it(
            self, mocked_send):
        # the presence of an area was proved namespace-agnostically while the
        # area itself was read in one bound namespace: a GML 3.2 answer selected
        # no area at all, all() of nothing is true and the answer travelled
        # although no feature was ever compared (#1471)
        ANSWERS.append(answer(
            feature("f1", *INSIDE, gml_ns=GML_3_2_NS),
            feature("f2", *OUTSIDE, gml_ns=GML_3_2_NS)))
        ANSWERS.append(geojson_answer())

        response = self.ask()

        self.assertRefused(response)

    @patch.object(
        target=WebMapServiceClient, attribute="send_request",
        side_effect=answer_as_upstream)
    def test_a_feature_of_an_answer_of_a_foreign_gml_namespace_is_compared(
            self, mocked_send):
        # the areas are read by their local name, whatever namespace the
        # answering service spells them in: an answer of a namespace no reader
        # of this deployment names is compared like any other, and its feature
        # outside the allowed area keeps the answer private (#1471)
        ANSWERS.append(answer(
            feature("f1", *INSIDE, gml_ns="http://example.com/gml"),
            feature("f2", *OUTSIDE, gml_ns="http://example.com/gml")))
        ANSWERS.append(geojson_answer())

        response = self.ask()

        self.assertRefused(response)

    @patch.object(
        target=WebMapServiceClient, attribute="send_request",
        side_effect=answer_as_upstream)
    def test_an_area_nested_below_the_member_is_compared_too(self, mocked_send):
        # an answer is read by the local names of its areas, whatever element
        # carries them: a service which wraps its envelope one level deeper is
        # compared like the flat answer of the other tests (#1471)
        outside = etree.fromstring(feature("f1", *OUTSIDE))
        envelope = outside.find(f".//{{{GML_NS}}}boundedBy")
        wrapper = etree.Element(f"{{{WFS_NS}}}shape")
        envelope.addprevious(wrapper)
        wrapper.append(envelope)
        ANSWERS.append(answer(etree.tostring(outside)))
        ANSWERS.append(geojson_answer())

        response = self.ask()

        self.assertRefused(response)

    @patch.object(
        target=WebMapServiceClient, attribute="send_request",
        side_effect=answer_as_upstream)
    def test_an_answer_naming_a_refusal_is_still_checked_feature_by_feature(
            self, mocked_send):
        # whether an answer is the report of a refusal is decided by its root,
        # not by a word of its serialisation: upstream writes the attributes of
        # a feature, so an answer which mentions a report is no report and the
        # feature outside the allowed area keeps it private (#1471)
        ANSWERS.append(answer(feature(
            "f1", *OUTSIDE, name="ServiceExceptionReport")))
        ANSWERS.append(geojson_answer())

        response = self.ask()

        self.assertRefused(response)

    @patch.object(
        target=WebMapServiceClient, attribute="send_request",
        side_effect=answer_as_upstream)
    def test_an_ows_exception_report_of_the_remote_is_forwarded_as_its_own(
            self, mocked_send):
        # a service of the OWS shape refuses with an ExceptionReport, not with
        # the ServiceExceptionReport of the WMS; both are the refusal of the
        # remote and travel as their own
        ANSWERS.append(ows_exception_report())
        ANSWERS.append(ows_exception_report())

        response = self.ask()

        self.assertEqual(status.HTTP_400_BAD_REQUEST, response.status_code)
        self.assertIn(b"OperationNotSupported", response.content)
