from datetime import datetime

from django.test import SimpleTestCase, TestCase
from lxml import etree
from registry.models.service import CatalogueService
from registry.ows_lib.csw.builder import CSWBuilder, CSWCapabilities
from registry.ows_lib.xml.builder import XSDSkeletonBuilder
from registry.ows_lib.xml.consts import NAMESPACE_LOOKUP
from registry.settings import MRMAP_CSW_PK

CSW_NS = NAMESPACE_LOOKUP["csw_2_0_2"]
OGC_NS = NAMESPACE_LOOKUP["ogc"]
GML_NS = NAMESPACE_LOOKUP["gml_3_1_1"]


class CSWBuilderTest(TestCase):
    fixtures = [
        'test_users.json',
        'test_keywords.json',
        'test_csw.json'
    ]

    def test_csw_builder(self):
        csw = CatalogueService.objects.get(
            pk=MRMAP_CSW_PK
        )

        builder = CSWCapabilities(
            csw,
            extra_keywords=["test_keyword_1", "test_keyword_2"],
            operation_parameters={
                "GetRecords": {
                    "CONSTRAINTLANGUAGE": ["FILTER", "CQL_TEXT"],
                    "outputSchema": ["http://www.isotc211.org/2005/gmd"],
                    "outputFormat": ["application/xml"],
                    "ElementSetName": ["full"],
                    "resultType": ["results", "hits", "validate"],
                    "typeNames": ["gmd:MD_Metadata"],
                }
            },
            filter_capabilities={
                "Spatial_Capabilities": {
                    "GeometryOperands": [
                        {
                            "name": "GeometryOperand",
                            "text": "gml:Point"
                        },
                        {
                            "name": "GeometryOperand",
                            "text": "gml:LineString"
                        },
                        {
                            "name": "GeometryOperand",
                            "text": "gml:Polygon"
                        }
                    ],
                    "SpatialOperators": [
                        {
                            "name": "SpatialOperator",
                            "_name": "BBOX"
                        },
                        {
                            "name": "SpatialOperator",
                            "_name": "Contains"
                        },
                        {
                            "name": "SpatialOperator",
                            "_name": "Crosses"
                        },
                        {
                            "name": "SpatialOperator",
                            "_name": "Disjoint"
                        },
                        {
                            "name": "SpatialOperator",
                            "_name": "Equals"
                        },
                        {
                            "name": "SpatialOperator",
                            "_name": "Intersects"
                        },
                        {
                            "name": "SpatialOperator",
                            "_name": "Overlaps"
                        },
                        {
                            "name": "SpatialOperator",
                            "_name": "Touches"
                        },
                        {
                            "name": "SpatialOperator",
                            "_name": "Within"
                        }
                    ],
                },
                "Scalar_Capabilities": {
                    "LogicalOperators": [
                        {
                            "name": "LogicalOperator",
                            "text": "AND"
                        },
                        {
                            "name": "LogicalOperator",
                            "text": "OR"
                        },
                        {
                            "name": "LogicalOperator",
                            "text": "NOT"
                        }
                    ],

                    "ComparisonOperators": [
                        {
                            "name": "ComparisonOperator",
                            "text": "EqualTo"
                        },
                        {
                            "name": "ComparisonOperator",
                            "text": "NotEqualTo"
                        },
                        {
                            "name": "ComparisonOperator",
                            "text": "LessThan"
                        },
                        {
                            "name": "ComparisonOperator",
                            "text": "GreaterThan"
                        },
                        {
                            "name": "ComparisonOperator",
                            "text": "LessThanEqualTo"
                        },
                        {
                            "name": "ComparisonOperator",
                            "text": "GreaterThanEqualTo"
                        }
                    ]
                }
            }
        )
        capabilities = builder.to_xml()

        self.assertIsInstance(capabilities, etree._Element)


class CswAcknowledgementBuilderTest(SimpleTestCase):
    def test_acknowledgement_has_one_echo_and_the_schema_timestamp(self):
        timestamp = datetime(2026, 10, 27, 10, 0, 0)
        request = etree.fromstring(b'<GetRecords xmlns="http://www.opengis.net/cat/csw/2.0.2"/>')
        root = CSWBuilder().build_acknowledgement(
            timestamp=timestamp, request_id='urn:uuid:test', echoed_request=request)
        self.assertEqual(root.get('timeStamp'), timestamp.isoformat())
        self.assertEqual(len(root.findall('{*}EchoedRequest')), 1)
        self.assertEqual(list(root.find('{*}EchoedRequest')), [request])
        self.assertEqual(root.findtext('{*}RequestId'), 'urn:uuid:test')
        self.assertEqual([etree.QName(child).localname for child in root], ['EchoedRequest', 'RequestId'])


class CswGetRecordsViewTest(TestCase):
    def test_validate_acknowledges_and_echoes_the_request(self):
        response = self.client.get('/csw', {
            'SERVICE': 'CSW', 'VERSION': '2.0.2', 'REQUEST': 'GetRecords',
            'typeNames': 'gmd:MD_Metadata', 'resultType': 'validate',
        })

        self.assertEqual(response.status_code, 200)
        root = etree.fromstring(response.content)
        self.assertEqual(root.tag, '{http://www.opengis.net/cat/csw/2.0.2}Acknowledgement')
        self.assertIsInstance(datetime.fromisoformat(root.get('timeStamp')), datetime)
        self.assertNotIn('timestamp', root.attrib)
        self.assertEqual(len(root.findall('{*}EchoedRequest')), 1)
        echoed = root.find('{*}EchoedRequest/{*}GetRecords')
        self.assertIsNotNone(echoed)
        self.assertEqual(echoed.get('resultType'), 'validate')

    def test_hits_and_results_still_return_search_results(self):
        for result_type in ('hits', 'results'):
            with self.subTest(result_type=result_type):
                response = self.client.get('/csw', {
                    'SERVICE': 'CSW', 'VERSION': '2.0.2', 'REQUEST': 'GetRecords',
                    'typeNames': 'gmd:MD_Metadata', 'resultType': result_type,
                })
                self.assertEqual(response.status_code, 200)
                root = etree.fromstring(response.content)
                self.assertEqual(root.tag, '{http://www.opengis.net/cat/csw/2.0.2}GetRecordsResponse')
                self.assertEqual(root.find('{*}SearchResults').get('numberOfRecordsMatched'), '0')


class CswAcknowledgementEchoTest(TestCase):
    """the echoed request carries its attributes as attributes (#866)"""

    def test_validate_echoes_a_query_naming_its_type_names(self):
        # the KVP request is synthesized by this very builder, so the echo of
        # a validate response shows exactly what the synthesis writes: until
        # #866 the Query carried attributes="{'typeNames': ...}" -- the repr of
        # a dict passed as one keyword -- instead of the typeNames attribute
        response = self.client.get('/csw', {
            'SERVICE': 'CSW', 'VERSION': '2.0.2', 'REQUEST': 'GetRecords',
            'typeNames': 'gmd:MD_Metadata', 'resultType': 'validate',
            'CONSTRAINTLANGUAGE': 'CQL_TEXT',
            'Constraint': "AnyText = 'niederschlag'",
            'sortby': 'title:A',
        })
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(b"attributes=", response.content, response.content)

        echoed = etree.fromstring(response.content).find(
            '{*}EchoedRequest/{*}GetRecords')
        query = echoed.find(f'{{{CSW_NS}}}Query')
        self.assertEqual(query.get('typeNames'), 'gmd:MD_Metadata')
        self.assertIsNone(query.get('attributes'))
        constraint = query.find(f'{{{CSW_NS}}}Constraint')
        self.assertEqual(constraint.get('version'), '1.1.0')


class CswRequestAttributesTest(SimpleTestCase):
    """the five request children which passed their attributes as a dict (#866)"""

    def test_query_names_its_type_names(self):
        root = CSWBuilder().build_get_records(
            type_names=('csw:Record', 'gmd:MD_Metadata'))
        query = root.find(f'{{{CSW_NS}}}Query')
        self.assertEqual(query.get('typeNames'), 'csw:Record gmd:MD_Metadata')

    def test_cql_constraint_names_its_version(self):
        root = CSWBuilder().build_get_records(
            constraint="AnyText = 'x'", constraint_language='CQL_TEXT')
        constraint = root.find(f'.//{{{CSW_NS}}}Constraint')
        self.assertEqual(constraint.get('version'), '1.1.0')
        self.assertEqual(constraint.find(f'{{{CSW_NS}}}CqlText').text,
                         "AnyText = 'x'")

    def test_fes_constraint_names_its_version(self):
        # a harvested CSW request asks its filter through this constraint --
        # without the version attribute no server can tell which filter
        # profile is asked of it
        root = CSWBuilder().build_get_records(
            constraint='<Filter/>', constraint_language='FILTER')
        constraint = root.find(f'.//{{{CSW_NS}}}Constraint')
        self.assertEqual(constraint.get('version'), '1.1.0')
        self.assertIsNotNone(constraint.find(f'{{{OGC_NS}}}Filter'))

    def test_bbox_constraint_and_envelope_name_their_version_and_crs(self):
        builder = CSWBuilder()
        root = builder.build_get_records()
        builder.add_bbox_constraint(
            root.find(f'{{{CSW_NS}}}Query'), '5.0,46.0,16.0,56.0')
        constraint = root.find(f'.//{{{CSW_NS}}}Constraint')
        self.assertEqual(constraint.get('version'), '1.1.0')
        envelope = root.find(f'.//{{{GML_NS}}}Envelope')
        self.assertEqual(envelope.get('srsName'), 'EPSG:4326')
        self.assertEqual(envelope.findtext(f'{{{GML_NS}}}lowerCorner'),
                         '5.0 46.0')

    def test_no_built_request_carries_an_attributes_attribute(self):
        # the assertion the issue asks for: the string is what makes the
        # finding invisible in a response nobody read
        cql_builder = CSWBuilder()
        cql = cql_builder.build_get_records(
            type_names=('csw:Record',),
            constraint="AnyText = 'x'", constraint_language='CQL_TEXT',
            sort_by=[('dc:title', 'ASC')])
        bbox_builder = CSWBuilder()
        bbox = bbox_builder.build_get_records()
        bbox_builder.add_bbox_constraint(
            bbox.find(f'{{{CSW_NS}}}Query'), '1.0,2.0,3.0,4.0')
        requests = (
            cql,
            bbox,
            CSWBuilder().build_get_records(
                constraint='<Filter/>', constraint_language='FILTER'),
            CSWBuilder().build_get_record_by_id(ids=['urn:uuid:test']),
        )
        for root in requests:
            with self.subTest(request=etree.QName(root).localname):
                self.assertNotIn('attributes=',
                                 etree.tostring(root).decode())


class XSDSkeletonShapeTest(SimpleTestCase):
    """a skeleton which cannot carry the report says so instead of answering empty (#866)"""

    def test_the_ows_exception_skeleton_declares_no_service_exception_report(self):
        # this is the key mismatch behind the empty report of the issue: the
        # ("csw", "Exception", "2.0.2") skeleton is an OWS ExceptionReport and
        # knows no element of the WMS ServiceExceptionReport spelling
        builder = XSDSkeletonBuilder(('csw', 'Exception', '2.0.2'))
        self.assertTrue(builder.declares_element('ExceptionReport'))
        self.assertFalse(builder.declares_element('ServiceExceptionReport'))

    def test_building_a_root_the_schema_declares_still_builds(self):
        report = XSDSkeletonBuilder(
            ('wms', 'Exception', '1.3.0')).build_element(
                'ServiceExceptionReport', attributes={'version': '1.3.0'})
        self.assertEqual(
            etree.QName(report).localname, 'ServiceExceptionReport')
        self.assertEqual(report.get('version'), '1.3.0')

    def test_building_an_undeclared_root_names_the_schema(self):
        # before #866 this answered the childless root -- the empty report a
        # client cannot tell apart from no response at all
        builder = XSDSkeletonBuilder(('csw', 'Exception', '2.0.2'))
        with self.assertRaises(ValueError) as refused:
            builder.build_element('ServiceExceptionReport')
        self.assertIn('owsExceptionReport.xsd', str(refused.exception))
        self.assertIn('ServiceExceptionReport', str(refused.exception))
