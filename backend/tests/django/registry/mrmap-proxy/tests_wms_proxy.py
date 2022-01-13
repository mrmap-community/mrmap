import hashlib
from pathlib import Path
from unittest.mock import patch

from axis_order_cache.models import Origin, SpatialReference
from axis_order_cache.registry import Registry
from django.test import Client, TestCase
from registry.models.security import AllowedWebMapServiceOperation
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
    # def setUpClass():
    #     management.call_command("loaddata", "test_users.json", verbosity=1)
    #     management.call_command("loaddata", "test_wms.json", verbosity=1)
    #     management.call_command("loaddata", "test_allowedoperation.json", verbosity=1)

    # def tearDownClass():
    #     pass

    def setUp(self):
        self.client = Client()

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
    def test_success(self, mocked_proxy, mocked_registry):
        from django.db import connection

        db_name = connection.settings_dict["NAME"]
        print(db_name)
        print(AllowedWebMapServiceOperation.objects.all())

        expected_png_path = Path(
            Path.joinpath(
                Path(__file__).parent.resolve(),
                "../../test_data/expected_karte_rp.fcgi.png",
            )
        )
        in_file = open(expected_png_path, "rb")
        expected_png = in_file.read()
        in_file.close()
        print(AllowedWebMapServiceOperation.objects.all())

        response = self.client.get(
            "/mrmap-proxy/wms/cd16cc1f-3abb-4625-bb96-fbe80dbe23e3?map=/etc/mapserver/security_mask_test_db.map&VERSION=1.3.0&REQUEST=GetMap&SERVICE=WMS&LAYERS=node1&STYLES=&CRS=EPSG:25832&BBOX=393340,5574710,405660,5581190&WIDTH=1563&HEIGHT=920&FORMAT=image/png&BGCOLOR=0xffffff&TRANSPARENT=TRUE"
        )
        print(AllowedWebMapServiceOperation.objects.all())

        f = open("response.png", "wb")
        f.write(response.content)
        f.close()

        self.assertEqual(200, response.status_code)
        self.assertEqual(
            hashlib.md5(expected_png).hexdigest(),
            hashlib.md5(response.content).hexdigest(),
        )
