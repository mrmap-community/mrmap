from accounts.models.users import User
from django.contrib.gis.geos import GEOSGeometry
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.db.models.query_utils import Q
from django.test import Client
from epsg_cache.utils import adjust_axis_order, get_epsg_srid
from lxml import etree
from MrMap.settings import BASE_DIR
from registry.models.security import AllowedWebFeatureServiceOperation
from registry.models.service import WebFeatureService
from tests.django.contrib import XpathTestCase


class WebMapServiceProxyTest(XpathTestCase):

    @classmethod
    def setUpClass(cls):
        # we can't setup test data in db inside the normal test setup routines, cause django wraps it with a transaction...
        # Cause this is a system test which depends on other system (mapserver) the test_db setup must be done before the normal transaction routine.
        # Otherwise the objects are not present in the database if the mapserver instance is connecting.
        call_command("loaddata", "test_users.json", verbosity=0)
        call_command("loaddata", "test_keywords.json", verbosity=0)
        call_command("loaddata", "test_crs.json", verbosity=0)
        call_command("loaddata", "test_wfs_proxy.json", verbosity=0)

        call_command(
            "loaddata", "test_allowed_wfs_operation.json", verbosity=0)

        wfs: WebFeatureService = WebFeatureService.objects.get(
            pk="73cf78c9-6605-47fd-ac4f-1be59265df65")

        cap_file = open(
            f"{BASE_DIR}/tests/django/test_data/capabilities/wfs/local_mapserver.2.0.0.xml", mode="rb")

        wfs.xml_backup_file = SimpleUploadedFile(
            'capabilitites.xml', cap_file.read())
        wfs.save()

    @classmethod
    def tearDownClass(cls):
        # Custom clean up... see setUpClass method above for explanations
        User.objects.filter(~Q(username='mrmap')).delete()
        WebFeatureService.objects.all().delete()
        AllowedWebFeatureServiceOperation.objects.all().delete()

    def setUp(self):
        self.client = Client()
        self.wfs_url = "/mrmap-proxy/wfs/73cf78c9-6605-47fd-ac4f-1be59265df65"
        self.query_params = {
            "VERSION": "2.0.0",
            "REQUEST": "GetFeature",
            "SERVICE": "WFS",
            "TYPENAMES": "ms:Countries"
        }

    def test_matching_secured_get_feature_response_for_wfs_200(self):
        self.client.login(username="User1", password="User1")

        get_feature_request = """
            <?xml version='1.0' encoding='UTF-8'?>
            <wfs:GetFeature 
                xmlns:wfs="http://www.opengis.net/wfs/2.0" 
                outputFormat="application/gml+xml; version=3.2" 
                version="2.0.0" 
                service="wfs">
                <wfs:Query typeNames="ms:Countries"/>
            </wfs:GetFeature>
        """

        response = self.client.post(
            self.wfs_url,
            data=get_feature_request.strip(),
            content_type="application/gml+xml; version=3.2"
        )

        response_xml = etree.fromstring(response.content)

        gml = self._get_by_xpath(
            response_xml, "/wfs:FeatureCollection/wfs:boundedBy/gml:*")
        gml_str = etree.tostring(
            gml[0],
            encoding="UTF-8"
        )

        srs = gml[0].get("srsName")
        if srs:
            _, srid = get_epsg_srid(srs)
        else:
            srid = 4326  # default srs
        bounded_by_geometry = GEOSGeometry(
            geo_input=GEOSGeometry.from_gml(gml_str).wkt, srid=srid)
        # cause we are testing for wfs 2.0.0, we need to adjust the axis order to get an correct initialized python geometry object.
        bounded_by_geometry = adjust_axis_order(bounded_by_geometry)

        allowed_area: GEOSGeometry = AllowedWebFeatureServiceOperation.objects.get(
            pk="1235").allowed_area

        self.assertEqual(200, response.status_code)
        self.assertXpathValue(
            response_xml, "/wfs:FeatureCollection/@numberMatched", 4)
        self.assertXpathValue(
            response_xml, "/wfs:FeatureCollection/@numberReturned", 4)
        self.assertTrue(
            allowed_area.overlaps(bounded_by_geometry),
            msg="configured allowed area does not overlaps the responsed bounding box"
        )
