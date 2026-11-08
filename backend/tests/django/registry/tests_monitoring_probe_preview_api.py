"""Tests of the monitoring probe preview endpoint of a registered WMS.

The endpoint exposes the transient generator of
``registry.helper.monitoring_generation`` for the epic's consumers: it must
respect object permissions, answer the full preview contract, report the not
yet implemented comprehensive preset explicitly and never execute a probe or
write a setting while previewing.
"""
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import Resolver404, resolve
from guardian.shortcuts import assign_perm
from registry.models.monitoring import (GetMapProbe,
                                        WebMapServiceMonitoringSetting)
from registry.models.service import WebMapService
from rest_framework.test import APIClient

WMS = 'cd16cc1f-3abb-4625-bb96-fbe80dbe23e3'
WMS_WITHOUT_CAPABILITIES = '1b195589-dcfa-403f-9e66-e7e1c0a67024'
WFS = '73cf78c9-6605-47fd-ac4f-1be59265df65'


def capabilities(version="1.3.0"):
    return f"""
        <WMS_Capabilities version="{version}" xmlns:xlink="http://www.w3.org/1999/xlink">
            <Capability><Request>
                <GetCapabilities><Format>text/xml</Format><DCPType><HTTP><Get>
                    <OnlineResource xlink:href="https://registered.example/capabilities?"/>
                </Get></HTTP></DCPType></GetCapabilities>
                <GetMap><Format>image/png</Format><DCPType><HTTP><Get>
                    <OnlineResource xlink:href="https://registered.example/wms?"/>
                </Get></HTTP></DCPType></GetMap>
            </Request>
            <Exception><Format>XML</Format></Exception>
            <Layer><Name>node1</Name>
                <CRS>CRS:84 EPSG:4326</CRS>
                <Style><Name>style node 1</Name><Title>s1</Title></Style>
                <Layer><Name>node1.1</Name></Layer>
                <Layer><Name>node1.1.1</Name></Layer>
                <Layer><Name>node1.1.2</Name></Layer>
                <Layer><Name>node1.1.3</Name></Layer>
                <Layer><Name>node1.2</Name></Layer>
                <Layer><Name>node1.3</Name></Layer>
                <Layer><Name>node1.3.1</Name></Layer>
            </Layer></Capability>
        </WMS_Capabilities>""".encode()


class MonitoringProbePreviewApiTests(TestCase):

    fixtures = ['test_users.json', 'test_keywords.json', 'test_crs.json',
                'test_wms.json', 'test_wfs_proxy.json']

    def setUp(self):
        self.media = TemporaryDirectory()
        self.addCleanup(self.media.cleanup)
        override = override_settings(MEDIA_ROOT=self.media.name)
        override.enable()
        self.addCleanup(override.disable)
        self.user = get_user_model().objects.create_superuser(
            username='probe-preview', password='test')
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.client.credentials(HTTP_ACCEPT='application/json')
        self.wms = WebMapService.objects.get(pk=WMS)
        # the fixtures ship one deactivated layer; activate the tree so the
        # contract test counts a deterministic full set
        self.wms.layers.update(is_active=True)
        self.store()
        # a preview never executes a probe: every remote send is a failure
        self.send = patch(
            'requests.sessions.Session.send',
            side_effect=AssertionError('the preview must not contact the service'),
        ).start()
        self.addCleanup(patch.stopall)

    def store(self, service=None, document=None):
        service = service or self.wms
        service.xml_backup_file = SimpleUploadedFile(
            'probes.xml', document or capabilities())
        service.save()

    def url(self, pk=None, protocol='wms'):
        return f'/api/registry/{protocol}/{pk or self.wms.pk}/monitoring-probe-preview'

    # --- the contract ---------------------------------------------------------

    def test_superuser_gets_the_full_preview_contract(self):
        response = self.client.get(self.url())

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response['Cache-Control'], 'no-store')
        result = response.json()
        self.assertEqual(result['serviceId'], str(self.wms.pk))
        self.assertEqual(result['preset'], 'standard')
        self.assertEqual({
            'serviceId', 'serviceTitle', 'preset', 'generatorVersion', 'wmsVersion',
            'bounds', 'presets', 'notImplemented', 'request', 'pagination',
            'probes', 'skipped', 'skippedTotal', 'skippedTruncated',
        } - set(result), set())
        self.assertEqual(len(result['probes']), 1 + 8)  # GetCapabilities plus layers
        self.assertEqual(result['probes'][0]['probeType'], 'GetCapabilities')
        self.assertNotEqual(result['probes'][0]['candidateId'],
                            result['probes'][1]['candidateId'])
        self.send.assert_not_called()

    def test_editable_parameters_shape_the_proposal_without_writes(self):
        response = self.client.get(self.url(), {
            'preset': 'basic', 'width': 128, 'height': 128, 'timeout': 10,
            'imageFormat': 'image/png'})

        self.assertEqual(response.status_code, 200, response.content)
        result = response.json()
        self.assertEqual(result['request'], {
            'width': 128, 'height': 128, 'timeout': 10,
            'format': 'image/png', 'crs': None})
        self.assertEqual(len(result['probes']), 2)
        self.send.assert_not_called()
        # previewing proposes, it never persists
        self.assertEqual(WebMapServiceMonitoringSetting.objects.count(), 0)
        self.assertEqual(GetMapProbe.objects.count(), 0)

    def test_explicit_selection_pages_through_large_services(self):
        response = self.client.get(self.url(), {'layer': 'node1.2'})

        self.assertEqual(response.status_code, 200, response.content)
        result = response.json()
        maps = [probe for probe in result['probes'] if probe['probeType'] == 'GetMap']
        self.assertEqual([probe['targetLayer']['identifier'] for probe in maps],
                         ['node1.2'])

    # --- permissions -----------------------------------------------------------

    def test_user_without_view_permission_is_rejected(self):
        user = get_user_model().objects.create_user(username='no-probes')
        self.client.force_authenticate(user)

        response = self.client.get(self.url())

        self.assertEqual(response.status_code, 403)
        self.send.assert_not_called()

    def test_anonymous_caller_without_view_permission_is_rejected(self):
        # guardian answers the object permissions of an anonymous caller
        # through its anonymous user row, which a test database may or may not
        # hold depending on the suite order
        get_user_model().objects.get_or_create(username='AnonymousUser')
        client = APIClient()
        client.credentials(HTTP_ACCEPT='application/json')

        response = client.get(self.url())

        self.assertEqual(response.status_code, 403)
        self.send.assert_not_called()

    def test_anonymous_caller_is_rejected_without_an_anonymous_user(self):
        # without that row nothing can be granted to an anonymous caller: the
        # answer is a rejection, not the exception of the permission lookup
        get_user_model().objects.filter(username='AnonymousUser').delete()
        client = APIClient()
        client.credentials(HTTP_ACCEPT='application/json')

        response = client.get(self.url())

        self.assertEqual(response.status_code, 403, response.content)
        self.send.assert_not_called()

    def test_view_permission_of_the_anonymous_user_opens_the_preview(self):
        # the preview follows the object permission, so a service which is
        # public to the anonymous user is previewable without credentials
        anonymous = get_user_model().objects.get_or_create(
            username='AnonymousUser')[0]
        assign_perm('view_webmapservice', anonymous, self.wms)
        client = APIClient()
        client.credentials(HTTP_ACCEPT='application/json')

        response = client.get(self.url())

        self.assertEqual(response.status_code, 200, response.content)
        self.send.assert_not_called()

    def test_assigned_view_permission_opens_the_preview(self):
        user = get_user_model().objects.create_user(username='probe-reader')
        assign_perm('view_webmapservice', user, self.wms)
        self.client.force_authenticate(user)

        response = self.client.get(self.url())

        self.assertEqual(response.status_code, 200, response.content)
        self.send.assert_not_called()

    # --- explicit rejections -----------------------------------------------------

    def test_comprehensive_preset_is_reported_with_its_operations(self):
        response = self.client.get(self.url(), {'preset': 'comprehensive'})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response['Cache-Control'], 'no-store')
        result = response.json()
        self.assertEqual(result['error'], 'presetNotImplemented')
        self.assertEqual(result['implementedPresets'], ['basic', 'standard'])
        self.assertEqual(result['operations'],
                         ['GetFeatureInfo', 'DescribeFeatureType'])

    def test_invalid_parameters_are_answered_with_their_code(self):
        for params, code in [({'preset': 'kitchen-sink'}, 'preset'),
                             ({'width': 4000}, 'limit'),
                             ({'offset': -1}, 'offset'),
                             ({'crs': 'world-yx'}, 'crsOverride'),
                             ({'imageFormat': 'application/pdf'}, 'formatOverride')]:
            with self.subTest(**params):
                response = self.client.get(self.url(), params)

                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.json()['error'], code)
        self.send.assert_not_called()

    def test_disabled_service_stays_locked(self):
        WebMapService.objects.filter(pk=WMS).update(is_active=False)

        response = self.client.get(self.url())

        self.assertEqual(response.status_code, 423)
        self.assertEqual(response.json()['error'], 'disabled')

    def test_service_without_stored_capabilities_reports_discovery(self):
        response = self.client.get(self.url(pk=WMS_WITHOUT_CAPABILITIES))

        self.assertEqual(response.status_code, 422, response.content)
        self.assertEqual(response.json()['error'], 'discovery')
        self.send.assert_not_called()

    def test_the_nested_service_route_does_not_offer_the_preview(self):
        # nested relationship viewsets inherit the service viewsets, but the
        # preview addresses only the canonical registered-service endpoint
        from registry.views.service import (NestedWebMapServiceViewSet,
                                            WebMapServiceViewSet)

        self.assertIn('monitoring_probe_preview', {
            action.__name__ for action in WebMapServiceViewSet.get_extra_actions()})
        self.assertNotIn('monitoring_probe_preview', {
            action.__name__ for action in NestedWebMapServiceViewSet.get_extra_actions()})

    def test_only_the_wms_route_offers_the_preview(self):
        for url in (self.url(pk=WFS, protocol='wfs'),
                    f'/api/registry/csw/{WFS}/monitoring-probe-preview'):
            with self.subTest(url=url), self.assertRaises(Resolver404):
                resolve(url)

    def test_the_schema_describes_the_endpoint_on_the_wms_route(self):
        from django.urls import include, path
        from drf_spectacular.generators import SchemaGenerator
        from registry.urls import urlpatterns

        patterns = [pattern for pattern in urlpatterns
                    if getattr(pattern, 'name', None) == 'wms-monitoring-probe-preview']
        self.assertTrue(patterns)
        schema = SchemaGenerator(
            patterns=[path('api/registry/', include(patterns))]
        ).get_schema(public=True)

        paths = [operation for url, operation in schema['paths'].items()
                 if url.endswith('/monitoring-probe-preview')]
        self.assertEqual(len(paths), 1)
        operation = paths[0]['get']
        parameters = {parameter['name'] for parameter in operation['parameters']}
        self.assertTrue({'preset', 'layer', 'offset', 'limit', 'width', 'height',
                         'timeout', 'imageFormat', 'crs'} <= parameters)
        self.assertTrue({'id', 'pk'} & parameters)
        self.assertIn('200', operation['responses'])
        self.assertIn('comprehensive', operation['description'])
