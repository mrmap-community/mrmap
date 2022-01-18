from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from accounts.models.users import User
from axis_order_cache.models import Origin, SpatialReference
from axis_order_cache.registry import Registry
from django.core.management import call_command
from django.db.models.query_utils import Q
from django.test import Client, TestCase
from lxml import etree, objectify
from PIL import Image, ImageChops
from registry.models.security import AllowedWebMapServiceOperation
from registry.models.service import WebMapService
from registry.proxy.wms_proxy import WebMapServiceProxy
from rest_framework import status


class MockResponse:
    def __init__(self, status_code, content, content_type, url=""):
        self.status_code = status_code

        if isinstance(content, Path):
            in_file = open(content, "rb")
            self.content = in_file.read()
            in_file.close()

        if isinstance(content, bytes):
            self.content = content

        self.reason = "OK"
        self.elapsed = 123
        self.headers = {}
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


class WebMapServiceProxyTest(TestCase):

    @classmethod
    def setUpClass(cls):
        # we can't setup test data in db inside the normal test setup routines, cause django wraps it with a transaction...
        # Cause this is a system test which depends on other system (mapserver) the test_db setup must be done before the normal transaction routine.
        # Otherwise the objects are not present in the database if the mapserver instance is connecting.
        call_command("loaddata", "test_users.json", verbosity=0)
        call_command("loaddata", "test_wms.json", verbosity=0)
        call_command("loaddata", "test_allowedoperation.json", verbosity=0)

    @classmethod
    def tearDownClass(cls):
        # Custom clean up... see setUpClass method above for explanations
        User.objects.filter(~Q(username='mrmap')).delete()
        WebMapService.objects.all().delete()
        AllowedWebMapServiceOperation.objects.all().delete()

    def setUp(self):
        self.client = Client()
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

    @patch.object(
        target=WebMapServiceProxy,
        attribute="get_remote_response",
        side_effect=[REMOTE_RESPONSE],
    )
    @patch.object(
        target=Registry,
        attribute="coord_ref_system_export",
        side_effect=[EPSG_API_25832_RESPONSE],
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
        response = self.client.get(
            self.wms_url,
            self.query_params
        )

        self.assertEqual(200, response.status_code)

        received_image = Image.open(BytesIO(response.content))
        expected_image = Image.open(fp=expected_png_path)

        self.assertTrue(self.are_images_equal(received_image, expected_image))

    def test_unknown_layer_exception(self):
        self.client.login(username="User1", password="User1")
        self.query_params.update({"LAYERS": "qwertz"})
        response = self.client.get(
            self.wms_url,
            self.query_params
        )

        self.assertEqual(200, response.status_code)

        response_xml = objectify.fromstring(response.content)
        expected_xml = objectify.fromstring(b'<?xml version="1.0" encoding="UTF-8"?>'
                                            b'<ServiceExceptionReport version="1.3.0" xmlns="http://www.opengis.net/ogc" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:schemaLocation="http://www.opengis.net/ogc">'
                                            b'<ServiceException code="LayerNotDefined" locator="LAYERS">'
                                            b'unknown layer'
                                            b'</ServiceException>'
                                            b'</ServiceExceptionReport>')
        self.assertEqual(etree.tostring(response_xml),
                         etree.tostring(expected_xml))

    def test_forbidden_exception_if_one_requested_layer_is_not_enabled(self):
        self.query_params.update({"LAYERS": "node1"})
        response = self.client.get(
            self.wms_url,
            self.query_params
        )

        self.assertEqual(200, response.status_code)

        response_xml = objectify.fromstring(response.content)
        expected_xml = objectify.fromstring(b'<?xml version="1.0" encoding="UTF-8"?>'
                                            b'<ServiceExceptionReport version="1.3.0" xmlns="http://www.opengis.net/ogc" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:schemaLocation="http://www.opengis.net/ogc">'
                                            b'<ServiceException code="Forbidden">'
                                            b'The requesting user has no permissions to access the service.'
                                            b'</ServiceException>'
                                            b'</ServiceExceptionReport>')
        self.assertEqual(etree.tostring(response_xml),
                         etree.tostring(expected_xml))

    @patch.object(
        target=WebMapServiceProxy,
        attribute="get_remote_response",
        side_effect=[REMOTE_RESPONSE],
    )
    @patch.object(
        target=Registry,
        attribute="coord_ref_system_export",
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
