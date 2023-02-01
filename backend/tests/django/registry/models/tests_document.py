from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from MrMap.settings import BASE_DIR
from ows_lib.xml_mapper.capabilities.wms.wms130 import \
    WebMapService as XmlWebMapService
from registry.models.metadata import Keyword
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
        self.wms: WebMapService = WebMapService.objects.get(
            pk="cd16cc1f-3abb-4625-bb96-fbe80dbe23e3")

        # change service metadata
        self.wms.title = "huhu"
        self.wms.save()

        # change root layer metadata
        self.wms.root_layer.title = "hihi"
        self.wms.root_layer.save()
        self.wms.root_layer.keywords.set(
            Keyword.objects.filter(keyword__contains="ergiebiger Dauerregen"))

        # change a layer metadata in deep
        some_layer: Layer = self.wms.layers.get(identifier="node1.1.1")
        some_layer.title = "hoho"
        some_layer.keywords.set(
            Keyword.objects.filter(keyword__contains="ergiebiger Dauerregen"))
        some_layer.save()

    def test_current_capabilities(self):
        capabilities: XmlWebMapService = self.wms.updated_capabilitites

        # check service metadata
        self.assertEqual("huhu", capabilities.service_metadata.title)

        # check root layer metadata
        self.assertEqual("hihi",
                         capabilities.root_layer.metadata.title)
        self.assertListEqual(
            list(set(["ergiebiger Dauerregen", "extrem ergiebiger Dauerregen"])), list(set(capabilities.root_layer.metadata.keywords)))

        # check a layer metadata in deep
        some_layer = capabilities.get_layer_by_identifier(
            identifier="node1.1.1")
        self.assertEqual("hoho", some_layer.metadata.title)
        self.assertListEqual(
            list(set(["ergiebiger Dauerregen", "extrem ergiebiger Dauerregen"])), list(set(some_layer.metadata.keywords)))

        self.fail(
            msg="complete this test by adding more data changes on on more sub objects.")
