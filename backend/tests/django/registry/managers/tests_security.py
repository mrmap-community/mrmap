import json
import os

from accounts.models.users import User
from django.contrib.gis.geos import GEOSGeometry
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
        path = os.path.join(DJANGO_TEST_ROOT_DIR,
                            "./test_data/xml_requests/get_feature_2.0.0.xml")

        get_feature_request: GetFeatureRequest = load_xmlobject_from_file(
            filename=path, xmlclass=GetFeatureRequest)

        # we add a random additional requested ft, to be clear, that the manager collects the correct geometry_property_names
        get_feature_request.queries[0].type_names = [
            "ms:Countries", "ms:Rivers"]

        factory = RequestFactory()

        user = User.objects.get(username="User1")

        request = factory.post(path='/mrmap-proxy/wfs/73cf78c9-6605-47fd-ac4f-1be59265df65/',
                               data=get_feature_request.serializeDocument().decode("UTF-8"), content_type="application/gml+xml; version=3.2")
        request.user = user

        ogc_request = OGCRequest(request=request)

        wfs = WebFeatureService.security.get_with_security_info(
            pk="73cf78c9-6605-47fd-ac4f-1be59265df65", request=ogc_request)

        allowed_area_union_expected = GEOSGeometry("SRID=4326;POLYGON ((-14.725670173410293 54.832216088439935, -5.435135881276892 49.1554694663281, -4.082178360026234 42.72691779324404, 2.1166591694489796 41.07051723812464, 7.05663770755126 42.20224421073627, 13.618688317285574 4.47565842021575, 15.987912975940674 9.7521877167475, 14.66892412940092 54.15103930861173, 10.89001402833091 8.271249535024225, 7.179678246901659 57.11916111340176, -0.277712915455538 61.882949994691586, -14.725670173410293 54.832216088439935))")
        allowed_area_union_given = GEOSGeometry(json.dumps(
            wfs.security_info_per_feature_type[0]["allowed_area_union"]))
        try:

            self.assertEqual(
                "ms:Countries", wfs.security_info_per_feature_type[0]["type_name"])
            self.assertEqual(
                "ms:Geometry", wfs.security_info_per_feature_type[0]["geometry_property_name"])
            # don't know why, but equals does not match for true... so i used equals_exact with tolerance here...
            self.assertTrue(allowed_area_union_expected.equals_exact(
                allowed_area_union_given, tolerance=0.000000001))

        except AttributeError as e:
            self.fail(msg=f"wfs object shall has the attribute '{e.name}'")
