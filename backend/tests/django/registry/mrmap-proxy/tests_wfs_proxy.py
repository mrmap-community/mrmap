
from accounts.models.users import User
from axis_order_cache.utils import adjust_axis_order
from django.contrib.gis.geos import GEOSGeometry
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.db.models.query_utils import Q
from django.test import Client, TestCase
from eulxml.xmlmap import load_xmlobject_from_string
from MrMap.settings import BASE_DIR
from ows_lib.xml_mapper.xml_requests.wfs.get_feature import (GetFeatureRequest,
                                                             Query)
from ows_lib.xml_mapper.xml_responses.wfs.feature_collection import \
    FeatureCollection
from registry.models.security import AllowedWebFeatureServiceOperation
from registry.models.service import WebFeatureService


class WebMapServiceProxyTest(TestCase):

    @classmethod
    def setUpClass(cls):
        # we can't setup test data in db inside the normal test setup routines, cause django wraps it with a transaction...
        # Cause this is a system test which depends on other system (mapserver) the test_db setup must be done before the normal transaction routine.
        # Otherwise the objects are not present in the database if the mapserver instance is connecting.
        call_command("loaddata", "test_users.json", verbosity=0)
        call_command("loaddata", "test_keywords.json", verbosity=0)
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

    def test_matching_secured_get_feature_response(self):
        self.client.login(username="User1", password="User1")

        query = Query()
        query.type_names = ["ms:Countries"]

        get_feature_request: GetFeatureRequest = GetFeatureRequest()
        get_feature_request.output_format = "application/gml+xml; version=3.2"
        get_feature_request.version = "2.0.0"
        get_feature_request.service_type = "wfs"
        get_feature_request.queries.append(query)

        response = self.client.post(
            self.wfs_url,
            data=get_feature_request.serializeDocument().decode("UTF-8"),
            content_type="application/gml+xml; version=3.2"
        )

        feature_collection: FeatureCollection = load_xmlobject_from_string(
            string=response.content, xmlclass=FeatureCollection)

        bounded_by: GEOSGeometry = feature_collection.bounded_by.geos
        # cause we are testing for wfs 2.0.0, we need to adjust the axis order to get an correct initialized python geometry object.
        bounded_by = adjust_axis_order(bounded_by)

        allowed_area: GEOSGeometry = AllowedWebFeatureServiceOperation.objects.get(
            pk="1235").allowed_area

        self.assertEqual(200, response.status_code)
        self.assertEqual(feature_collection.number_matched, 4)
        self.assertEqual(feature_collection.number_returned, 4)
        self.assertTrue(allowed_area.overlaps(
            bounded_by), msg="configured allowed area does not overlaps the responsed bounding box")
