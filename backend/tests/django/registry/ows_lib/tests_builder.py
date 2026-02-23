from django.test import TestCase
from lxml import etree
from registry.models.service import CatalogueService
from registry.ows_lib.csw.builder import CSWCapabilities


class CSWBuilderTest(TestCase):
    fixtures = ['test_users.json', 'test_keywords.json', 'test_csw.json']

    def test_csw_builder(self):
        csw = CatalogueService.objects.get(
            pk="9cc4889d-0cd4-4c3b-8975-58de6d30db41")

        builder = CSWCapabilities(csw)
        capabilities = builder.to_xml()

        capabilities.getroottree().write("output.xml", encoding="utf-8",
                                         xml_declaration=True, standalone=True, pretty_print=True)
        self.assertIsInstance(capabilities, etree._Element)
        self.assertIsInstance(capabilities, etree._Element)
