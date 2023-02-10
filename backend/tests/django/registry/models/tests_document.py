from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from MrMap.settings import BASE_DIR
from ows_lib.xml_mapper.capabilities.csw.csw202 import \
    CatalogueService as XmlCatalogueService
from ows_lib.xml_mapper.capabilities.wfs.wfs200 import \
    WebFeatureService as XmlWebFeatureService
from ows_lib.xml_mapper.capabilities.wms.wms130 import \
    WebMapService as XmlWebMapService
from registry.models.metadata import Keyword
from registry.models.service import (CatalogueService, FeatureType, Layer,
                                     WebFeatureService, WebMapService)


class CapabilitiesDocumentModelMixinTest(TestCase):

    fixtures = ["test_keywords.json", "test_wms.json",
                "test_wfs.json", "test_csw.json"]

    def setUpWms(self):
        self.wms: WebMapService = WebMapService.objects.get(
            pk="cd16cc1f-3abb-4625-bb96-fbe80dbe23e3")
        cap_file = open(
            f"{BASE_DIR}/tests/django/test_data/capabilities/wms/fixture_1.3.0.xml", mode="rb")

        self.wms.xml_backup_file = SimpleUploadedFile(
            'capabilitites.xml', cap_file.read())
        self.wms.save()

        cap_file.close()

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

    def setUpWfs(self):
        self.wfs: WebFeatureService = WebFeatureService.objects.get(
            pk="9cc4889d-0cd4-4c3b-8975-58de6d30db41")

        cap_file = open(
            f"{BASE_DIR}/tests/django/test_data/capabilities/wfs/fixture_2.0.0.xml", mode="rb")

        self.wfs.xml_backup_file = SimpleUploadedFile(
            'capabilitites.xml', cap_file.read())
        self.wfs.save()

        cap_file.close()

        # change service metadata
        self.wfs.title = "huhu"
        self.wfs.save()

        # change some feature type
        some_feature_type: FeatureType = FeatureType.objects.get(
            identifier="node2")
        some_feature_type.title = "hoho"
        some_feature_type.keywords.set(Keyword.objects.filter(
            keyword__contains="ergiebiger Dauerregen"))
        some_feature_type.save()

    def setUpCsw(self):
        self.csw: CatalogueService = CatalogueService.objects.get(
            pk="3df586c6-b89b-4ce5-980a-12dc3ca23df2"
        )

        cap_file = open(
            f"{BASE_DIR}/tests/django/test_data/capabilities/csw/2.0.2.xml", mode="rb")

        self.csw.xml_backup_file = SimpleUploadedFile(
            'capabilitites.xml', cap_file.read())
        self.csw.save()
        cap_file.close()

        self.csw.title = "huhu"
        self.wfs.save()

    def setUp(self):
        self.setUpWms()
        self.setUpWfs()
        self.setUpCsw()

    def test_current_capabilities_of_wms(self):
        capabilities: XmlWebMapService = self.wms.updated_capabilitites

        # check service operation urls
        self.assertEqual(3, len(capabilities.operation_urls))
        self.assertEqual("http://example.com/wms?",
                         capabilities.get_operation_url_by_name_and_method("GetMap", "Get").url)

        # check service metadata
        self.assertEqual("huhu", capabilities.title)

        # check root layer metadata
        self.assertEqual("hihi",
                         capabilities.root_layer.title)
        self.assertListEqual(
            list(set(["ergiebiger Dauerregen", "extrem ergiebiger Dauerregen"])), list(set(capabilities.root_layer.keywords)))

        # check a layer metadata in deep
        some_layer = capabilities.get_layer_by_identifier(
            identifier="node1.1.1")
        self.assertEqual("hoho", some_layer.title)
        self.assertListEqual(
            list(set(["ergiebiger Dauerregen", "extrem ergiebiger Dauerregen"])), list(set(some_layer.keywords)))

        self.assertEqual(7, len(capabilities._layers),
                         msg="only 7 layers are active.")
        self.assertIsNone(
            capabilities.get_layer_by_identifier(identifier="node1.1.2"))

    def test_current_capabilitites_of_wfs(self):
        capabilities: XmlWebFeatureService = self.wfs.updated_capabilitites

        # check service operation urls
        self.assertEqual(1, len(capabilities.operation_urls))
        self.assertEqual("http://example.com/wfs?",
                         capabilities.get_operation_url_by_name_and_method("GetFeature", "Get").url)

        # check service metadata
        self.assertEqual("huhu", capabilities.title)

        # check a feature type metadata
        some_feature_type = capabilities.get_feature_type_by_identifier(
            identifier="node2")
        self.assertEqual("hoho", some_feature_type.title)
        self.assertListEqual(
            list(set(["ergiebiger Dauerregen", "extrem ergiebiger Dauerregen"])), list(set(some_feature_type.keywords)))

        self.assertEqual(3, len(capabilities.feature_types),
                         msg="only 3 feature types are active.")

    def test_current_capabilitites_of_csw(self):
        capabilities: XmlCatalogueService = self.csw.updated_capabilitites

        # check service operation urls
        self.assertEqual(2, len(capabilities.operation_urls))
        self.assertEqual("http://example.com/wms?",
                         capabilities.get_operation_url_by_name_and_method("GetCapabilities", "Get").url)

        # check service metadata
        self.assertEqual("huhu", capabilities.title)
