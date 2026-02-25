from django.test import TransactionTestCase
from lxml import etree
from registry.models.service import CatalogueService
from registry.ows_lib.csw.builder import CSWCapabilities
from registry.settings import MRMAP_CSW_PK


class CSWBuilderTest(TransactionTestCase):
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

        capabilities.getroottree().write(
            "output.xml",
            encoding="utf-8",
            xml_declaration=True,
            standalone=True,
            pretty_print=True
        )
        self.assertIsInstance(capabilities, etree._Element)
