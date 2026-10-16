import base64
import json
from io import BytesIO
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.contrib.gis.geos import MultiPolygon, Polygon
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, TestCase, override_settings
from guardian.shortcuts import assign_perm
from lxml import etree
from PIL import Image
from registry.helper.preview import (FEATURE_LIMIT, PreviewError, PreviewSession,
                                     checked_bbox, registered_previews,
                                     validate_features)
from registry.models.harvest import HarvestedMetadataRelation, HarvestingJob
from registry.models.metadata import DatasetMetadataRecord, MetadataRelation
from registry.models.security import AllowedWebFeatureServiceOperation, AllowedWebMapServiceOperation
from registry.models.service import CatalogueService, WebFeatureService, WebMapService
from registry.models.update import WebMapServiceUpdateJob
from registry.ows_lib.request.ogc_request import OGCRequest
from registry.proxy.mixins import OgcServiceProxyView
from requests import Request, Response, Session
from rest_framework.test import APIClient

WMS = 'cd16cc1f-3abb-4625-bb96-fbe80dbe23e3'
WFS = '73cf78c9-6605-47fd-ac4f-1be59265df65'
CSW = '9cc4889d-0cd4-4c3b-8975-58de6d30db41'


def response(content, content_type='application/json', status=200):
    result = Response()
    result.status_code = status
    result._content = content
    result._content_consumed = True
    result.headers['Content-Type'] = content_type
    result.url = 'https://registered.example/data'
    return result


def capabilities(protocol, version='2.0.0'):
    if protocol == 'WMS':
        return f'''<WMS_Capabilities version="{version}"><Capability><Request>
          <GetMap><Format>image/png</Format></GetMap>
          <GetFeatureInfo><Format>text/html</Format><Format>text/plain; charset=utf-8</Format></GetFeatureInfo></Request>
          <Layer><CRS>EPSG:4326</CRS><SRS>EPSG:4326</SRS><Name>node1</Name>
          <Layer><Name>node1.1</Name></Layer></Layer></Capability></WMS_Capabilities>'''.encode()
    operations = '<ows:Operation name="GetRecords"><ows:DCP><ows:HTTP><ows:Get xlink:href="https://registered.example/records"/></ows:HTTP></ows:DCP></ows:Operation>' if protocol == 'CSW' else '<ows:Operation name="GetFeature"><ows:Parameter name="outputFormat"><ows:AllowedValues><ows:Value>application/json</ows:Value></ows:AllowedValues></ows:Parameter></ows:Operation>'
    prefix = 'csw' if protocol == 'CSW' else 'wfs'
    return f'''<{prefix}:Capabilities xmlns:{prefix}="http://www.opengis.net/{prefix}" version="{version}"
      xmlns:ows="http://www.opengis.net/ows" xmlns:xlink="http://www.w3.org/1999/xlink" xmlns:ms="https://example.test/ms">
      <ows:OperationsMetadata>{operations}</ows:OperationsMetadata>
      <FeatureTypeList><FeatureType><Name>ms:Countries</Name><DefaultCRS>urn:ogc:def:crs:EPSG::4326</DefaultCRS></FeatureType></FeatureTypeList>
    </{prefix}:Capabilities>'''.encode()


def iso_record(identifier='live-id'):
    return f'''<gmd:MD_Metadata xmlns:gmd="http://www.isotc211.org/2005/gmd" xmlns:gco="http://www.isotc211.org/2005/gco">
      <gmd:fileIdentifier><gco:CharacterString>{identifier}</gco:CharacterString></gmd:fileIdentifier>
      <gmd:hierarchyLevel><gmd:MD_ScopeCode codeListValue="dataset"/></gmd:hierarchyLevel>
      <gmd:identificationInfo><gmd:MD_DataIdentification>
        <gmd:citation><gmd:CI_Citation><gmd:title><gco:CharacterString>Live dataset</gco:CharacterString></gmd:title></gmd:CI_Citation></gmd:citation>
        <gmd:abstract><gco:CharacterString>Fresh metadata</gco:CharacterString></gmd:abstract>
        <gmd:extent><gmd:EX_Extent><gmd:geographicElement><gmd:EX_GeographicBoundingBox>
          <gmd:westBoundLongitude><gco:Decimal>0</gco:Decimal></gmd:westBoundLongitude>
          <gmd:eastBoundLongitude><gco:Decimal>4</gco:Decimal></gmd:eastBoundLongitude>
          <gmd:southBoundLatitude><gco:Decimal>-2</gco:Decimal></gmd:southBoundLatitude>
          <gmd:northBoundLatitude><gco:Decimal>0</gco:Decimal></gmd:northBoundLatitude>
        </gmd:EX_GeographicBoundingBox></gmd:geographicElement></gmd:EX_Extent></gmd:extent>
      </gmd:MD_DataIdentification></gmd:identificationInfo>
    </gmd:MD_Metadata>'''


class LivePreviewTests(TestCase):
    fixtures = ['test_users.json', 'test_keywords.json', 'test_crs.json',
                'test_wms.json', 'test_wfs_proxy.json', 'test_csw.json']

    def setUp(self):
        self.media = TemporaryDirectory()
        self.addCleanup(self.media.cleanup)
        override = override_settings(MEDIA_ROOT=self.media.name)
        override.enable()
        self.addCleanup(override.disable)
        self.user = get_user_model().objects.create_superuser(username='preview', password='test')
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.client.credentials(HTTP_ACCEPT='application/json', HTTP_AUTHORIZATION='Token mrmap-secret')
        self.wms = WebMapService.objects.get(pk=WMS)
        self.wfs = WebFeatureService.objects.get(pk=WFS)
        self.csw = CatalogueService.objects.get(pk=CSW)
        for service in (self.wms, self.wfs, self.csw):
            self.set_capabilities(service)
            for operation in service.operation_urls.all():
                operation.url = f'https://registered.example/{operation.operation}-{operation.method}'
                operation.save()
        self.wms.layers.update(is_queryable=True)
        self.wfs.featuretypes.update(is_active=True)
        self.image = BytesIO()
        Image.new('RGB', (64, 32), 'green').save(self.image, 'PNG')
        self.features = {'type': 'FeatureCollection', 'features': [
            {'type': 'Feature', 'properties': {'text': '<img onerror=alert(1)>'},
             'geometry': {'type': 'Point', 'coordinates': [0, 0]}}]}
        self.send = patch('requests.sessions.Session.send', return_value=response(self.image.getvalue(), 'image/png')).start()
        self.addCleanup(patch.stopall)

    @staticmethod
    def set_capabilities(service, version=None):
        from registry.enums.service import OGCServiceVersionEnum
        version = version or OGCServiceVersionEnum(service.version).label
        service.xml_backup_file = SimpleUploadedFile('preview.xml', capabilities(service.service_type, version))
        service.save()

    def request(self, protocol='wms', **params):
        service = {'wms': self.wms, 'wfs': self.wfs, 'csw': self.csw}[protocol]
        return self.client.get(f'/api/registry/{protocol}/{service.pk}/preview', params)

    def test_closed_discovery_reads_no_upstream_and_missing_extent_still_requests(self):
        self.wms.layers.update(bbox_lat_lon=None)
        result = self.request(selection='node1.1')
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json()['discovery'], 'stored')
        self.assertIsNone(result.json()['configuration']['extent'])
        self.send.assert_not_called()
        result = self.request(selection='node1.1', bbox='-2,0,4,8')
        self.assertEqual(result.status_code, 200)
        self.assertEqual(base64.b64decode(result.json()['image'].split(',')[1]), self.image.getvalue())
        self.assertIn('fetchedAt', result.json())

    def test_wms_versions_axis_order_and_operation_endpoints(self):
        for version, code, bbox, crs in [('1.3.0', 130, '0.0,-2.0,8.0,4.0', 'CRS'), ('1.1.1', 111, '-2.0,0.0,4.0,8.0', 'SRS')]:
            self.wms.version = code
            self.set_capabilities(self.wms, version)
            result = self.request(selection='node1.1', bbox='-2,0,4,8')
            self.assertEqual(result.status_code, 200, result.content)
            request = self.send.call_args.args[0]
            params = parse_qs(urlsplit(request.url).query)
            self.assertEqual(params['BBOX'], [bbox])
            self.assertEqual(params[crs], ['EPSG:4326'])
            self.assertIn('/20-1', request.url)
            self.send.return_value = response(self.image.getvalue(), 'image/png')
            self.send.reset_mock()
            discovery = self.request(selection='node1.1').json()
            url = discovery['identify']['url']
            identify = parse_qs(urlsplit(url).query)
            self.assertEqual(urlsplit(url).path, f'/mrmap-proxy/wms/{self.wms.pk}')
            self.assertEqual(identify['QUERY_LAYERS'], ['node1.1'])
            self.assertEqual(identify[crs], ['EPSG:4326'])
            self.assertEqual(identify['FEATURE_COUNT'], ['10'])
            # The service advertises text/html first, but only self contained formats are
            # handed to the browser.
            self.assertEqual(identify['INFO_FORMAT'], ['text/plain'])
            self.assertEqual(discovery['identify']['infoFormat'], 'text/plain')
            self.assertTrue(discovery['configuration']['queryable'])
            # Generating the url must not contact upstream.
            self.send.assert_not_called()

    def test_html_only_identify_offers_no_url(self):
        self.wms.xml_backup_file = SimpleUploadedFile(
            'preview.xml', capabilities('WMS', '1.3.0').replace(b'<Format>text/plain; charset=utf-8</Format>', b''))
        self.wms.save()
        result = self.request(selection='node1.1')
        self.assertEqual(result.status_code, 200, result.content)
        self.assertFalse(result.json()['configuration']['queryable'])
        self.assertIsNone(result.json()['identify'])
        self.send.assert_not_called()

    def test_upstream_auth_is_applied_without_caller_credentials(self):
        session = Session()
        session.auth = ('upstream', 'password')
        with patch.object(WebMapService, 'get_session_for_request', return_value=session):
            result = self.request(selection='node1.1', bbox='0,0,4,8')
        self.assertEqual(result.status_code, 200)
        request = self.send.call_args.args[0]
        self.assertTrue(request.headers['Authorization'].startswith('Basic '))
        self.assertNotIn('mrmap-secret', str(request.headers))
        self.assertNotIn('Cookie', request.headers)
        self.assertFalse(self.send.call_args.kwargs['allow_redirects'])
        self.assertTrue(self.send.call_args.kwargs['stream'])

    def test_permissions_and_disabled_services_do_not_contact_upstream(self):
        user = get_user_model().objects.create_user(username='no-preview')
        self.client.force_authenticate(user)
        self.assertEqual(self.request(selection='node1.1', bbox='0,0,4,8').status_code, 403)
        self.client.force_authenticate(self.user)
        WebMapService.objects.filter(pk=WMS).update(is_active=False)
        result = self.request(selection='node1.1', bbox='0,0,4,8')
        self.assertEqual(result.status_code, 423)
        self.send.assert_not_called()

    def test_ogc_malformed_and_unsupported_states(self):
        for content, expected in [(b'<ServiceExceptionReport><ServiceException>gone</ServiceException></ServiceExceptionReport>', 'ogc'), (b'not an image', 'malformed')]:
            self.send.return_value = response(content, 'image/png')
            result = self.request(selection='node1.1', bbox='0,0,4,8')
            self.assertEqual(result.json()['error'], expected)
        self.assertEqual(self.request(selection='gone').json()['error'], 'stale')
        self.assertEqual(self.request(selection='node1.1', bbox='nan,0,4,8').status_code, 400)
        self.assertEqual(self.request(selection='node1.1', bbox='0,0,4,8', width=5000).status_code, 400)
        self.wms.xml_backup_file = SimpleUploadedFile('preview.xml', capabilities('WMS', '1.3.0').replace(b'EPSG:4326', b'EPSG:25832'))
        self.wms.save()
        self.assertEqual(self.request(selection='node1.1').json()['error'], 'crs')

    def test_wfs_version_correct_requests_and_feature_limit(self):
        self.send.return_value = response(json.dumps(self.features).encode())
        for version, code in [('1.0.0', 1), ('1.1.0', 11), ('2.0.0', 200), ('2.0.2', 202)]:
            self.wfs.version = code
            self.set_capabilities(self.wfs, version)
            result = self.request('wfs', selection='ms:Countries', bbox='-2,0,4,8', count=99999)
            self.assertEqual(result.status_code, 200, result.content)
            self.assertEqual(result.json()['features'], self.features)
            params = parse_qs(urlsplit(self.send.call_args.args[0].url).query)
            name = 'TYPENAMES' if version.startswith('2.') else 'TYPENAME'
            limit = 'COUNT' if version.startswith('2.') else 'MAXFEATURES'
            self.assertEqual(params[name], ['ms:Countries'])
            self.assertEqual(params[limit], ['500'])
            self.assertEqual(params['BBOX'], ['-2.0,0.0,4.0,8.0' if version == '1.0.0' else '0.0,-2.0,8.0,4.0,EPSG:4326'])
            self.assertTrue(result.json()['limited'])
            self.assertIn('/30-1', self.send.call_args.args[0].url)

    def test_gml_only_wfs_is_explicitly_unsupported(self):
        self.wfs.xml_backup_file = SimpleUploadedFile('gml.xml', capabilities('WFS').replace(b'application/json', b'application/gml+xml'))
        self.wfs.save()
        self.assertEqual(self.request('wfs', selection='ms:Countries', bbox='0,0,4,8').json()['error'], 'format')
        self.send.assert_not_called()

    def test_wfs_spatial_permissions_are_caller_scoped_and_keep_viewport_and_limit(self):
        user = get_user_model().objects.create_user(username='restricted')
        group = Group.objects.create(name='preview-area')
        user.groups.add(group)
        assign_perm('view_webfeatureservice', user, self.wfs)
        element = self.wfs.featuretypes.get(identifier='ms:Countries')
        area = MultiPolygon(Polygon.from_bbox((0, 0, 4, 8)), srid=4326)
        allowed = AllowedWebFeatureServiceOperation.objects.create(secured_service=self.wfs, allowed_area=area)
        allowed.operations.add(30)
        allowed.secured_feature_types.add(element)
        allowed.allowed_groups.add(group)
        other = AllowedWebFeatureServiceOperation.objects.create(secured_service=self.wfs, allowed_area=MultiPolygon(Polygon.from_bbox((80, 40, 100, 50)), srid=4326))
        other.operations.add(30)
        other.secured_feature_types.add(element)
        other.allowed_groups.add(Group.objects.create(name='other-area'))
        self.client.force_authenticate(user)
        self.send.return_value = response(json.dumps(self.features).encode())
        # Axis-order helper is deterministic here; no external EPSG registry lookup.
        with patch('registry.helper.preview.adjust_axis_order', side_effect=lambda geometry: geometry):
            result = self.request('wfs', selection='ms:Countries', bbox='-2,0,4,8')
        self.assertEqual(result.status_code, 200, result.content)
        request = self.send.call_args.args[0]
        self.assertEqual(request.method, 'POST')
        self.assertIn('/30-2', request.url)
        root = etree.fromstring(request.body)
        self.assertEqual(root.get('count'), '500')
        self.assertEqual(root.get('outputFormat'), 'application/json')
        self.assertEqual(root.xpath('//*[local-name()="Query"]')[0].get('typeNames'), 'ms:Countries')
        self.assertEqual(root.xpath('//*[local-name()="Query"]')[0].get('srsName'), 'EPSG:4326')
        self.assertEqual(root.xpath('count(//*[local-name()="And"])'), 1)
        self.assertEqual(root.xpath('count(//*[local-name()="Within"])'), 1)
        self.assertNotIn(b'100', request.body)
        self.assertEqual(root.nsmap['ms'], 'https://example.test/ms')
        self.send.return_value = response(json.dumps({**self.features, 'features': [
            {**self.features['features'][0], 'geometry': {'type': 'Point', 'coordinates': [90, 45]}}
        ]}).encode())
        with patch('registry.helper.preview.adjust_axis_order', side_effect=lambda geometry: geometry):
            result = self.request('wfs', selection='ms:Countries', bbox='-2,0,4,8')
        self.assertEqual(result.status_code, 403)
        user.groups.clear()
        self.send.reset_mock()
        self.assertEqual(self.request('wfs', selection='ms:Countries', bbox='-2,0,4,8').status_code, 403)
        self.send.assert_not_called()
        user.groups.add(group)
        self.wfs.version = 11
        self.set_capabilities(self.wfs, '1.1.0')
        self.send.reset_mock()
        result = self.request('wfs', selection='ms:Countries', bbox='-2,0,4,8')
        self.assertEqual(result.json()['error'], 'spatialVersion')
        self.send.assert_not_called()

    def test_wms_spatial_mask_and_identify_url_stays_with_the_proxy(self):
        user = get_user_model().objects.create_user(username='map-preview')
        group = Group.objects.create(name='map-preview-area')
        user.groups.add(group)
        assign_perm('view_webmapservice', user, self.wms)
        allowed = AllowedWebMapServiceOperation.objects.create(
            secured_service=self.wms, allowed_area=MultiPolygon(Polygon.from_bbox((0, 0, 2, 8)), srid=4326))
        allowed.operations.add(20, 21)
        allowed.secured_layers.add(self.wms.layers.get(identifier='node1.1'))
        allowed.allowed_groups.add(group)
        self.client.force_authenticate(user)
        result = self.request(selection='node1.1', bbox='0,0,4,8', width=64, height=32)
        self.assertEqual(result.status_code, 200, result.content)
        raster = Image.open(BytesIO(base64.b64decode(result.json()['image'].split(',')[1])))
        self.assertNotEqual(raster.convert('RGB').getpixel((63, 16)), (0, 128, 0))
        self.assertEqual(raster.convert('RGB').getpixel((0, 16)), (0, 128, 0))
        self.send.reset_mock()
        # Identify is answered by the security proxy: the preview only hands out the
        # same-origin url, so the spatial decision stays with the browser request.
        discovery = self.request(selection='node1.1').json()
        self.assertEqual(discovery['identify']['url'].split('?')[0], f'/mrmap-proxy/wms/{self.wms.pk}')
        self.send.reset_mock()
        result = self.request(selection='node1.1', bbox='0,0,4,8', width=64, height=32)
        self.assertEqual(result.status_code, 200, result.content)
        self.assertNotIn('info', result.json())
        self.assertEqual(parse_qs(urlsplit(self.send.call_args.args[0].url).query)['REQUEST'], ['GetMap'])
        self.send.assert_called_once()

    def test_csw_live_pages_parse_zero_extents_without_persistence(self):
        content = f'<csw:GetRecordsResponse xmlns:csw="http://www.opengis.net/cat/csw/2.0.2"><csw:SearchResults numberOfRecordsMatched="40" numberOfRecordsReturned="1" nextRecord="26">{iso_record()}</csw:SearchResults></csw:GetRecordsResponse>'.encode()
        self.send.return_value = response(content, 'application/xml')
        counts = (DatasetMetadataRecord.objects.count(), HarvestingJob.objects.count(), WebMapServiceUpdateJob.objects.count())
        result = self.request('csw', start=1)
        self.assertEqual(result.status_code, 200, result.content)
        self.assertEqual(result.json()['records'][0]['extent'], [0.0, -2.0, 4.0, 0.0])
        self.assertEqual(result.json()['records'][0]['previews'], [])
        self.assertEqual(result.json()['next'], 26)
        params = parse_qs(urlsplit(self.send.call_args.args[0].url).query)
        self.assertEqual(params['maxRecords'], ['25'])
        self.assertEqual(params['resultType'], ['results'])
        self.assertEqual(counts, (DatasetMetadataRecord.objects.count(), HarvestingJob.objects.count(), WebMapServiceUpdateJob.objects.count()))
        self.assertEqual(result.headers['Cache-Control'], 'no-store')

    def test_csw_unsupported_schema(self):
        self.send.return_value = response(b'<GetRecordsResponse><SearchResults><Record/></SearchResults></GetRecordsResponse>', 'application/xml')
        self.assertEqual(self.request('csw').json()['error'], 'schema')

    def test_csw_links_require_same_catalogue_provenance_and_registered_relation(self):
        metadata = DatasetMetadataRecord.objects.create(file_identifier='live-id', title='registered',
                                                        dataset_contact_id=1, metadata_contact_id=1)
        element = self.wms.layers.get(identifier='node1.1')
        MetadataRelation.objects.create(dataset_metadata=metadata, layer=element, origin=1)
        job = HarvestingJob.objects.create(service=self.csw)
        HarvestedMetadataRelation.objects.create(harvesting_job=job, dataset_metadata_record=metadata, collecting_state=1)
        links = registered_previews(self.csw, 'live-id', 'dataset', self.user)
        self.assertEqual(links[0]['selection'], 'node1.1')
        self.assertEqual(registered_previews(self.csw, 'other-id', 'dataset', self.user), [])
        self.assertEqual(registered_previews(CatalogueService.objects.exclude(pk=CSW).first(), 'live-id', 'dataset', self.user), [])


class PreviewLimitsTests(SimpleTestCase):
    def test_digest_challenge_is_bounded_before_authentication_hooks_consume_it(self):
        from requests.auth import HTTPDigestAuth
        session = PreviewSession()
        session.auth = HTTPDigestAuth('registered', 'password')
        request = session.prepare_request(Request('GET', 'https://registered.example'))
        first_hook = request.hooks['response'][0]
        self.assertEqual(first_hook.__name__, 'buffer_auth_response')
        session.started_at = 0
        challenge = response(b'x' * 32, status=401)
        with patch('registry.helper.preview.RESPONSE_LIMIT', 16), patch('registry.helper.preview.time.monotonic', return_value=0), patch.object(challenge, 'close') as close:
            with self.assertRaises(PreviewError):
                first_hook(challenge)
            close.assert_called_once()

    def test_ogc_kvp_accepts_case_variants_and_legacy_typenames(self):
        from registry.ows_lib.wfs.wfs import WebFeatureServiceClient
        for name in ['typeName', 'typeNames', 'TYPENAME', 'TYPENAMES']:
            request = OGCRequest(method='GET', params={
                name: 'ms:Countries', 'request': 'GetFeature',
                'service': 'WFS', 'version': '2.0.2', 'count': '500'})
            self.assertEqual(request.requested_entities, ['ms:Countries'])
            self.assertEqual(request.ogc_query_params['COUNT'], '500')
        client = WebFeatureServiceClient(capabilities('WFS', '2.0.2'))
        self.assertEqual(client.type_name_qp, 'TYPENAMES')
        self.assertEqual(client.max_features_qp, 'COUNT')

    def test_size_and_time_limits_close_upstream_response(self):
        for chunks, clock in [([b'x' * 32], [0, 0]), ([b'x'], [0, 20])]:
            remote = response(b'')
            with patch('requests.sessions.Session.send', return_value=remote), patch.object(remote, 'iter_content', return_value=iter(chunks)), patch('registry.helper.preview.RESPONSE_LIMIT', 16), patch('registry.helper.preview.time.monotonic', side_effect=clock), patch.object(remote, 'close') as close:
                with self.assertRaises(PreviewError):
                    PreviewSession().send(Request('GET', 'https://registered.example').prepare())
                close.assert_called_once()

    def test_invalid_geojson_crs_geometry_and_feature_overflow(self):
        for value in [{'type': 'FeatureCollection', 'features': [{}]},
                      {'type': 'FeatureCollection', 'features': [], 'crs': ['invalid']},
                      {'type': 'FeatureCollection', 'features': [{}] * (FEATURE_LIMIT + 1)},
                      {'type': 'FeatureCollection', 'features': [], 'crs': {'properties': {'name': 'EPSG:3857'}}},
                      {'type': 'FeatureCollection', 'features': [{'type': 'Feature', 'properties': {}, 'geometry': {'type': 'Point', 'coordinates': [900, 0]}}]}]:
            with self.assertRaises(PreviewError):
                validate_features(value)
        self.assertEqual(checked_bbox('-2,0,4,8'), [-2, 0, 4, 8])

    def test_general_proxy_dispatches_by_operation_and_method(self):
        view = OgcServiceProxyView()
        view.service = SimpleNamespace(operation_urls=SimpleNamespace(values=lambda *args: SimpleNamespace(get=lambda **kwargs: {'url': f'https://registered.example/{kwargs["operation"]}-{kwargs["method"]}'})))
        for operation, method, expected in [('GetFeature', 'GET', '30-1'), ('GetFeatureInfo', 'GET', '21-1'), ('GetFeature', 'POST', '30-2')]:
            view.ogc_request = OGCRequest(method=method, params={'REQUEST': operation, 'VERSION': '2.0.0'}, headers={'Authorization': 'Token secret', 'Cookie': 'session=secret'})
            view.ogc_request.operation = operation
            with patch.object(OgcServiceProxyView, 'remote_service', new=SimpleNamespace(send_request=lambda request: request)):
                request = view.get_remote_response()
            self.assertIn(expected, request.url)
            self.assertNotIn('Authorization', request.headers)
            self.assertNotIn('Cookie', request.headers)
