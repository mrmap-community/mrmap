from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from MrMap.settings import BASE_DIR
from ows_lib.xml_mapper.capabilities.wms.wms130 import \
    WebMapService as XmlWebMapService
from registry.models.service import Layer, WebMapService


def setup_capabilitites_file():
    wms: WebMapService = WebMapService.objects.get(
        pk="cd16cc1f-3abb-4625-bb96-fbe80dbe23e3")

    cap_file = open(
        f"{BASE_DIR}/tests/django/test_data/capabilities/wms/fixture_1.3.0.xml", mode="rb")

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
            pk="cd16cc1f-3abb-4625-bb96-fbe80dbe23e3")

        wms.title = "huhu"
        wms.save()

        wms.root_layer.title = "hihi"
        wms.root_layer.save()

        some_layer: Layer = wms.layers.get(identifier="node1.1.1")
        some_layer.title = "hoho"
        some_layer.save()

        capabilities: XmlWebMapService = wms.updated_capabilitites

        self.assertEqual("huhu", capabilities.service_metadata.title)
        self.assertEqual("hihi",
                         capabilities.root_layer.metadata.title)
        self.assertEqual("hoho", capabilities.get_layer_by_identifier(
            identifier="node1.1.1").metadata.title)

        self.fail(
            msg="complete this test by adding more data changes on on more sub objects.")
