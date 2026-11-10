from accounts.models.users import User
from django.contrib.gis.geos import GEOSGeometry
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.db.models.query_utils import Q
from epsg_cache.utils import adjust_axis_order, get_epsg_srid
from lxml import etree
from MrMap.settings import BASE_DIR
from registry.models.security import AllowedWebFeatureServiceOperation
from registry.models.service import WebFeatureService
from rest_framework.test import APIClient
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
        self.client = APIClient()
        self.wfs_url = "/mrmap-proxy/wfs/73cf78c9-6605-47fd-ac4f-1be59265df65"
        self.query_params = {
            "VERSION": "2.0.0",
            "REQUEST": "GetFeature",
            "SERVICE": "WFS",
            "TYPENAMES": "ms:Countries"
        }

    def test_get_capabilities_of_an_inactive_service_is_answered_with_the_disabled_report(self):
        # a deactivated service refuses every operation with the Disabled
        # report, its capabilities included (#1147). WFS 2.0.0 profiles
        # against OWS Common, so the report is the common ExceptionReport
        WebFeatureService.objects.filter(
            pk="73cf78c9-6605-47fd-ac4f-1be59265df65"
        ).update(is_active=False)

        response = self.client.get(
            self.wfs_url,
            {"SERVICE": "WFS", "REQUEST": "GetCapabilities", "VERSION": "2.0.0"}
        )

        self.assertEqual(400, response.status_code)
        root = etree.fromstring(response.content)
        self.assertEqual("ExceptionReport", etree.QName(root).localname)
        exception = root.find(".//{*}Exception")
        self.assertIsNotNone(exception, response.content)
        self.assertEqual("Disabled", exception.get("exceptionCode"))
        # the capabilities document itself is not part of the answer
        self.assertNotIn(b"WFS_Capabilities", response.content)

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

        self.assertEqual(200, response.status_code, response.content)
        response_xml = etree.fromstring(response.content)
        self.assertEqual(
            response_xml.tag,
            "{http://www.opengis.net/wfs/2.0}FeatureCollection",
            response.content,
        )
        try:

            gml = self._get_by_xpath(
                response_xml,
                "/wfs:FeatureCollection/wfs:boundedBy/gml:*"
            )
            gml_str = etree.tostring(
                gml[0],
                encoding="UTF-8"
            )
        except Exception as e:
            self.fail(
                f"Failed to parse the response xml and get the boundedBy element. Error: {e}")

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

        self.assertXpathValue(
            response_xml, "/wfs:FeatureCollection/@numberMatched", "4")
        self.assertXpathValue(
            response_xml, "/wfs:FeatureCollection/@numberReturned", "4")
        self.assertTrue(
            allowed_area.overlaps(bounded_by_geometry),
            msg="configured allowed area does not overlaps the responsed bounding box"
        )

    def assert_feature_collection(self, response, number_matched: str = None,
                                  number_returned: str = None):
        """The response is a feature collection answering the numbers given.

        A number which is not passed is not asserted: a service asked for a page
        of features does not answer how many matched in total at all.

        A refused OGC request answers an exception report instead; the report of
        the endpoints catch-all is never a feature collection.
        """
        self.assertEqual(200, response.status_code, response.content)
        response_xml = etree.fromstring(response.content)
        self.assertEqual(
            "{http://www.opengis.net/wfs/2.0}FeatureCollection",
            response_xml.tag,
            response.content,
        )
        if number_matched is not None:
            self.assertXpathValue(
                response_xml,
                "/wfs:FeatureCollection/@numberMatched",
                str(number_matched),
            )
        if number_returned is not None:
            self.assertXpathValue(
                response_xml,
                "/wfs:FeatureCollection/@numberReturned",
                str(number_returned),
            )
        return response_xml

    def test_secured_get_feature_of_the_kvp_binding_is_answered_secured(self):
        """The key value pairing binding is secured like the XML binding.

        The proxy secures the request *document*, so the parameters of this
        binding are translated into that document before the restriction of the
        allowed area is applied. Without the translation no document existed to
        restrict and the request was answered with the permissions report of the
        catch-all (#1155).
        """
        self.client.login(username="User1", password="User1")

        response = self.client.get(self.wfs_url, self.query_params)

        # the answer is the restricted one, not the whole layer
        self.assert_feature_collection(response, "4")

    def test_secured_get_feature_of_the_kvp_binding_honours_the_requested_bbox(self):
        # the extent a request asks within is part of the query which is
        # answered: a translation which dropped it answered features which were
        # never asked for (#1155). The box is around Australia, outside of the
        # allowed area of the user, so nothing may match at all
        self.client.login(username="User1", password="User1")

        response = self.client.get(
            self.wfs_url,
            {**self.query_params, "BBOX": "-45,110,-10,180,EPSG:4326"})

        self.assert_feature_collection(response, "0")

    def test_secured_get_feature_of_the_kvp_binding_answers_the_requested_count(self):
        # the paging of the KVP binding belongs to the translated document: the
        # service answers the page it was asked, while how many features match in
        # total it leaves uncomputed for a request which asks a page
        self.client.login(username="User1", password="User1")

        response = self.client.get(
            self.wfs_url,
            {**self.query_params, "COUNT": "2"})

        response_xml = self.assert_feature_collection(response)
        self.assertXpathCount(
            response_xml,
            "/*[local-name()='FeatureCollection']/*[local-name()='member']",
            2)

    def test_secured_get_feature_is_answered_for_every_media_type_of_the_xml_binding(self):
        # DRF matches exactly one media type per parser and answers a type no
        # parser names with UnsupportedMediaType, which the catch-all of the
        # endpoint reported as a missing permission (#1155)
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

        for content_type in ("text/xml", "application/xml",
                             "application/gml+xml; version=3.2"):
            with self.subTest(content_type=content_type):
                response = self.client.post(
                    self.wfs_url,
                    data=get_feature_request.strip(),
                    content_type=content_type
                )

                self.assert_feature_collection(response, "4")

    def test_a_kvp_get_feature_with_an_unreadable_parameter_is_refused_by_name(self):
        # a parameter of the request which cannot be read is a faulty parameter
        # of the client and answers with the report naming it, not with the
        # permissions report of the catch-all (#1155)
        self.client.login(username="User1", password="User1")

        refusals = {
            "FILTER": "NAME = 'Germany'",
            "BBOX": "no,a,bbox,EPSG:4326",
        }
        for locator, value in refusals.items():
            with self.subTest(locator=locator):
                response = self.client.get(
                    self.wfs_url, {**self.query_params, locator: value})

                self.assertEqual(400, response.status_code, response.content)
                exception = etree.fromstring(
                    response.content).find(".//{*}Exception")
                self.assertIsNotNone(exception, response.content)
                self.assertEqual(
                    "InvalidParameterValue", exception.get("exceptionCode"))
                self.assertEqual(locator, exception.get("locator"))
