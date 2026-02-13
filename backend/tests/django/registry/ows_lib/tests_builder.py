from django.test import TestCase
from lxml import etree
from registry.ows_lib.csw.builder import CSWBuilder


class WebFeatureServiceSecurityManagerTest(TestCase):

    def test_csw_builder(self):
        builder = CSWBuilder()
        capabilities = builder.build_capabilities(
            title="Test CSW SPervice",
            abstract="This is a test CSW service.",
            keywords=["test", "csw", "service"]
        )
        capabilities.getroottree().write("output.xml", encoding="utf-8",
                                         xml_declaration=True, standalone=True, pretty_print=True)
        self.assertIsInstance(capabilities, etree._Element)
