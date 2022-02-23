from django.test import TestCase
from registry.models.background import BackgroundProcess


class BackgroundProcessModelTest(TestCase):

    fixtures = ['test_background.json']

    def test_background_process(self):
        process: BackgroundProcess = BackgroundProcess.objects.get(
            pk="cd16cc1f-3abb-4625-bb96-fbe80dbe23e3")
        self.assertEqual(wms.get_capabilities_url,
                         "http://example.com/wms?SERVICE=WMS&VERSION=1.3.0&REQUEST=GetCapabilities")
