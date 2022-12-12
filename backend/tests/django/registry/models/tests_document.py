from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from MrMap.settings import BASE_DIR
from registry.models.service import WebMapService


def setup_capabilitites_file():
    wms: WebMapService = WebMapService.objects.get(
        pk="1b195589-dcfa-403f-9e66-e7e1c0a67024")

    cap_file = open(
        f"{BASE_DIR}/tests/django/test_data/capabilities/wms/1.0.3.xml", mode="rb")

    wms.xml_backup_file = SimpleUploadedFile(
        'capabilitites.xml', cap_file.read())
    wms.save()

    cap_file.close()


class CapabilitiesDocumentModelMixinTest(TestCase):

    fixtures = ['test_keywords.json', "test_wms.json"]

    def setUp(self):
        setup_capabilitites_file()

    def test_current_capabilities(self):
        wms: WebMapService = WebMapService.objects.get(
            pk="1b195589-dcfa-403f-9e66-e7e1c0a67024")

        # TODO: title, abstract etc. differs from cap file content. So this database content shall be overwrite the values from the cap file
        wms.current_capabilities
        self.assertFalse(True, msg="implement this test")
