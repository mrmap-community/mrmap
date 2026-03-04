import json

from accounts.models.users import User
from django.contrib.gis.geos import GEOSGeometry
from django.test import RequestFactory, TestCase
from registry.models.service import WebFeatureService
from registry.ows_lib.request.ogc_request import OGCRequest


class WebFeatureServiceSecurityManagerTest(TestCase):

    fixtures = ["test_keywords.json", "test_crs.json", "test_users.json", "test_wfs.json", "test_wfs_proxy.json",
                "test_allowed_wfs_operation.json"]

    def test_get_with_security_info(self):
        get_feature_request = """<?xml version="1.0" encoding="UTF-8"?>
            <GetFeature version="2.0.0" service="WFS" outputFormat="application/gml+xml; version=3.2"
                xmlns="http://www.opengis.net/wfs/2.0"
                xmlns:fes="http://www.opengis.net/fes/2.0"
                xmlns:gml="http://www.opengis.net/gml/3.2"
                xmlns:ms="http://www.someserver.example.com/ms"
                xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:schemaLocation="http://www.opengis.net/wfs/2.0
                                http://schemas.opengis.net/wfs/2.0/wfs.xsd
                                http://www.opengis.net/gml/3.2
                                http://schemas.opengis.net/gml/3.2.1/gml.xsd
                                http://www.someserver.example.com/ms">

                <Query typeNames="ms:Countries, ms:Rivers">
                </Query>
            </GetFeature>
        """

        factory = RequestFactory()

        user = User.objects.get(username="User1")

        request = factory.post(path='/mrmap-proxy/wfs/73cf78c9-6605-47fd-ac4f-1be59265df65/',
                               data=get_feature_request, content_type="application/gml+xml; version=3.2")
        request.user = user
        ogc_request = OGCRequest.from_django_request(request)

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
