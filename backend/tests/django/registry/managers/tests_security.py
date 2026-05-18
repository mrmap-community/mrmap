import json

from accounts.models.users import User
from accounts.models.groups import Group
from django.contrib.gis.geos import GEOSGeometry
from django.test import RequestFactory, TestCase
from registry.enums.service import OGCOperationEnum
from registry.models.security import AllowedWebMapServiceOperation, WebMapServiceOperation
from registry.models.service import Layer, WebFeatureService, WebMapService
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


class WebMapServiceSecurityManagerTest(TestCase):

    fixtures = ["test_keywords.json", "test_crs.json", "test_users.json", "test_wms.json",
                "test_allowed_wms_operation.json"]

    def test_get_with_security_info_for_user_1(self):
        factory = RequestFactory()

        user = User.objects.get(username="User1")

        request = factory.get(
            path='/mrmap-proxy/wms/cd16cc1f-3abb-4625-bb96-fbe80dbe23e3/',
            data={
                "request": "GetMap",
                "service": "WMS",
                "version": "1.3.0",
                "layers": "node1",
                "styles": "",
                "crs": "EPSG:4326",
                "bbox": "-14.725670173410293, 54.832216088439935, -5.435135881276892, 49.1554694663281",
                "width": "800",
                "height": "600",
                "format": "image/png"
            }
        )
        request.user = user
        ogc_request = OGCRequest.from_django_request(request)

        wms = WebMapService.security.get_with_security_info(
            pk="cd16cc1f-3abb-4625-bb96-fbe80dbe23e3", request=ogc_request)

        allowed_area_union_expected = GEOSGeometry(
            'SRID=4326;POLYGON ((7.604598999023437 50.358275670499495, 7.596702575683594 50.3505540678909, 7.578248977661132 50.34721312721887, 7.5626277923583975 50.35641383867465, 7.568635940551757 50.36418924017004, 7.576103210449219 50.36709100023668, 7.58528709411621 50.363313202264315, 7.590723701840718 50.36270117831575, 7.588376998901368 50.365284264812935, 7.584686279296875 50.36895241327558, 7.590694427490234 50.3750288710761, 7.594985961914062 50.37497413168687, 7.602624893188476 50.372346566727884, 7.609319686889648 50.364134488274665, 7.6065731048583975 50.36172534234488, 7.605592026242317 50.36163593146097, 7.604598999023437 50.358275670499495))'
        )
        allowed_area_union_given = wms.allowed_area_union
        # don't know why, but equals does not match for true... so i used equals_exact with tolerance here...
        self.assertTrue(allowed_area_union_expected.equals(
            allowed_area_union_given))

    def test_get_with_security_info_for_user_2(self):
        factory = RequestFactory()

        user = User.objects.get(username="User2")

        request = factory.get(
            path='/mrmap-proxy/wms/cd16cc1f-3abb-4625-bb96-fbe80dbe23e3/',
            data={
                "request": "GetMap",
                "service": "WMS",
                "version": "1.3.0",
                "layers": "node1",
                "styles": "",
                "crs": "EPSG:4326",
                "bbox": "-14.725670173410293, 54.832216088439935, -5.435135881276892, 49.1554694663281",
                "width": "800",
                "height": "600",
                "format": "image/png"
            }
        )
        request.user = user
        ogc_request = OGCRequest.from_django_request(request)

        wms = WebMapService.security.get_with_security_info(
            pk="cd16cc1f-3abb-4625-bb96-fbe80dbe23e3", request=ogc_request)

        allowed_area_union_given = wms.allowed_area_union
        self.assertIsNone(allowed_area_union_given)

    def test_get_with_security_info_for_anonymous_user(self):
        factory = RequestFactory()

        user = User.objects.get(username="AnonymousUser")

        request = factory.get(
            path='/mrmap-proxy/wms/cd16cc1f-3abb-4625-bb96-fbe80dbe23e3/',
            data={
                "request": "GetMap",
                "service": "WMS",
                "version": "1.3.0",
                "layers": "node1.1",
                "styles": "",
                "crs": "EPSG:4326",
                "bbox": "-14.725670173410293, 54.832216088439935, -5.435135881276892, 49.1554694663281",
                "width": "800",
                "height": "600",
                "format": "image/png"
            }
        )
        request.user = user
        ogc_request = OGCRequest.from_django_request(request)

        wms = WebMapService.security.get_with_security_info(
            pk="cd16cc1f-3abb-4625-bb96-fbe80dbe23e3", request=ogc_request)

        allowed_area_union_expected = GEOSGeometry(
            'SRID=4326;Polygon ((7.590694427490234 50.3750288710761, 7.584686279296875 50.36895241327558, 7.588376998901368 50.365284264812935, 7.592754364013672 50.36046596739436, 7.6065731048583975 50.36172534234488, 7.609319686889648 50.364134488274665, 7.602624893188476 50.372346566727884, 7.594985961914062 50.37497413168687, 7.590694427490234 50.3750288710761))'
        )
        allowed_area_union_given = wms.allowed_area_union
        # don't know why, but equals does not match for true... so i used equals_exact with tolerance here...
        self.assertTrue(allowed_area_union_expected.equals(
            allowed_area_union_given))

    def test_get_with_security_info_for_mrmap_user(self):
        factory = RequestFactory()
        test_orga, _ = Group.objects.get_or_create(
            name="Testorganization")
        user = User.objects.get(username="mrmap")
        user.groups.add(test_orga)
        obj = AllowedWebMapServiceOperation.objects.create(
            secured_service=WebMapService.objects.get(
                pk="cd16cc1f-3abb-4625-bb96-fbe80dbe23e3"),
            allowed_area=GEOSGeometry(
                'SRID=4326;MultiPolygon (((6.968079 50.270471, 6.893234 50.167663, 7.088242 50.156226, 7.159653 50.197561, 7.159653 50.240618, 7.061462 50.193166, 7.001038 50.213383, 7.013397 50.234909, 6.968079 50.270471)))'
            )
        )
        obj.operations.set(WebMapServiceOperation.objects.filter(
            value=OGCOperationEnum.GET_MAP.value))
        obj.secured_layers.set(Layer.objects.filter(identifier="node1.1"))
        obj.allowed_groups.add(test_orga)
        request = factory.get(
            path='/mrmap-proxy/wms/cd16cc1f-3abb-4625-bb96-fbe80dbe23e3/',
            data={
                "request": "GetMap",
                "service": "WMS",
                "version": "1.3.0",
                "layers": "node1.1",
                "styles": "",
                "crs": "EPSG:4326",
                "bbox": "-14.725670173410293, 54.832216088439935, -5.435135881276892, 49.1554694663281",
                "width": "800",
                "height": "600",
                "format": "image/png"
            }
        )
        request.user = user
        ogc_request = OGCRequest.from_django_request(request)

        wms = WebMapService.security.get_with_security_info(
            pk="cd16cc1f-3abb-4625-bb96-fbe80dbe23e3", request=ogc_request)

        allowed_area_union_expected = GEOSGeometry(
            'SRID=4326;MULTIPOLYGON (((6.968079 50.270471, 6.893234 50.167663, 7.088242 50.156226, 7.159653 50.197561, 7.159653 50.240618, 7.061462 50.193166, 7.001038 50.213383, 7.013397 50.234909, 6.968079 50.270471)), ((7.590694427490234 50.3750288710761, 7.584686279296875 50.36895241327558, 7.588376998901368 50.365284264812935, 7.592754364013672 50.36046596739436, 7.6065731048583975 50.36172534234488, 7.609319686889648 50.364134488274665, 7.602624893188476 50.372346566727884, 7.594985961914062 50.37497413168687, 7.590694427490234 50.3750288710761)))'
        )
        allowed_area_union_given = wms.allowed_area_union
        # don't know why, but equals does not match for true... so i used equals_exact with tolerance here...
        self.assertTrue(allowed_area_union_expected.equals(
            allowed_area_union_given))
