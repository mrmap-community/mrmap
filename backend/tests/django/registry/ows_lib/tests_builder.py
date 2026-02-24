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
            extra_keywords=["test_keyword_1", "test_keyword_2"]
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
