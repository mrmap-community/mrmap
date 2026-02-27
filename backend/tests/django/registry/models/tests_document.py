from django.core.files.uploadedfile import SimpleUploadedFile
from MrMap.settings import BASE_DIR
from registry.models.metadata import Keyword
from registry.models.service import (CatalogueService, FeatureType, Layer,
                                     WebFeatureService, WebMapService)
from tests.django.contrib import XpathTestCase


class CapabilitiesDocumentModelMixinTest(XpathTestCase):

    fixtures = ['test_users.json', "test_keywords.json", "test_crs.json", "test_wms.json",
                "test_wfs.json", "test_csw.json"]

    def setUpWms(self):
        self.wms: WebMapService = WebMapService.objects.prefetch_whole_service(
        ).get(
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
            Keyword.objects.filter(
                # this also contains extrem ergiebiger Dauerregen
                keyword__contains="ergiebiger Dauerregen"))

        # change a layer metadata in deep
        some_layer: Layer = self.wms.layers.get(identifier="node1.1.1")
        some_layer.title = "hoho"
        some_layer.keywords.set(
            Keyword.objects.filter(
                # this also contains extrem ergiebiger Dauerregen
                keyword__contains="ergiebiger Dauerregen"))
        some_layer.save()

        # refetching again with all annotations..
        self.wms: WebMapService = WebMapService.objects.prefetch_whole_service(
        ).get(
            pk="cd16cc1f-3abb-4625-bb96-fbe80dbe23e3")

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
        some_feature_type.keywords.set(
            Keyword.objects.filter(
                # this also contains extrem ergiebiger Dauerregen
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
        capabilities = self.wms.get_updated_capabilitites()

        # check service metadata
        self.assertXpathValue(
            capabilities,
            "/d:WMS_Capabilities/d:Service/d:Title/text()",
            "huhu")

        self.assertXpathValues(capabilities,
                               "/d:WMS_Capabilities/d:Service/d:KeywordList/d:Keyword",
                               [
                                   "meteorology",
                                   # shall be removed: "climatology"
                               ])

        self.assertXpathCount(
            capabilities, "/d:WMS_Capabilities/d:Capability/d:Request/*", 6)

        # check root layer metadata
        self.assertXpathValue(
            capabilities,
            "/d:WMS_Capabilities/d:Capability/d:Layer/d:Title/text()",
            "hihi")
        self.assertXpathValue(
            capabilities,
            "/d:WMS_Capabilities/d:Capability/d:Layer/text()",
            "",
            strip_result=True)
        self.assertXpathValues(capabilities,
                               "/d:WMS_Capabilities/d:Capability/d:Layer/d:KeywordList/d:Keyword",
                               ["ergiebiger Dauerregen", "extrem ergiebiger Dauerregen"])

        # check a layer metadata in deep
        self.assertXpathValue(
            capabilities,
            "/d:WMS_Capabilities/d:Capability//d:Layer[d:Name='node1.1.1']/d:Title/text()",
            "hoho")
        self.assertXpathValues(capabilities,
                               "/d:WMS_Capabilities/d:Capability//d:Layer[d:Name='node1.1.1']/d:KeywordList/d:Keyword",
                               ["ergiebiger Dauerregen", "extrem ergiebiger Dauerregen"])
        self.assertXpathCount(
            capabilities,
            "/d:WMS_Capabilities/d:Capability/d:Layer/d:Layer",
            3)
        self.assertXpathCount(
            capabilities,
            "/d:WMS_Capabilities/d:Capability//d:Layer[d:Name='node1.1.2']",
            1)

    def test_current_capabilitites_of_wfs(self):
        capabilities = self.wfs.get_updated_capabilitites()

        # check service operation urls
        self.assertXpathCount(
            capabilities,
            "/wfs:WFS_Capabilities/ows:OperationsMetadata//ows:Operation",
            11)

        # check service metadata
        self.assertXpathValue(
            capabilities,
            "/wfs:WFS_Capabilities/ows:ServiceIdentification/ows:Title/text()",
            "huhu")

        # check a feature type metadata
        self.assertXpathValue(
            capabilities,
            "/wfs:WFS_Capabilities/wfs:FeatureTypeList/wfs:FeatureType[wfs:Name='node2']/wfs:Title/text()",
            "hoho")

        self.assertXpathValues(capabilities,
                               "/wfs:WFS_Capabilities/wfs:FeatureTypeList/wfs:FeatureType[wfs:Name='node2']/ows:Keywords/ows:Keyword",
                               ["ergiebiger Dauerregen", "extrem ergiebiger Dauerregen"])

        self.assertXpathCount(
            capabilities,
            "/wfs:WFS_Capabilities/wfs:FeatureTypeList//wfs:FeatureType",
            4)

    def test_current_capabilitites_of_csw(self):
        capabilities = self.csw.get_updated_capabilitites()

        # check service operation urls
        self.assertXpathCount(
            capabilities,
            "/csw:Capabilities/ows:OperationsMetadata//ows:Operation",
            6)

        # check service metadata
        self.assertXpathValue(
            capabilities,
            "/csw:Capabilities/ows:ServiceIdentification/ows:Title/text()",
            "huhu")
        # TODO: check other metadata too (keywords, etc..)
