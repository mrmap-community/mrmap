from datetime import datetime

from django.test import SimpleTestCase, TestCase
from lxml import etree
from registry.models.service import CatalogueService
from registry.ows_lib.csw.builder import CSWBuilder, CSWCapabilities
from registry.settings import MRMAP_CSW_PK


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
