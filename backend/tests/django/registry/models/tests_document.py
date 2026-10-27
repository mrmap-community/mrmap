from pathlib import Path
from unittest.mock import Mock, PropertyMock, patch
from urllib.parse import parse_qs, urlsplit

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from MrMap.settings import BASE_DIR
from registry.enums.service import HttpMethodEnum, OGCOperationEnum
from registry.models.metadata import Keyword, MimeType
from registry.models.service import (CatalogueService, FeatureType, Layer,
                                     WebFeatureService, WebMapService)
from registry.ows_lib.wfs.wfs import WebFeatureServiceClient
from requests import Response, Session
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
        self.wms.keywords.set(
            Keyword.objects.filter(
                keyword="meteorology"))

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
        some_layer.save()
        some_layer.keywords.set(
            Keyword.objects.filter(
                # this also contains extrem ergiebiger Dauerregen
                keyword__contains="ergiebiger Dauerregen"))

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


class DescribeFeatureTypeDocumentTest(TestCase):
    fixtures = ['test_users.json', 'test_keywords.json', 'test_crs.json', 'test_wfs.json']

    def setUp(self):
        self.feature_type = FeatureType.objects.select_related('service').get(identifier='node2')
        self.operation = self.feature_type.service.operation_urls.create(
            operation=OGCOperationEnum.DESCRIBE_FEATURE_TYPE, method=HttpMethodEnum.GET,
            url='https://example.test/wfs')
        self.session = Mock(spec=Session)
        self.session.prepare_request.side_effect = Session().prepare_request
        capabilities = Path(BASE_DIR, 'tests/django/test_data/capabilities/wfs/2.0.0.xml').read_bytes()
        self.wfs_client = WebFeatureServiceClient(capabilities, session=self.session)
        self.response = Response()
        self.response.status_code = 200
        self.response.headers['Content-Type'] = 'application/xml'
        self.response._content = b'<schema xmlns="http://www.w3.org/2001/XMLSchema"/>'
        self.session.send.return_value = self.response
        client = patch.object(WebFeatureService, 'client', new_callable=PropertyMock,
                              return_value=self.wfs_client)
        client.start()
        self.addCleanup(client.stop)

    def set_formats(self, *values):
        self.operation.mime_types.set([
            MimeType.objects.get_or_create(mime_type=value)[0] for value in values])

    def request_params(self):
        request = self.session.send.call_args.kwargs['request']
        return parse_qs(urlsplit(request.url).query, keep_blank_values=True)

    def test_fetch_uses_one_advertised_xml_format_and_saves(self):
        self.set_formats('application/json', 'application/gml+xml; version=3.2', 'text/xml')
        with patch.object(self.feature_type, 'save', wraps=self.feature_type.save) as save:
            result = self.feature_type.fetch_describe_feature_type_document()
        self.assertEqual(result, self.response.content)
        save.assert_called_once_with()
        params = self.request_params()
        self.assertEqual(params['REQUEST'], ['DescribeFeatureType'])
        self.assertEqual(params['TYPENAMES'], [self.feature_type.identifier])
        self.assertEqual(params['OUTPUTFORMAT'], ['application/gml+xml; version=3.2'])

    def test_fetch_without_save_updates_only_the_instance(self):
        previous = self.feature_type.describe_feature_type_document
        for output_format in ('text/xml; subtype=gml/3.1.1', 'XMLSCHEMA'):
            with self.subTest(output_format=output_format):
                self.set_formats(output_format)
                with patch.object(self.feature_type, 'save') as save:
                    result = self.feature_type.fetch_describe_feature_type_document(save=False)
                self.assertEqual(result, self.response.content)
                self.assertEqual(self.feature_type.describe_feature_type_document, self.response.content)
                save.assert_not_called()
                self.assertEqual(self.request_params()['OUTPUTFORMAT'], [output_format])
                stored = FeatureType.objects.get(pk=self.feature_type.pk)
                self.assertEqual(stored.describe_feature_type_document, previous)

    def test_missing_format_advertisement_uses_protocol_default(self):
        self.feature_type.fetch_describe_feature_type_document(save=False)
        self.assertNotIn('OUTPUTFORMAT', self.request_params())

    def test_get_feature_and_post_only_formats_are_not_used(self):
        xml_format = MimeType.objects.create(mime_type='text/xml')
        self.feature_type.service.operation_urls.filter(
            operation=OGCOperationEnum.GET_FEATURE).first().mime_types.add(xml_format)
        self.feature_type.service.operation_urls.create(
            operation=OGCOperationEnum.DESCRIBE_FEATURE_TYPE, method=HttpMethodEnum.POST,
            url='https://example.test/post').mime_types.add(xml_format)
        self.set_formats('application/json')
        self.feature_type.fetch_describe_feature_type_document(save=False)
        self.assertNotIn('OUTPUTFORMAT', self.request_params())

    def test_unsuccessful_response_does_not_replace_or_save_document(self):
        for status_code, content_type in ((500, 'application/xml'), (200, 'text/html')):
            with self.subTest(status_code=status_code, content_type=content_type):
                self.response.status_code = status_code
                self.response.headers['Content-Type'] = content_type
                self.feature_type.describe_feature_type_document = 'previous schema'
                with patch.object(self.feature_type, 'save') as save:
                    self.assertIsNone(self.feature_type.fetch_describe_feature_type_document())
                save.assert_not_called()
                self.assertEqual(self.feature_type.describe_feature_type_document, 'previous schema')
