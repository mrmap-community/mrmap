from unittest import skip

from django.test import TestCase
from registry.models.service import WebMapService


class WebMapServiceModelTest(TestCase):

    fixtures = ['test_keywords.json', "test_wms.json"]

    @skip("test which test runs endless")
    def test_get_capabilities_url(self):
        wms: WebMapService = WebMapService.objects.get(
            pk="cd16cc1f-3abb-4625-bb96-fbe80dbe23e3")
        self.assertEqual(wms.get_capabilities_url,
                         "http://example.com/wms?SERVICE=WMS&VERSION=1.3.0&REQUEST=GetCapabilities")
