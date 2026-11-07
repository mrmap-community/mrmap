from django.contrib.gis.geos import GEOSGeometry, Polygon
from django.test import RequestFactory, SimpleTestCase
from epsg_cache.utils import adjust_axis_order, get_epsg_srid
from lxml import etree
from registry.ows_lib.client.exceptions import (InvalidFilterParam,
                                                InvalidPagingParam)
from registry.ows_lib.request.ogc_request import OGCRequest
from registry.ows_lib.xml.consts import NAMESPACE_LOOKUP
from registry.ows_lib.wfs.xml_builder import WFSBuilder

WFS_NS = NAMESPACE_LOOKUP["wfs_2_0_0"]
FES_NS = NAMESPACE_LOOKUP["fes_2_0"]
GML_NS = NAMESPACE_LOOKUP["gml_3_2_2"]

NAMESPACES = {"wfs": WFS_NS, "fes": FES_NS, "gml": GML_NS}

# a selection clause of the Filter 2.0 profile, spelled with the prefix the
# filter itself declares
FILTER = (
    '<fes:Filter xmlns:fes="%s">'
    '<fes:PropertyIsEqualTo><fes:ValueReference>NAME</fes:ValueReference>'
    '<fes:Literal>Germany</fes:Literal></fes:PropertyIsEqualTo>'
    '</fes:Filter>' % FES_NS
)


class KVPGetFeatureRequestTest(SimpleTestCase):
    """The key value pairing binding of a GetFeature as the request class reads it.

    The proxy secures the request *document*, so everything the KVP encoding
    spells within its parameters has to be found in that document: a parameter
    the translation lost was answered anyway (#1155).
    """

    def kv_get(self, **params) -> OGCRequest:
        query = {
            "SERVICE": "WFS",
            "REQUEST": "GetFeature",
            "VERSION": "2.0.0",
            "TYPENAMES": "ms:Countries",
        }
        query.update(params)
        return OGCRequest.from_django_request(
            RequestFactory().get("/mrmap-proxy/wfs/73cf78c9", query))

    def queries(self, ogc_request):
        return ogc_request.xml_request.xpath("./wfs:Query",
                                             namespaces=NAMESPACES)

    def test_the_kvp_binding_is_translated_into_a_request_document(self):
        ogc_request = self.kv_get()

        document = ogc_request.xml_request
        self.assertIsNotNone(document)
        self.assertEqual("{%s}GetFeature" % WFS_NS, document.tag)
        self.assertEqual("WFS", document.get("service"))
        self.assertEqual("2.0.0", document.get("version"))
        # the document is what the proxy forwards, so it has to carry the
        # feature type the parameters asked
        self.assertXpathCount(
            document, "./wfs:Query[@typeNames='ms:Countries']", 1)
        self.assertIn(b'typeNames="ms:Countries"', ogc_request.content)

    def test_the_presentation_and_paging_parameters_reach_the_document(self):
        ogc_request = self.kv_get(
            OUTPUTFORMAT="application/json",
            COUNT="7",
            startIndex="3",
            SRSNAME="EPSG:25832",
        )

        document = ogc_request.xml_request
        self.assertEqual("application/json", document.get("outputFormat"))
        self.assertEqual("7", document.get("count"))
        self.assertEqual("3", document.get("startIndex"))
        self.assertEqual(
            "EPSG:25832", self.queries(ogc_request)[0].get("srsName"))

    def test_MAXFEATURES_becomes_the_count_of_the_document(self):
        # WFS 2.0 spells the limit of answered features "count"; the 1.x
        # spelling of a client is translated, not answered as an attribute the
        # 2.0 schema of the document does not know
        document = self.kv_get(MAXFEATURES="5").xml_request
        self.assertEqual("5", document.get("count"))
        self.assertIsNone(document.get("maxFeatures"))

        document = self.kv_get(MAXFEATURES="5", COUNT="7").xml_request
        self.assertEqual("7", document.get("count"))

    def test_the_filter_reaches_every_requested_feature_type(self):
        # one element has one parent: the filter of a request which asks several
        # feature types was answered for the last one alone
        ogc_request = self.kv_get(
            TYPENAMES="ms:Countries,ms:Rivers", FILTER=FILTER)

        queries = self.queries(ogc_request)
        self.assertEqual(2, len(queries))
        for query in queries:
            literals = query.xpath(
                "./fes:Filter//fes:Literal/text()", namespaces=NAMESPACES)
            self.assertEqual(["Germany"], literals,
                             etree.tostring(query))

    def test_a_filter_which_is_no_document_is_refused(self):
        ogc_request = self.kv_get(FILTER="NAME = 'Germany'")

        with self.assertRaises(InvalidFilterParam):
            ogc_request.xml_request

    def test_a_paging_parameter_which_is_no_integer_is_refused(self):
        ogc_request = self.kv_get(COUNT="seven")

        with self.assertRaises(InvalidPagingParam) as raised:
            ogc_request.xml_request
        self.assertEqual("COUNT", raised.exception.param)

    def test_a_parameter_present_without_a_value_asks_nothing(self):
        # #1154 keeps a whitelisted parameter which the request names with an
        # empty value, so the translation has to hear such a parameter as "asks
        # nothing": as a faulty parameter it would refuse the request of every
        # standard client, as an extent it would answer no feature at all
        ogc_request = self.kv_get(BBOX="", COUNT="", startIndex="", FILTER="")

        self.assertEqual("", ogc_request.ogc_query_params.get("BBOX"))
        self.assertEqual("", ogc_request.ogc_query_params.get("COUNT"))

        document = ogc_request.xml_request
        # a parameter named without a value has to answer the same document as a
        # parameter not named at all; the schema stamps its own default onto
        # startIndex, so the paging is compared against the request naming none
        unnamed = self.kv_get().xml_request
        paging = ("count", "startIndex")
        self.assertEqual(
            {key: unnamed.get(key) for key in paging},
            {key: document.get(key) for key in paging},
            etree.tostring(document))
        self.assertXpathCount(document, "./wfs:Query/fes:Filter", 0)

        exception = ogc_request.secure_get_feature_request([{
            "type_name": "ms:Countries",
            "geometry_property_name": "ms:Geometry",
            "allowed_area_union": Polygon(((0, 0), (0, 10), (10, 10),
                                           (10, 0), (0, 0)), srid=4326),
        }])
        self.assertIsNone(exception)

        # the allowed area is applied; the extent which asks nothing is not
        # ANDed on the query as a restriction answering nothing
        self.assertXpathCount(
            ogc_request.xml_request, "./wfs:Query/fes:Filter//fes:Within", 1)
        self.assertXpathCount(
            ogc_request.xml_request,
            "./wfs:Query/fes:Filter//fes:Intersects", 0)

    def test_the_bbox_of_a_wfs_request_is_read(self):
        # the parameters are collected under the spelling of the request class,
        # which the bbox helper of the WFS used not to find (#1155)
        bbox = self.kv_get(BBOX="-90,-180,90,180,EPSG:4326").bbox
        self.assertFalse(bbox.empty)
        self.assertEqual(4326, bbox.srid)
        self.assertEqual((-180.0, -90.0, 180.0, 90.0),
                         tuple(round(value) for value in bbox.extent))

        # a bbox naming its own crs is read in that crs and in its axis order
        bbox = self.kv_get(
            BBOX="5900000,2100000,6200000,2400000,EPSG:25832").bbox
        self.assertFalse(bbox.empty)
        self.assertEqual(25832, bbox.srid)
        self.assertEqual((5900000.0, 2100000.0, 6200000.0, 2400000.0),
                         tuple(bbox.extent))

    def test_the_secured_document_carries_allowed_area_and_requested_extent(self):
        allowed_area = Polygon(((0, 0), (0, 10), (10, 10), (10, 0), (0, 0)),
                               srid=4326)
        ogc_request = self.kv_get(
            FILTER=FILTER, BBOX="-45,110,-10,180,EPSG:4326")

        exception = ogc_request.secure_get_feature_request([{
            "type_name": "ms:Countries",
            "geometry_property_name": "ms:Geometry",
            "allowed_area_union": allowed_area,
        }])
        self.assertIsNone(exception)

        # the query keeps what the client asked and is restricted by the allowed
        # area and by the extent of the request itself
        self.assertXpathCount(
            ogc_request.xml_request,
            "./wfs:Query/fes:Filter", 1)
        for operator in ("PropertyIsEqualTo", "Within", "Intersects"):
            self.assertXpathCount(
                ogc_request.xml_request,
                "./wfs:Query/fes:Filter//fes:%s" % operator, 1)
        self.assertXpathValues(
            ogc_request.xml_request,
            "./wfs:Query/fes:Filter//fes:Within/fes:ValueReference | "
            "./wfs:Query/fes:Filter//fes:Intersects/fes:ValueReference",
            ["ms:Geometry", "ms:Geometry"])

        self.assertGeometry(
            ogc_request.xml_request, "Within", (0.0, 0.0, 10.0, 10.0), 4326)
        self.assertGeometry(
            ogc_request.xml_request, "Intersects",
            (110.0, -45.0, 180.0, -10.0), 4326)

    def test_a_securing_without_a_request_document_is_refused(self):
        # a request which answers no document to restrict is refused by name; the
        # permissions report of the endpoints catch-all tells nothing about it
        ogc_request = self.kv_get()
        ogc_request.method = "OPTIONS"
        ogc_request.operation = "GetFeature"

        report = ogc_request.secure_get_feature_request([])

        self.assertIsNotNone(report)
        self.assertIn(b"ParsingError", report.content)

    def assertGeometry(self, document, operator, extent, srid):
        """The geometry an operator of the secured document carries.

        Read the way the response of the service is read: the GML of the filter
        is written in the axis order its crs names, so it is adjusted back
        before its corners are compared.
        """
        operators = document.xpath(
            "./wfs:Query/fes:Filter//fes:%s" % operator, namespaces=NAMESPACES)
        self.assertEqual(1, len(operators), etree.tostring(document))

        geometry_element = next(
            child for child in operators[0]
            if isinstance(child.tag, str)
            and etree.QName(child).namespace == GML_NS)
        if geometry_element.get("srsName"):
            self.assertEqual(
                srid,
                int(get_epsg_srid(geometry_element.get("srsName"))[1]),
                geometry_element.get("srsName"))

        geometry = GEOSGeometry.from_gml(etree.tostring(geometry_element))
        geometry.srid = srid
        geometry = adjust_axis_order(geometry)
        self.assertEqual(extent, tuple(round(value, 6)
                                       for value in geometry.extent))

    def assertXpathCount(self, tree, xpath, expected_count):
        found = tree.xpath(xpath, namespaces=NAMESPACES)
        self.assertEqual(
            expected_count, len(found),
            "xpath %s found %s of %s" % (
                xpath, len(found), etree.tostring(tree)))

    def assertXpathValues(self, tree, xpath, expected):
        found = tree.xpath(xpath, namespaces=NAMESPACES)
        self.assertEqual([value.text for value in found], expected,
                         etree.tostring(tree))


class WFSBuilderTest(SimpleTestCase):
    """The document builder of a GetFeature answers the parameters it is given."""

    def test_the_document_carries_every_attribute_of_the_request(self):
        builder = WFSBuilder(service_version="2.0.0")

        document = builder.build_get_feature(
            ["ms:Countries"],
            srs_name="EPSG:25832",
            output_format="application/json",
            count=7,
            start_index=3,
        )

        self.assertEqual("application/json", document.get("outputFormat"))
        self.assertEqual("7", document.get("count"))
        self.assertEqual("3", document.get("startIndex"))
        self.assertEqual("EPSG:25832", document.find(
            "{%s}Query" % WFS_NS).get("srsName"))

    def test_an_unanswered_parameter_is_left_out_of_the_document(self):
        # a parameter the request does not name is not carried, not even empty
        document = WFSBuilder(service_version="2.0.0").build_get_feature(
            ["ms:Countries"])

        self.assertIsNone(document.get("count"))
        self.assertNotIn("", document.attrib.values())
