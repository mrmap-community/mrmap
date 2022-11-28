import os

from accounts.models.users import User
from django.test import RequestFactory, TestCase
from eulxml.xmlmap import load_xmlobject_from_file
from ows_lib.models.ogc_request import OGCRequest
from ows_lib.xml_mapper.xml_requests.wfs.get_feature import GetFeatureRequest
from registry.models.service import WebFeatureService
from tests.django.settings import DJANGO_TEST_ROOT_DIR


class WebFeatureServiceSecurityManagerTest(TestCase):

    fixtures = ["test_keywords.json", "test_users.json", "test_wfs.json", "test_wfs_proxy.json",
                "test_allowed_wfs_operation.json"]

    def test_get_with_security_info(self):
        """Test that create manager function works correctly."""

        path = os.path.join(DJANGO_TEST_ROOT_DIR,
                            "./test_data/xml_requests/get_feature_2.0.0.xml")

        get_feature_request: GetFeatureRequest = load_xmlobject_from_file(
            filename=path, xmlclass=GetFeatureRequest)

        factory = RequestFactory()

        user = User.objects.get(username="User1")

        request = factory.post(path='/mrmap-proxy/wfs/73cf78c9-6605-47fd-ac4f-1be59265df65/',
                               data=get_feature_request.serializeDocument().decode("UTF-8"), content_type="application/gml+xml; version=3.2")
        request.user = user

        ogc_request = OGCRequest(request=request)

        wfs = WebFeatureService.security.get_with_security_info(
            pk="73cf78c9-6605-47fd-ac4f-1be59265df65", request=ogc_request)

        try:

            self.assertEqual(
                [{"type_name": "ms:Countries", "geometry_property_name": "ms:Geometry"}],
                wfs.geometry_property_names,
                msg="There shall be a geometry_property_names property with type_name geometry_property_name information")

        except AttributeError as e:
            self.fail(msg=f"wfs object shall has the attribute '{e.name}'")
