import os

from accounts.models.users import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.db.models.query_utils import Q
from django.test import Client, TestCase
from eulxml.xmlmap import load_xmlobject_from_file
from MrMap.settings import BASE_DIR
from ows_lib.xml_mapper.xml_requests.wfs.get_feature import GetFeatureRequest
from registry.models.security import AllowedWebFeatureServiceOperation
from registry.models.service import WebFeatureService
from tests.django.settings import DJANGO_TEST_ROOT_DIR


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

        path = os.path.join(DJANGO_TEST_ROOT_DIR,
                            "./test_data/xml_requests/get_feature_2.0.0.xml")

        get_feature_request: GetFeatureRequest = load_xmlobject_from_file(
            filename=path, xmlclass=GetFeatureRequest)

        response = self.client.post(
            self.wfs_url,
            data=get_feature_request.serializeDocument().decode("UTF-8"),
            content_type="application/gml+xml; version=3.2"
        )

        print("response: ", response.content)
        self.assertEqual(200, response.status_code)

        # TODO: compare response xml content... if there is any spatial data outside the secured area the test should fail
