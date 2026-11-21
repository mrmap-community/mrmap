import json

from accounts.models.groups import Group
from accounts.models.users import User
from django.contrib.gis.geos import GeometryCollection, GEOSGeometry
from django.test import RequestFactory, TestCase
from registry.enums.service import OGCOperationEnum
from registry.models.security import (AllowedWebMapServiceOperation,
                                      WebMapServiceOperation)
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


class WebFeatureServiceAllowedAreaScopingTest(TestCase):
    """The union of #1470: only the rules of the requesting user are unioned.

    ``test_wfs_proxy.json`` knows the feature types ``ms:Countries`` and
    ``ms:Rivers`` of one service; the fixture below adds ``ms:Lakes`` to it. The
    rules are all for the GetFeature operation of that service:

    - 1235 (``test_allowed_wfs_operation.json``): ``ms:Countries`` of Group1 of
      User1.
    - 1236: ``ms:Countries`` of Group2 of User2.
    - 1237 and 1238: two rules of ``ms:Rivers``, both of Group2, so the union of
      User2 reads more than one rule.
    - 1239: ``ms:Lakes`` without any allowed group, which serves every caller.

    ``ms:Rivers`` has no rule of Group1, so User1 has no rule for it at all.
    """

    fixtures = ["test_keywords.json", "test_crs.json", "test_users.json",
                "test_wfs_proxy.json", "test_allowed_wfs_operation.json",
                "test_allowed_wfs_operation_scoping.json"]

    # the area of rule 1235 as the union answers it: a POLYGON, the way the
    # existing test of the manager states it
    AREA_OF_GROUP1 = "POLYGON ((-14.725670173410293 54.832216088439935, " \
        "-5.435135881276892 49.1554694663281, -4.082178360026234 42.72691779324404, " \
        "2.1166591694489796 41.07051723812464, 7.05663770755126 42.20224421073627, " \
        "13.618688317285574 4.47565842021575, 15.987912975940674 9.7521877167475, " \
        "14.66892412940092 54.15103930861173, 10.89001402833091 8.271249535024225, " \
        "7.179678246901659 57.11916111340176, -0.277712915455538 61.882949994691586, " \
        "-14.725670173410293 54.832216088439935))"
    AREA_OF_1236 = "POLYGON ((40 -40, 50 -40, 50 -30, 40 -30, 40 -40))"
    AREA_OF_1237 = "POLYGON ((5 5, 10 5, 10 10, 5 10, 5 5))"
    AREA_OF_1238 = "POLYGON ((15 15, 20 15, 20 20, 15 20, 15 15))"
    AREA_WITHOUT_GROUPS = "POLYGON ((-30 30, -20 30, -20 40, -30 40, -30 30))"

    def _security_info_of(self, request_user: str, type_names: str) -> dict:
        """The per feature type security info of one GetFeature, by type name.

        Args:
            request_user: username of the requesting user
            type_names: comma separated identifiers the query asks
        """
        get_feature_request = f"""<?xml version="1.0" encoding="UTF-8"?>
            <GetFeature version="2.0.0" service="WFS"
                outputFormat="application/gml+xml; version=3.2"
                xmlns="http://www.opengis.net/wfs/2.0"
                xmlns:fes="http://www.opengis.net/fes/2.0"
                xmlns:gml="http://www.opengis.net/gml/3.2"
                xmlns:ms="http://www.someserver.example.com/ms">
                <Query typeNames="{type_names}"/>
            </GetFeature>
        """

        request = RequestFactory().post(
            path='/mrmap-proxy/wfs/73cf78c9-6605-47fd-ac4f-1be59265df65/',
            data=get_feature_request,
            content_type="application/gml+xml; version=3.2")
        request.user = User.objects.get(username=request_user)

        wfs = WebFeatureService.security.get_with_security_info(
            pk="73cf78c9-6605-47fd-ac4f-1be59265df65",
            request=OGCRequest.from_django_request(request))

        return {info["type_name"]: info
                for info in wfs.security_info_per_feature_type}

    def _area_union_of(self, security_info: dict, type_name: str) -> GEOSGeometry:
        return GEOSGeometry(json.dumps(
            security_info[type_name]["allowed_area_union"]))

    def test_union_excludes_the_rule_of_another_group(self):
        """User1 is not answered the area Group2 configured for the same type.

        Before #1470 the union read ALL rules of the feature type and answered
        both areas, so User1 was restricted to an extent including the area of
        Group2 and User2 an extent including the area of Group1.
        """
        union = self._area_union_of(
            self._security_info_of("User1", "ms:Countries"), "ms:Countries")

        self.assertTrue(GEOSGeometry(f"SRID=4326;{self.AREA_OF_GROUP1}"
                                     ).equals_exact(union, tolerance=0.000000001))

    def test_union_of_the_other_group_is_its_own_rule(self):
        """The mirror of the first test: User2 is answered the area of Group2."""
        union = self._area_union_of(
            self._security_info_of("User2", "ms:Countries"), "ms:Countries")

        self.assertTrue(GEOSGeometry(f"SRID=4326;{self.AREA_OF_1236}"
                                     ).equals_exact(union, tolerance=0.000000001))

    def test_union_of_several_own_rules_is_their_union(self):
        """The narrowing must not drop to a single rule of the requesting user."""
        union = self._area_union_of(
            self._security_info_of("User2", "ms:Rivers"), "ms:Rivers")

        # the boxes are disjoint, so the union covers exactly both; an exact
        # geometry comparison is not used because the database answers the
        # union of disjoint polygons as a single MULTIPOLYGON whose member
        # order is not part of the contract
        box1 = GEOSGeometry(f"SRID=4326;{self.AREA_OF_1237}")
        box2 = GEOSGeometry(f"SRID=4326;{self.AREA_OF_1238}")
        self.assertTrue(union.covers(box1) and union.covers(box2))
        self.assertAlmostEqual(union.area, box1.area + box2.area, places=7)

    def test_rule_without_allowed_groups_is_unioned_for_every_caller(self):
        """A rule which names no group serves every caller, so it is unioned."""
        for request_user in ("User1", "User2"):
            with self.subTest(request_user=request_user):
                union = self._area_union_of(
                    self._security_info_of(request_user, "ms:Lakes"),
                    "ms:Lakes")
                self.assertTrue(GEOSGeometry(
                    f"SRID=4326;{self.AREA_WITHOUT_GROUPS}"
                ).equals_exact(union, tolerance=0.000000001))

    def test_feature_type_without_a_relevant_rule_is_not_annotated(self):
        """No entry, not an unrestricted one.

        The only rules of ``ms:Rivers`` are of Group2, so User1 has no rule for
        it. An entry with an empty union would tell the proxy to restrict the
        query without any area, since an empty allowed area means no spatial
        restriction (registry.ows_lib.request.ogc_request.OGCRequest
        ._restrict_query). Without an entry the request stays unanswerable for
        that feature type.
        """
        security_info = self._security_info_of("User1", "ms:Rivers")

        self.assertEqual(security_info, {})


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
        allowed_area_union_given = GeometryCollection(
            *[aop.allowed_area for aop in wms.relevant_allowed_operations],
            srid=4623
        ).unary_union

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

        self.assertIs(len(wms.relevant_allowed_operations), 0)

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
        allowed_area_union_given = GeometryCollection(
            *[aop.allowed_area for aop in wms.relevant_allowed_operations],
            srid=4623
        ).unary_union
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
        allowed_area_union_given = GeometryCollection(
            *[aop.allowed_area for aop in wms.relevant_allowed_operations],
            srid=4623
        ).unary_union
        # don't know why, but equals does not match for true... so i used equals_exact with tolerance here...
        self.assertTrue(allowed_area_union_expected.equals(
            allowed_area_union_given))
