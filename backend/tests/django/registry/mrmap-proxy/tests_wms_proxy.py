import tempfile
from datetime import timedelta
from importlib import resources
from io import BytesIO
from pathlib import Path
from urllib.parse import parse_qsl, urlparse
from unittest.mock import patch

from accounts.models.users import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.db.models.query_utils import Q
from django.test import SimpleTestCase, TestCase
from epsg_cache.models import Origin, SpatialReference
from epsg_cache.registry import Registry
from lxml import etree
from MrMap.settings import BASE_DIR
from PIL import Image, ImageChops
from registry.models.security import (
    AllowedWebMapServiceOperation, WebFeatureServiceHttpRequestLog,
    WebMapServiceHttpRequestLog, WebMapServiceProxySetting)
from registry.models.service import WebMapService
from registry.ows_lib.request.ogc_request import OGCRequest
from registry.ows_lib.wms.wms import WebMapServiceClient
from registry.proxy.wms_proxy import WebMapServiceProxy
from rest_framework import status
from rest_framework.test import APIClient


class MockResponse:
    def __init__(self, status_code, content, content_type, url=""):
        self.status_code = status_code

        if isinstance(content, Path):
            with open(content, "rb") as in_file:
                self.content = in_file.read()

        if isinstance(content, bytes):
            self.content = content

        self.reason = "OK"
        # what requests reports for a response: the time it waited, as a timedelta
        self.elapsed = timedelta(seconds=1)
        self.headers = {"content-type": content_type}
        self.url = url
        self.content_type = content_type


EPSG_API_25832_RESPONSE = SpatialReference(
    origin=Origin.EPSG_REGISTRY,
    srs_input='PROJCRS["ETRS89 / UTM zone 32N",BASEGEOGCRS["ETRS89",ENSEMBLE["European Terrestrial Reference System 1989 ensemble", MEMBER["European Terrestrial Reference Frame 1989", ID["EPSG",1178]], MEMBER["European Terrestrial Reference Frame 1990", ID["EPSG",1179]], MEMBER["European Terrestrial Reference Frame 1991", ID["EPSG",1180]], MEMBER["European Terrestrial Reference Frame 1992", ID["EPSG",1181]], MEMBER["European Terrestrial Reference Frame 1993", ID["EPSG",1182]], MEMBER["European Terrestrial Reference Frame 1994", ID["EPSG",1183]], MEMBER["European Terrestrial Reference Frame 1996", ID["EPSG",1184]], MEMBER["European Terrestrial Reference Frame 1997", ID["EPSG",1185]], MEMBER["European Terrestrial Reference Frame 2000", ID["EPSG",1186]], MEMBER["European Terrestrial Reference Frame 2005", ID["EPSG",1204]], MEMBER["European Terrestrial Reference Frame 2014", ID["EPSG",1206]], ELLIPSOID["GRS 1980",6378137,298.257222101,LENGTHUNIT["metre",1,ID["EPSG",9001]],ID["EPSG",7019]], ENSEMBLEACCURACY[0.1],ID["EPSG",6258]],ID["EPSG",4258]],CONVERSION["UTM zone 32N",METHOD["Transverse Mercator",ID["EPSG",9807]],PARAMETER["Latitude of natural origin",0,ANGLEUNIT["degree",0.0174532925199433,ID["EPSG",9102]]],PARAMETER["Longitude of natural origin",9,ANGLEUNIT["degree",0.0174532925199433,ID["EPSG",9102]]],PARAMETER["Scale factor at natural origin",0.9996,SCALEUNIT["unity",1,ID["EPSG",9201]]],PARAMETER["False easting",500000,LENGTHUNIT["metre",1,ID["EPSG",9001]]],PARAMETER["False northing",0,LENGTHUNIT["metre",1,ID["EPSG",9001]]],ID["EPSG",16032]],CS[Cartesian,2,ID["EPSG",4400]],AXIS["Easting (E)",east],AXIS["Northing (N)",north],LENGTHUNIT["metre",1,ID["EPSG",9001]],ID["EPSG",25832]]'.encode(
    ),
    srs_type="wkt",
)

REMOTE_RESPONSE = MockResponse(
    status_code=status.HTTP_200_OK,
    content=Path(
        Path.joinpath(
            Path(__file__).parent.resolve(), "../../test_data/karte_rp.fcgi.png"
        )
    ),
    content_type="image/png",
)


def epsg_side_effect(*args, **kwargs):
    return EPSG_API_25832_RESPONSE


def remote_effect(*args, **kwargs):
    return REMOTE_RESPONSE


# the upstream requests the patched client below was asked to send
FORWARDED_REQUESTS = []


def capture_remote_request(*args, **kwargs):
    """Answer as the remote WMS does, after recording the request it is sent."""
    FORWARDED_REQUESTS.append(args[0])
    return REMOTE_RESPONSE


class WebMapServiceProxyTest(TestCase):

    @classmethod
    def setUpClass(cls):
        # we can't setup test data in db inside the normal test setup routines, cause django wraps it with a transaction...
        # Cause this is a system test which depends on other system (mapserver) the test_db setup must be done before the normal transaction routine.
        # Otherwise the objects are not present in the database if the mapserver instance is connecting.
        call_command("loaddata", "test_users.json", verbosity=0)
        call_command("loaddata", "test_keywords.json", verbosity=0)
        call_command("loaddata", "test_wms.json", verbosity=0)
        call_command(
            "loaddata", "test_allowed_wms_operation.json", verbosity=0)
        wms: WebMapService = WebMapService.objects.get(
            pk="cd16cc1f-3abb-4625-bb96-fbe80dbe23e3")

        cap_file = open(
            f"{BASE_DIR}/tests/django/test_data/capabilities/wms/1.3.0.xml", mode="rb")

        wms.xml_backup_file = SimpleUploadedFile(
            'capabilitites.xml', cap_file.read())
        wms.save()

    @classmethod
    def tearDownClass(cls):
        # Custom clean up... see setUpClass method above for explanations
        User.objects.filter(~Q(username='mrmap')).delete()
        WebMapService.objects.all().delete()
        AllowedWebMapServiceOperation.objects.all().delete()

    def setUp(self):
        self.client = APIClient()
        self.wms_url = "/mrmap-proxy/wms/cd16cc1f-3abb-4625-bb96-fbe80dbe23e3"
        self.query_params = {
            "VERSION": "1.3.0",
            "REQUEST": "GetMap",
            "SERVICE": "WMS",
            "STYLES": "",
            "CRS": "EPSG:25832",
            "BBOX": "393340,5574710,405660,5581190",
            "WIDTH": "1563",
            "HEIGHT": "920",
            "FORMAT": "image/png",
            "BGCOLOR": "0xffffff",
            "TRANSPARENT": "TRUE"
        }

    def are_images_equal(self, img1, img2):
        equal_size = img1.height == img2.height and img1.width == img2.width

        if img1.mode == img2.mode == "RGBA":
            img1_alphas = [pixel[3] for pixel in img1.getdata()]
            img2_alphas = [pixel[3] for pixel in img2.getdata()]
            equal_alphas = img1_alphas == img2_alphas
        else:
            equal_alphas = True

        diff = ImageChops.difference(
            img1.convert("RGB"), img2.convert("RGB")
        )

        equal_content = not diff.getbbox()

        return equal_size and equal_alphas and equal_content

    def assertXmlSchema(self, xml_content: bytes, schema_path: str, schema_file: str) -> bool:
        with resources.files(schema_path).joinpath(schema_file).open("rb") as f:
            xsd = f.read()

        xmlschema_doc = etree.parse(BytesIO(xsd))
        xmlschema = etree.XMLSchema(xmlschema_doc)

        doc = etree.fromstring(xml_content)
        self.assertTrue(xmlschema.validate(
            doc), xmlschema.error_log.last_error)

    def assertXmlEquals(self, got_xml: bytes, expected_xml: bytes) -> bool:
        """
        Compare two XML documents semantically.
        Returns True if equivalent, False otherwise.
        """
        parser = etree.XMLParser(remove_blank_text=True)
        got_tree = etree.fromstring(got_xml, parser)
        expected_tree = etree.fromstring(expected_xml, parser)
        self.assertEqual(etree.tostring(got_tree), etree.tostring(expected_tree),
                         "XML documents are not identical.")

    @patch.object(
        target=WebMapServiceProxy,
        attribute="get_remote_response",
        side_effect=remote_effect,
    )
    @patch.object(
        target=Registry,
        attribute="_fetch_coord_ref_system",
        side_effect=epsg_side_effect,
    )
    def test_matching_secured_map(self, mocked_proxy, mocked_registry):
        expected_png_path = Path(
            Path.joinpath(
                Path(__file__).parent.resolve(),
                "../../test_data/expected_karte_rp.fcgi.png",
            )
        )
        self.client.login(username="User1", password="User1")
        self.query_params.update({"LAYERS": "node1"})
        # wms 1.3.0
        response = self.client.get(
            self.wms_url,
            self.query_params
        )

        self.assertEqual(200, response.status_code)

        received_image = Image.open(BytesIO(response.content))
        expected_image = Image.open(fp=expected_png_path)

        self.assertTrue(self.are_images_equal(received_image, expected_image))

        # wms 1.1.1
        self.query_params.pop("CRS")
        self.query_params.update(
            {"VERSION": "1.1.1", "SRS": "EPSG:25832", "BBOX": "393340,5574710,405660,5581190", })
        response = self.client.get(
            self.wms_url,
            self.query_params
        )

        self.assertEqual(200, response.status_code)

        received_image = Image.open(BytesIO(response.content))
        expected_image = Image.open(fp=expected_png_path)

        self.assertTrue(self.are_images_equal(received_image, expected_image))

    def test_get_capabilities_of_an_active_service_is_answered(self):
        # the proxy answers capabilities unauthenticated as long as the
        # service is active
        response = self.client.get(
            self.wms_url,
            {"SERVICE": "WMS", "REQUEST": "GetCapabilities", "VERSION": "1.3.0"}
        )

        self.assertEqual(200, response.status_code)
        root = etree.fromstring(response.content)
        self.assertEqual("WMS_Capabilities", etree.QName(root).localname)

    def test_get_capabilities_of_an_inactive_service_is_answered_with_the_disabled_report(self):
        # a deactivated service refuses every operation with the Disabled
        # report, its capabilities included (#1147): deactivation shall not
        # leave the metadata of the service readable
        WebMapService.objects.filter(
            pk="cd16cc1f-3abb-4625-bb96-fbe80dbe23e3"
        ).update(is_active=False)

        response = self.client.get(
            self.wms_url,
            {"SERVICE": "WMS", "REQUEST": "GetCapabilities", "VERSION": "1.3.0"}
        )

        self.assertEqual(200, response.status_code)

        got_xml = response.content
        expected_xml = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<ogc:ServiceExceptionReport xmlns:ogc="http://www.opengis.net/ogc" version="1.3.0">'
            '<ogc:ServiceException code="Disabled">'
            'The requested service is temporaly disabled.'
            '</ogc:ServiceException>'
            '</ogc:ServiceExceptionReport>'
        ).encode()

        self.assertXmlSchema(
            got_xml,
            "registry.ows_lib.xml.schemas",
            "wmsExceptionReport130.xsd"
        )
        self.assertXmlEquals(got_xml, expected_xml)
        # the capabilities document itself is not part of the answer
        self.assertNotIn(b"WMS_Capabilities", got_xml)

    def test_unknown_layer_exception(self):
        self.client.login(username="User1", password="User1")
        self.query_params.update({"LAYERS": "qwertz"})
        response = self.client.get(
            self.wms_url,
            self.query_params
        )
        self.assertEqual(200, response.status_code)

        got_xml = response.content
        expected_xml = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<ogc:ServiceExceptionReport '
            'xmlns:ogc="http://www.opengis.net/ogc" version="1.3.0">'
            '<ogc:ServiceException code="LayerNotDefined" locator="LAYERS">'
            'unknown layer'
            '</ogc:ServiceException>'
            '</ogc:ServiceExceptionReport>'
        ).encode()

        self.assertXmlSchema(
            got_xml,
            "registry.ows_lib.xml.schemas",
            "wmsExceptionReport130.xsd"
        )
        self.assertXmlEquals(got_xml, expected_xml)

    def test_forbidden_exception_if_one_requested_layer_is_not_enabled(self):
        self.query_params.update({"LAYERS": "node1"})
        response = self.client.get(
            self.wms_url,
            self.query_params
        )

        self.assertEqual(200, response.status_code)

        got_xml = response.content
        expected_xml = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<ogc:ServiceExceptionReport xmlns:ogc="http://www.opengis.net/ogc" version="1.3.0">'
            '<ogc:ServiceException code="Forbidden">'
            'Permission denied'
            '</ogc:ServiceException>'
            '</ogc:ServiceExceptionReport>'
        ).encode()

        self.assertXmlSchema(
            got_xml,
            "registry.ows_lib.xml.schemas",
            "wmsExceptionReport130.xsd"
        )
        self.assertXmlEquals(got_xml, expected_xml)

    @patch.object(
        target=WebMapServiceProxy,
        attribute="get_remote_response",
        side_effect=[REMOTE_RESPONSE],
    )
    @patch.object(
        target=Registry,
        attribute="_fetch_coord_ref_system",
        side_effect=[EPSG_API_25832_RESPONSE],
    )
    def test_successfully_request_as_anonymous_a_subtree(self, mocked_proxy, mocked_registry):
        self.query_params.update({"LAYERS": "node1.1.1,node1.1.2,node1.1.3"})
        response = self.client.get(
            self.wms_url,
            self.query_params
        )

        self.assertEqual(200, response.status_code)
        # TODO: check the response picture

    @patch.object(
        target=WebMapServiceClient,
        attribute="send_request",
        side_effect=capture_remote_request,
    )
    @patch.object(
        target=Registry,
        attribute="_fetch_coord_ref_system",
        side_effect=epsg_side_effect,
    )
    def test_empty_styled_param_is_forwarded_to_the_upstream_request(
        self, mocked_registry, mocked_send
    ):
        # every standard WMS client sends STYLES= -- the empty value is the
        # default style (OGC 05-008, 7.2.2). The proxy used to rebuild the
        # upstream request from a parameter set which kept only non-empty
        # values, so upstream never read STYLES and refused with
        # "missing parameters ['styles']" (#1154)
        FORWARDED_REQUESTS.clear()
        self.client.login(username="User1", password="User1")
        self.query_params.update({"LAYERS": "node1"})

        response = self.client.get(self.wms_url, self.query_params)

        self.assertEqual(200, response.status_code)
        self.assertEqual(1, len(FORWARDED_REQUESTS))
        forwarded_url = FORWARDED_REQUESTS[0].url
        pairs = parse_qsl(urlparse(forwarded_url).query, keep_blank_values=True)
        self.assertIn(("STYLES", ""), pairs)
        # the parameter is present-with-empty-value, not absent and not filled
        self.assertNotIn(
            "STYLES", [name for name, _ in parse_qsl(urlparse(forwarded_url).query)]
        )


    def ask_for_response_logging(self):
        """Turns response logging on for the service of the fixtures.

        The constraint of the proxy settings only allows logging together with
        camouflage, which is what the API answers for it as well.
        """
        return WebMapServiceProxySetting.objects.create(
            secured_service=WebMapService.objects.get(
                pk="cd16cc1f-3abb-4625-bb96-fbe80dbe23e3"),
            camouflage=True,
            log_response=True)

    def use_own_media_root(self):
        """Keeps the logged bodies of this test out of the media root of the project."""
        media_root = tempfile.TemporaryDirectory(prefix="mrmap-proxy-log-")
        self.addCleanup(media_root.cleanup)
        override = self.settings(MEDIA_ROOT=media_root.name)
        override.enable()
        self.addCleanup(override.disable)
        return media_root.name

    @patch.object(
        target=WebMapServiceProxy,
        attribute="get_remote_response",
        side_effect=remote_effect,
    )
    @patch.object(
        target=Registry,
        attribute="_fetch_coord_ref_system",
        side_effect=epsg_side_effect,
    )
    def test_a_service_with_log_response_answers_and_logs_the_exchange(
            self, mocked_proxy, mocked_registry):
        # the log of a proxied request is an auxiliary of the answer: the service
        # is answered exactly like with the setting off, and the rows are kept in
        # the log models of the requested service's type (#1153)
        self.use_own_media_root()
        self.ask_for_response_logging()
        self.client.login(username="User1", password="User1")
        self.query_params.update({"LAYERS": "node1"})

        response = self.client.get(self.wms_url, self.query_params)

        self.assertEqual(200, response.status_code, response.content)

        logs = WebMapServiceHttpRequestLog.objects.all()
        self.assertEqual(1, logs.count(), "the proxied request was not logged")
        request_log = logs.first()
        self.assertEqual("GET", request_log.method)
        self.assertEqual("User1", request_log.user.username)
        self.assertFalse(request_log.is_test_request)
        self.assertIn("/mrmap-proxy/wms/", request_log.url)

        response_log = request_log.response
        self.assertEqual(200, response_log.status_code)
        self.assertEqual("OK", response_log.reason)
        self.assertGreater(response_log.elapsed, timedelta(0))
        self.assertEqual({"content-type": "image/png"}, response_log.headers)
        with response_log.content.open("rb") as logged:
            self.assertEqual(response.content, logged.read())

        # the row is in the table of the service which was requested, not in the
        # one of another service type
        self.assertEqual(0, WebFeatureServiceHttpRequestLog.objects.count())

    @patch.object(
        target=WebMapServiceProxy,
        attribute="get_remote_response",
        side_effect=remote_effect,
    )
    @patch.object(
        target=Registry,
        attribute="_fetch_coord_ref_system",
        side_effect=epsg_side_effect,
    )
    @patch("registry.models.security.async_analyze_log")
    def test_a_logged_response_is_handed_to_the_analysis_with_its_own_model(
            self, mocked_analysis, mocked_proxy, mocked_registry):
        # the analysis task is told which concrete response log it shall read: the
        # primary key alone does not say which table the row is in (#1153)
        self.use_own_media_root()
        self.ask_for_response_logging()
        self.client.login(username="User1", password="User1")
        self.query_params.update({"LAYERS": "node1"})

        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.get(self.wms_url, self.query_params)

        self.assertEqual(200, response.status_code, response.content)
        response_log = WebMapServiceHttpRequestLog.objects.get().response
        mocked_analysis.apply_async.assert_called_once_with(
            args=(response_log.pk, "registry.webmapservicehttpresponselog"))

    @patch.object(
        target=WebMapServiceProxy,
        attribute="get_remote_response",
        side_effect=remote_effect,
    )
    @patch.object(
        target=Registry,
        attribute="_fetch_coord_ref_system",
        side_effect=epsg_side_effect,
    )
    def test_a_response_which_cannot_be_logged_is_answered_anyway(
            self, mocked_proxy, mocked_registry):
        # the log shall never decide the answer: with a media root which cannot be
        # written the service still serves the map instead of refusing the request
        # (#1153). /proc takes no directory, not even for root.
        override = self.settings(MEDIA_ROOT="/proc/mrmap-unwritable-media")
        override.enable()
        self.addCleanup(override.disable)
        self.ask_for_response_logging()
        self.client.login(username="User1", password="User1")
        self.query_params.update({"LAYERS": "node1"})

        response = self.client.get(self.wms_url, self.query_params)

        self.assertEqual(200, response.status_code, response.content)
        # the map itself reached the client, although its log could not be written
        self.assertEqual("PNG", Image.open(BytesIO(response.content)).format)
        # what could not be finished was rolled back as a whole
        self.assertEqual(0, WebMapServiceHttpRequestLog.objects.count())

    @patch.object(
        target=WebMapServiceProxy,
        attribute="handle_secured_get_map",
        side_effect=TypeError("simulated failure inside the proxy"),
    )
    def test_a_failure_of_the_proxy_is_answered_with_no_applicable_code(
            self, mocked_get_map):
        # a proxy which broke on its own does not tell the caller that it lacks a
        # permission: that sends the operator after a permission which was never
        # the cause of the failure (#1153)
        self.client.login(username="User1", password="User1")
        self.query_params.update({"LAYERS": "node1"})

        response = self.client.get(self.wms_url, self.query_params)

        self.assertEqual(500, response.status_code, response.content)

        got_xml = response.content
        expected_xml = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<ogc:ServiceExceptionReport xmlns:ogc="http://www.opengis.net/ogc" version="1.3.0">'
            '<ogc:ServiceException code="NoApplicableCode">'
            'The server was unable to complete the request.'
            '</ogc:ServiceException>'
            '</ogc:ServiceExceptionReport>'
        ).encode()

        self.assertXmlSchema(
            got_xml,
            "registry.ows_lib.xml.schemas",
            "wmsExceptionReport130.xsd"
        )
        self.assertXmlEquals(got_xml, expected_xml)
        # nothing of the failure is a permission problem
        self.assertNotIn(b"Forbidden", got_xml)


class WebMapServiceProxyFontTest(SimpleTestCase):
    @patch('registry.proxy.wms_proxy.Path.exists', return_value=False)
    def test_no_system_fonts_falls_back_to_a_sized_font_and_renders(self, exists):
        proxy = WebMapServiceProxy()
        font = proxy._get_default_ttf(16)
        self.assertEqual(font.size, 16)
        proxy.ogc_request = OGCRequest(method='GET', params={'WIDTH': '200'})
        image = proxy._create_image_with_text(200, 40, 'Restricted layer')
        self.assertEqual(image.size, (200, 40))
        self.assertIsNotNone(image.getbbox())
