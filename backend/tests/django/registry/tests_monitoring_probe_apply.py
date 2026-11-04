"""Tests of the apply action which persists generated monitoring probes.

The apply endpoint of #743 consumes the candidates of the monitoring probe
preview (#742): it must revalidate them against the CURRENT capabilities,
persist atomically and idempotently (repeated, retried and concurrent applies
can not duplicate a generated probe), preserve manual probes and
user-customized generated parameters unless the replacement is confirmed,
never activate the periodic schedule and stay inside its bounds. The probe
provenance itself is exercised on the models.
"""
import copy
import threading
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection, transaction
from django.test import SimpleTestCase, TestCase, TransactionTestCase, override_settings
from django.urls import Resolver404, resolve
from django_celery_beat.models import CrontabSchedule
from guardian.shortcuts import assign_perm
from registry.enums.monitoring import ProbeOriginEnum
from registry.models.monitoring import (
    GetCapabilitiesProbe, GetMapProbe, WebMapServiceMonitoringRun,
    WebMapServiceMonitoringSetting)
from registry.models.service import Layer, WebMapService
from registry.ows_lib.client.core import OgcClient
from rest_framework.renderers import JSONRenderer
from rest_framework.test import APIClient
from tests.django.utils import MockResponse

WMS = 'cd16cc1f-3abb-4625-bb96-fbe80dbe23e3'

CAPABILITIES = """
    <WMS_Capabilities version="1.3.0" xmlns:xlink="http://www.w3.org/1999/xlink">
        <Capability><Request>
            <GetCapabilities><Format>text/xml</Format><DCPType><HTTP><Get>
                <OnlineResource xlink:href="https://registered.example/capabilities?"/>
            </Get></HTTP></DCPType></GetCapabilities>
            <GetMap><Format>image/png</Format><Format>image/jpeg</Format><DCPType><HTTP><Get>
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


def capabilities():
    return CAPABILITIES


def probe_parameters(preview, probe_type, identifier=None):
    """The full candidate of one preview probe, as the UI would submit it."""
    for probe in preview['probes']:
        if probe['probeType'] != probe_type:
            continue
        target = probe.get('targetLayer')
        if identifier is None and probe_type == 'GetCapabilities':
            return probe
        if target and target['identifier'] == identifier:
            return probe
    raise AssertionError(f"no {probe_type} candidate for {identifier}")


class ProbeProvenanceModelTests(TestCase):
    """Provenance fields, upgrade defaults and the idempotence constraint."""

    fixtures = ['test_users.json', 'test_keywords.json', 'test_crs.json',
                'test_wms.json']

    def setUp(self):
        self.wms = WebMapService.objects.get(pk=WMS)
        self.setting = WebMapServiceMonitoringSetting.objects.create(
            service=self.wms,
            crontab=CrontabSchedule.objects.create(minute="*/5", hour="*"))

    def test_existing_style_probes_are_manual_by_default(self):
        # a probe created the way every probe was created before the
        # generated probes — the migration applies the same default to the
        # rows which already exist
        probe = GetMapProbe.objects.create(setting=self.setting)
        self.assertEqual(probe.origin, ProbeOriginEnum.MANUAL)
        self.assertIsNone(probe.generator_identity)
        self.assertIsNone(probe.generator_version)
        self.assertIsNone(probe.generator_preset)

    def test_manual_probes_need_no_identity(self):
        for _ in range(3):
            GetCapabilitiesProbe.objects.create(setting=self.setting)
        self.assertEqual(GetCapabilitiesProbe.objects.count(), 3)

    def test_generated_identity_is_unique_per_probe_type(self):
        first = GetMapProbe.objects.create(
            setting=self.setting, origin=ProbeOriginEnum.GENERATED,
            generator_identity='abc123', generator_version='1.0.0',
            generator_preset='standard')
        self.assertIsNotNone(first.pk)
        with transaction.atomic():
            with self.assertRaises(Exception):
                GetMapProbe.objects.create(
                    setting=self.setting, origin=ProbeOriginEnum.GENERATED,
                    generator_identity='abc123')
        self.assertEqual(GetMapProbe.objects.count(), 1)
        # another probe type is another table: the same identity may exist
        GetCapabilitiesProbe.objects.create(
            setting=self.setting, origin=ProbeOriginEnum.GENERATED,
            generator_identity='abc123')
        self.assertEqual(GetCapabilitiesProbe.objects.count(), 1)

    def test_manual_probes_may_share_an_identity_value(self):
        # the constraint is partial: only generated rows are pinned
        GetCapabilitiesProbe.objects.create(
            setting=self.setting, origin=ProbeOriginEnum.GENERATED,
            generator_identity='same')
        GetCapabilitiesProbe.objects.create(
            setting=self.setting, origin=ProbeOriginEnum.MANUAL,
            generator_identity='same')
        GetCapabilitiesProbe.objects.create(
            setting=self.setting, origin=ProbeOriginEnum.MANUAL,
            generator_identity='same')
        self.assertEqual(GetCapabilitiesProbe.objects.count(), 3)


class PlainJSONClient(APIClient):
    """Client which can send the plain JSON body the apply action takes;
    the deployed REST_FRAMEWORK only registers the JSON:API test renderer."""

    def __init__(self, **defaults):
        super().__init__(**defaults)
        self.renderer_classes['json'] = JSONRenderer


class MonitoringProbeApplyTestsMixin:
    """Setup shared by the API tests of the apply action."""

    fixtures = ['test_users.json', 'test_keywords.json', 'test_crs.json',
                'test_wms.json', 'test_wfs_proxy.json']

    def setUp(self):
        self.media = TemporaryDirectory()
        self.addCleanup(self.media.cleanup)
        override = override_settings(MEDIA_ROOT=self.media.name)
        override.enable()
        self.addCleanup(override.disable)
        self.user = get_user_model().objects.create_superuser(
            username='probe-apply', password='test')
        self.client = PlainJSONClient()
        self.client.force_authenticate(self.user)
        self.client.credentials(HTTP_ACCEPT='application/json')
        self.wms = WebMapService.objects.get(pk=WMS)
        self.wms.layers.update(is_active=True)
        self.store()
        self.setting = WebMapServiceMonitoringSetting.objects.create(
            service=self.wms, enabled=False,
            crontab=CrontabSchedule.objects.create(minute="*/5", hour="*"))
        # persistence never contacts the service either
        self.send = patch(
            'requests.sessions.Session.send',
            side_effect=AssertionError('the apply must not contact the service'),
        ).start()
        self.addCleanup(patch.stopall)

    def store(self, document=None):
        self.wms.xml_backup_file = SimpleUploadedFile(
            'probes.xml', document or capabilities())
        self.wms.save()

    def url(self):
        return f'/api/registry/wms/{self.wms.pk}/monitoring-probes'

    def preview(self):
        response = self.client.get(
            f'/api/registry/wms/{self.wms.pk}/monitoring-probe-preview')
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()

    def payload(self, *candidates, **overrides):
        body = {
            'setting': str(self.setting.pk),
            'preset': 'standard',
            'probes': [
                {'candidateId': candidate['candidateId'],
                 'probeType': candidate['probeType'],
                 'parameters': candidate['parameters']}
                for candidate in candidates],
        }
        body.update(overrides)
        return body

    def default_candidates(self, preview=None):
        preview = preview or self.preview()
        return [probe_parameters(preview, 'GetCapabilities'),
                probe_parameters(preview, 'GetMap', 'node1.2'),
                probe_parameters(preview, 'GetMap', 'node1.1.3')]


class MonitoringProbeApplyApiTests(MonitoringProbeApplyTestsMixin, TestCase):

    # --- the explicit apply -------------------------------------------------

    def test_apply_persists_the_selected_candidates_with_provenance(self):
        report = self.client.post(
            self.url(), self.payload(*self.default_candidates()),
            format='json')

        self.assertEqual(report.status_code, 200, report.content)
        self.assertEqual(report['Cache-Control'], 'no-store')
        result = report.json()
        self.assertEqual(result['summary'], {
            'created': 3, 'updated': 0, 'unchanged': 0, 'preserved': 0})
        self.assertEqual(result['generatorVersion'], '1.0.0')
        self.send.assert_not_called()

        generated = GetMapProbe.objects.filter(
            origin=ProbeOriginEnum.GENERATED)
        self.assertEqual(generated.count(), 2)
        self.assertEqual(
            GetCapabilitiesProbe.objects.filter(
                origin=ProbeOriginEnum.GENERATED).count(), 1)
        probe = generated.select_related('reference_system', 'format').first()
        self.assertEqual(probe.generator_version, '1.0.0')
        self.assertEqual(probe.generator_preset, 'standard')
        self.assertEqual(len(probe.generator_identity), 20)
        self.assertEqual(probe.timeout, 30)
        self.assertEqual(str(probe.reference_system), 'CRS:84')
        self.assertEqual(str(probe.format), 'image/png')
        self.assertEqual(probe.layers.count(), 1)
        # every generated probe lives on the explicitly selected setting
        self.assertEqual(
            set(GetMapProbe.objects.values_list('setting_id', flat=True)),
            {self.setting.pk})

    def test_apply_never_activates_the_periodic_schedule(self):
        # the setting is a PeriodicTask row which the apply must leave alone:
        # never enabled, never rescheduled, no setting created
        settings = WebMapServiceMonitoringSetting.objects.count()
        crontab_id = self.setting.crontab_id

        response = self.client.post(
            self.url(), self.payload(*self.default_candidates()),
            format='json')

        self.assertEqual(response.status_code, 200, response.content)
        self.setting.refresh_from_db()
        self.assertFalse(self.setting.enabled)
        self.assertIsNone(self.setting.last_run_at)
        self.assertEqual(self.setting.crontab_id, crontab_id)
        self.assertEqual(
            WebMapServiceMonitoringSetting.objects.count(), settings)

    def test_editing_parameters_then_applying_persists_the_edit(self):
        preview = self.preview()
        candidate = probe_parameters(preview, 'GetMap', 'node1.2')
        candidate['parameters']['width'] = 512
        candidate['parameters']['timeout'] = 10

        response = self.client.post(
            self.url(), self.payload(candidate), format='json')

        self.assertEqual(response.status_code, 200, response.content)
        probe = GetMapProbe.objects.get()
        self.assertEqual(probe.width, 512)
        self.assertEqual(probe.timeout, 10)

    # --- idempotence ----------------------------------------------------------

    def test_repeated_apply_never_duplicates(self):
        candidates = self.default_candidates()
        first = self.client.post(self.url(), self.payload(*candidates),
                                 format='json').json()
        second = self.client.post(self.url(), self.payload(*candidates),
                                  format='json')

        self.assertEqual(second.status_code, 200, second.content)
        self.assertEqual(second.json()['summary'], {
            'created': 0, 'updated': 0, 'unchanged': 3, 'preserved': 0})
        self.assertEqual(first['summary']['created'], 3)
        self.assertEqual(GetMapProbe.objects.count(), 2)
        self.assertEqual(GetCapabilitiesProbe.objects.count(), 1)

    def test_retry_after_user_edit_is_idempotent_on_the_edited_state(self):
        candidates = self.default_candidates()
        map_candidate = next(c for c in candidates
                             if c['probeType'] == 'GetMap')
        map_candidate['parameters']['width'] = 128
        self.client.post(self.url(), self.payload(*candidates), format='json')

        second = self.client.post(self.url(), self.payload(*candidates),
                                  format='json').json()

        # the stored probe is customized against the regeneration, so the
        # second apply preserves it — with the same effect as writing the
        # identical submitted value: no duplication and no value change
        self.assertEqual(GetMapProbe.objects.count(), 2)
        self.assertEqual(
            GetMapProbe.objects.get(width=128).width, 128)
        self.assertIn(map_candidate['candidateId'],
                      second['replaceConfirmationRequired'])

    def test_stable_identity_survives_preset_and_parameter_changes(self):
        # the identity keys on the target only: applying the same target
        # again under the basic preset recognizes the generated row instead
        # of duplicating it and the row carries the latest preset
        candidate = probe_parameters(self.preview(), 'GetMap', 'node1.2')
        self.client.post(self.url(), self.payload(candidate), format='json')

        rerun = probe_parameters(self.preview(), 'GetMap', 'node1.2')
        second = self.client.post(
            self.url(), self.payload(rerun, preset='basic'), format='json'
        ).json()

        self.assertEqual(GetMapProbe.objects.count(), 1)
        self.assertEqual(second['summary']['unchanged'], 1)
        self.assertEqual(
            GetMapProbe.objects.get().generator_preset, 'basic')

    # --- stale previews ---------------------------------------------------------

    def test_unknown_candidate_is_refused_as_stale(self):
        candidates = self.default_candidates()
        candidates[0]['candidateId'] = 'f' * 20

        response = self.client.post(
            self.url(), self.payload(*candidates), format='json')

        self.assertEqual(response.status_code, 409, response.content)
        self.assertEqual(response.json()['error'], 'stalePreview')
        self.send.assert_not_called()
        # nothing was persisted for the stale request — not even the valid ones
        self.assertEqual(GetMapProbe.objects.count(), 0)
        self.assertEqual(GetCapabilitiesProbe.objects.count(), 0)

    def test_candidate_removed_from_the_capabilities_is_refused_as_stale(self):
        candidates = self.default_candidates()
        stale = next(c for c in candidates if c['probeType'] == 'GetMap'
                     and c['targetLayer']['identifier'] == 'node1.1.3')
        # the capabilities change after the preview was fetched
        self.store(document=capabilities().replace(
            b'<Layer><Name>node1.1.3</Name></Layer>', b''))

        response = self.client.post(
            self.url(), self.payload(*candidates), format='json')

        self.assertEqual(response.status_code, 409, response.content)
        body = response.json()
        self.assertEqual(body['error'], 'stalePreview')
        self.assertEqual(body['candidates'], [stale['candidateId']])
        self.assertEqual(GetMapProbe.objects.count(), 0)

    def test_deactivated_layer_refuses_its_candidate(self):
        candidates = self.default_candidates()
        Layer.objects.filter(identifier='node1.2').update(is_active=False)

        response = self.client.post(
            self.url(), self.payload(*candidates), format='json')

        self.assertEqual(response.status_code, 409)
        self.assertEqual(GetMapProbe.objects.count(), 0)

    def test_foreign_generator_version_requires_a_fresh_preview(self):
        payload = self.payload(*self.default_candidates())
        payload['generatorVersion'] = '99.0.0'

        response = self.client.post(self.url(), payload, format='json')

        self.assertEqual(response.status_code, 409)
        body = response.json()
        self.assertEqual(body['error'], 'stalePreview')
        self.assertEqual(body['reason'], 'generatorVersion')
        self.assertEqual(GetMapProbe.objects.count(), 0)

    # --- preservation of manual and customized probes ---------------------------

    def test_manual_probes_are_never_touched(self):
        manual_caps = GetCapabilitiesProbe.objects.create(
            setting=self.setting, timeout=99)
        manual_map = GetMapProbe.objects.create(
            setting=self.setting, timeout=42, width=20)

        response = self.client.post(
            self.url(),
            self.payload(*self.default_candidates(), confirmReplace=True),
            format='json')

        self.assertEqual(response.status_code, 200, response.content)
        manual_caps.refresh_from_db()
        manual_map.refresh_from_db()
        self.assertEqual(manual_caps.timeout, 99)
        self.assertEqual(manual_map.timeout, 42)
        self.assertEqual(manual_map.width, 20)
        self.assertEqual(manual_caps.origin, ProbeOriginEnum.MANUAL)
        # the generated counterparts exist next to them
        self.assertEqual(GetCapabilitiesProbe.objects.count(), 2)
        self.assertEqual(
            GetCapabilitiesProbe.objects.filter(
                origin=ProbeOriginEnum.GENERATED).count(), 1)

    def test_customized_generated_parameters_are_preserved_without_confirmation(self):
        candidates = self.default_candidates()
        self.client.post(self.url(), self.payload(*candidates), format='json')
        # the operator tunes the generated probe afterwards
        probe = GetMapProbe.objects.get(
            layers__identifier='node1.2')
        probe.width = 77
        probe.save()

        response = self.client.post(
            self.url(), self.payload(*candidates), format='json')

        self.assertEqual(response.status_code, 200, response.content)
        result = response.json()
        self.assertEqual(result['summary']['preserved'], 1)
        self.assertEqual(result['replaceConfirmationRequired'],
                         [probe_parameters(self.preview(), 'GetMap',
                                           'node1.2')['candidateId']])
        probe.refresh_from_db()
        self.assertEqual(probe.width, 77)
        self.assertEqual(result['summary']['updated'], 0)

    def test_customization_is_only_replaced_after_explicit_confirmation(self):
        candidates = self.default_candidates()
        self.client.post(self.url(), self.payload(*candidates), format='json')
        probe = GetMapProbe.objects.get(layers__identifier='node1.2')
        probe.width = 77
        probe.save()

        response = self.client.post(
            self.url(),
            self.payload(*candidates, confirmReplace=True), format='json')

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()['summary']['updated'], 1)
        probe.refresh_from_db()
        self.assertEqual(probe.width, 256)

    def test_capabilities_change_below_the_identity_is_treated_as_customization(self):
        # a conservative read of the epic: the apply can not tell a user
        # edit from a capabilities change which kept the candidate identity,
        # so a differing regeneration is preserved, not overwritten
        candidates = self.default_candidates()
        self.client.post(self.url(), self.payload(*candidates), format='json')
        Layer.objects.filter(identifier='node1.2').update(
            bbox_lat_lon='SRID=4326;POLYGON ((3 1, 3 2, 4 2, 4 1, 3 1))')

        response = self.client.post(
            self.url(), self.payload(*candidates), format='json').json()

        self.assertEqual(response['summary']['preserved'], 1)
        probe = GetMapProbe.objects.get(layers__identifier='node1.2')
        self.assertEqual(
            [round(v, 2) for v in probe.bbox_lat_lon.extent],
            [-180.00, -90.00, 180.00, 90.00])

    # --- server side validation of the (edited) parameters -----------------------

    def test_edited_parameters_are_validated_against_the_current_capabilities(self):
        base = self.preview()
        cases = [
            ({'crs': 'EPSG:1234'}, 'crs'),
            ({'width': 4000}, 'width'),
            ({'height': 0}, 'height'),
            ({'timeout': 9999}, 'timeout'),
            ({'format': 'application/pdf'}, 'format'),
            ({'layers': ['node1.3']}, 'layers'),
            ({'bbox': [-200, -90, 0, 0]}, 'bbox'),
            ({'color': 'blue'}, 'parameters'),
        ]
        for edit, field in cases:
            with self.subTest(**edit):
                candidate = copy.deepcopy(
                    probe_parameters(base, 'GetMap', 'node1.2'))
                candidate['parameters'].update(edit)

                response = self.client.post(
                    self.url(), self.payload(candidate), format='json')

                self.assertEqual(response.status_code, 400, response.content)
                body = response.json()
                self.assertEqual(body['error'], 'parameters')
                self.assertEqual(body['field'], field)
        self.send.assert_not_called()
        self.assertEqual(GetMapProbe.objects.count(), 0)

    def test_body_shape_and_setting_are_validated(self):
        for overrides, code in [
                ({'setting': 'nope'}, 'setting'),
                ({'setting': str(self.setting.pk + 1000)}, 'setting'),
                ({'preset': 'kitchen-sink'}, 'preset'),
                ({'confirmReplace': 'yes'}, 'confirmReplace')]:
            with self.subTest(**{k: str(v) for k, v in overrides.items()}):
                response = self.client.post(
                    self.url(),
                    self.payload(*self.default_candidates(), **overrides),
                    format='json')
                self.assertEqual(response.status_code, 400, response.content)
                self.assertEqual(response.json()['error'], code)
        self.assertEqual(GetMapProbe.objects.count(), 0)

    def test_selection_is_bounded(self):
        # more candidates than the bound may never be applied at once
        payload = self.payload(*self.default_candidates())
        payload['probes'] = [
            {'candidateId': f'{index:020x}', 'probeType': 'GetMap',
             'parameters': {}}
            for index in range(101)]

        response = self.client.post(self.url(), payload, format='json')

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['error'], 'limit')
        self.send.assert_not_called()

    def test_duplicate_candidates_are_refused(self):
        candidate = probe_parameters(self.preview(), 'GetMap', 'node1.2')

        response = self.client.post(
            self.url(), self.payload(candidate, candidate), format='json')

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['error'], 'probes')

    # --- atomicity ---------------------------------------------------------------

    def test_a_failing_candidate_rolls_the_whole_apply_back(self):
        candidates = self.default_candidates()
        original = __import__(
            'registry.helper.monitoring_persistence',
            fromlist=['_apply_candidate'])._apply_candidate
        calls = []

        def explode(entry, *args, **kwargs):
            calls.append(entry['candidateId'])
            if len(calls) == 3:
                raise RuntimeError('simulated failure on the last candidate')
            return original(entry, *args, **kwargs)

        with patch('registry.helper.monitoring_persistence._apply_candidate',
                   side_effect=explode):
            with self.assertRaises(RuntimeError):
                self.client.post(self.url(), self.payload(*candidates),
                                 format='json')

        # the probes of the first two candidates did not survive
        self.assertEqual(GetMapProbe.objects.count(), 0)
        self.assertEqual(GetCapabilitiesProbe.objects.count(), 0)

    # --- permissions -------------------------------------------------------------

    def test_user_without_write_permission_is_rejected(self):
        user = get_user_model().objects.create_user(username='no-apply')
        assign_perm('view_webmapservice', user, self.wms)
        self.client.force_authenticate(user)

        response = self.client.post(
            self.url(), self.payload(*self.default_candidates()),
            format='json')

        self.assertEqual(response.status_code, 403)
        self.send.assert_not_called()
        self.assertEqual(GetMapProbe.objects.count(), 0)

    def test_writer_without_permission_on_the_service_object_is_rejected(self):
        # the candidates are collected while the client still acts as the
        # owner — the preview is not the subject of this test
        body = self.payload(*self.default_candidates())
        user = get_user_model().objects.create_user(username='model-writer')
        user.user_permissions.add(
            *user.user_permissions.model.objects.filter(
                codename__in=['change_webmapservice'],
                content_type__app_label='registry'))
        self.client.force_authenticate(user)

        response = self.client.post(self.url(), body, format='json')

        self.assertEqual(response.status_code, 403)
        self.assertEqual(GetMapProbe.objects.count(), 0)

    def test_writer_needs_the_setting_permission_too(self):
        body = self.payload(*self.default_candidates())
        user = get_user_model().objects.create_user(username='service-writer')
        user.user_permissions.add(
            *user.user_permissions.model.objects.filter(
                codename__in=['change_webmapservice'],
                content_type__app_label='registry'))
        assign_perm('change_webmapservice', user, self.wms)
        self.client.force_authenticate(user)

        response = self.client.post(self.url(), body, format='json')

        self.assertEqual(response.status_code, 403)
        self.assertEqual(GetMapProbe.objects.count(), 0)

    def test_assigned_writer_may_apply(self):
        body = self.payload(*self.default_candidates())
        user = get_user_model().objects.create_user(username='apply-writer')
        user.user_permissions.add(
            *user.user_permissions.model.objects.filter(
                codename__in=['change_webmapservice'],
                content_type__app_label='registry'))
        assign_perm('change_webmapservice', user, self.wms)
        assign_perm('change_webmapservicemonitoringsetting', user, self.setting)
        self.client.force_authenticate(user)

        response = self.client.post(self.url(), body, format='json')

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(GetMapProbe.objects.count(), 2)

    def test_anonymous_caller_is_rejected(self):
        # the guardian mapping of an anonymous request needs the
        # AnonymousUser row, which a preceding TransactionTestCase flushed
        get_user_model().objects.get_or_create(username='AnonymousUser')
        client = PlainJSONClient()
        client.credentials(HTTP_ACCEPT='application/json')

        response = client.post(
            self.url(), self.payload(*self.default_candidates()),
            format='json')

        self.assertEqual(response.status_code, 403)
        self.send.assert_not_called()
        self.assertEqual(GetMapProbe.objects.count(), 0)

    # --- routing and schema ---------------------------------------------------------

    def test_only_the_canonical_wms_route_offers_the_apply(self):
        for url in (f'/api/registry/wfs/{WMS}/monitoring-probes',
                    f'/api/registry/csw/{WMS}/monitoring-probes',
                    '/api/registry/service-metadata/wms/'
                    f'{WMS}/monitoring-probes'):
            with self.subTest(url=url):
                try:
                    match = resolve(url)
                except Resolver404:
                    continue
                # a resolvable nested route must not expose the action
                self.fail(f"{url} unexpectedly resolves to {match.view_name}")

    def test_the_schema_describes_the_apply_endpoint(self):
        from drf_spectacular.generators import SchemaGenerator

        # the full schema: exactly one POST under the canonical WMS route,
        # which also proves the nested viewsets do not expose the action
        schema = SchemaGenerator().get_schema(public=True)
        paths = [url for url in schema['paths']
                 if url.endswith('/wms/{id}/monitoring-probes')]

        self.assertEqual(len(paths), 1, schema['paths'].keys())
        self.assertIn('post', schema['paths'][paths[0]])
        self.assertIn('requestBody', schema['paths'][paths[0]]['post'])


class MonitoringProbeApplyConcurrencyTests(MonitoringProbeApplyTestsMixin,
                                           TransactionTestCase):
    """Concurrent applies of the same candidate must not duplicate it."""

    def test_concurrent_applies_create_exactly_one_probe_per_candidate(self):
        payload = self.payload(*self.default_candidates())
        results = {}

        def apply(index):
            try:
                client = PlainJSONClient()
                client.force_authenticate(self.user)
                client.credentials(HTTP_ACCEPT='application/json')
                response = client.post(self.url(), payload, format='json')
                results[index] = (response.status_code,
                                  response.json().get('summary'))
            except Exception as error:  # noqa: BLE001 - surfaced below
                results[index] = ('error', error)
            finally:
                connection.close()

        threads = [threading.Thread(target=apply, args=(index,))
                   for index in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=60)
            self.assertFalse(thread.is_alive(), 'apply deadlocked')

        self.assertEqual(len(results), 2)
        for outcome in results.values():
            self.assertNotEqual(outcome[0], 'error', outcome[1])
            self.assertEqual(outcome[0], 200, outcome[1])
            self.assertEqual(outcome[1]['created'] + outcome[1]['updated']
                             + outcome[1]['unchanged'], 3)
        # across both concurrent requests: one row per candidate, never more
        self.assertEqual(GetMapProbe.objects.count(), 2)
        self.assertEqual(GetCapabilitiesProbe.objects.count(), 1)


class MonitoringProbeRunnerIntegrationTests(MonitoringProbeApplyTestsMixin,
                                            TransactionTestCase):
    """Generated probes run through the current runner and their results
    appear in the current run endpoints."""

    @override_settings(CELERY_TASK_EAGER_PROPAGATES=True,
                       CELERY_TASK_ALWAYS_EAGER=True,
                       BROKER_BACKEND='memory')
    @patch('django.db.transaction.on_commit', side_effect=lambda f: f())
    @patch.object(target=OgcClient, attribute='send_request')
    def test_generated_probes_execute_in_a_monitoring_run(self, mocked_send,
                                                          _mocked_on_commit):
        # the same mocked OGC answers the monitoring task tests use
        from pathlib import Path

        test_data = Path(__file__).resolve().parent.parent / 'test_data'

        def side_effect(request, timeout):
            if 'GetCapabilities' in request.url:
                return MockResponse(
                    url=request.url, status_code=200,
                    content=test_data / 'dwd_wms_1.3.0.xml')
            return MockResponse(
                url=request.url, status_code=200,
                content=test_data / 'karte_rp.fcgi.png')

        mocked_send.side_effect = side_effect
        response = self.client.post(
            self.url(), self.payload(*self.default_candidates()),
            format='json')
        self.assertEqual(response.status_code, 200, response.content)
        self.send.stop()  # the run itself is allowed to send (mocked)

        run = WebMapServiceMonitoringRun.objects.create(setting=self.setting)

        self.assertEqual(
            run.registry_getcapabilitiesproberesults.count(), 1)
        self.assertEqual(run.registry_getmapproberesults.count(), 2)
        self.assertEqual(mocked_send.call_count, 3)

        # the results are answered by the current run endpoint — the JSON:API
        # renderer is selected through the client credentials, which the
        # APIClient applies over per-request headers
        self.client.credentials(HTTP_ACCEPT='application/vnd.api+json')
        detail = self.client.get(
            f'/api/registry/monitoring/wms-monitoring-runs/{run.pk}')
        self.assertEqual(detail.status_code, 200, detail.content)
        self.assertEqual(
            len(detail.json()['data']['relationships']['getMapProbeResults']
                ['data']), 2)


class MonitoringRunDispatchBoundTests(SimpleTestCase):
    """The dispatch of a run stays inside its execution bound."""

    def test_probe_tasks_are_dispatched_in_bounded_batches(self):
        from types import SimpleNamespace

        from registry.models.monitoring import GetMapProbe
        from registry.tasks.monitoring import (
            MAX_CONCURRENT_PROBE_REQUESTS, start_run)

        probes = [SimpleNamespace(_meta=GetMapProbe._meta, pk=index)
                  for index in range(25)]
        run = SimpleNamespace(
            _meta=SimpleNamespace(label_lower='registry.webmapservicemonitoringrun'),
            pk=1, report_process=lambda *a, **k: None)
        task = SimpleNamespace(s=lambda **kwargs: kwargs)

        with patch('registry.tasks.monitoring.group') as mocked_group, \
                patch('registry.tasks.monitoring.chain') as mocked_chain:
            start_run(run=run, probes=probes, task=task)

        batches = [call.args[0] for call in mocked_group.call_args_list]
        self.assertEqual(
            [len(batch) for batch in batches],
            [MAX_CONCURRENT_PROBE_REQUESTS, MAX_CONCURRENT_PROBE_REQUESTS, 5])
        chained = mocked_chain.call_args.args
        self.assertEqual(len(chained), mocked_group.call_count + 1)
        self.assertIs(chained[-2], mocked_group.return_value)
        mocked_chain.return_value.apply_async.assert_called_once_with()

    def test_a_run_without_probes_keeps_its_empty_group(self):
        from types import SimpleNamespace

        from registry.tasks.monitoring import start_run

        run = SimpleNamespace(
            _meta=SimpleNamespace(label_lower='registry.webmapservicemonitoringrun'),
            pk=1, report_process=lambda *a, **k: None)
        task = SimpleNamespace(s=lambda **kwargs: kwargs)

        with patch('registry.tasks.monitoring.group') as mocked_group, \
                patch('registry.tasks.monitoring.chain') as mocked_chain:
            start_run(run=run, probes=[], task=task)

        mocked_group.assert_called_once_with([])
        # the empty group stays the first link of the chain, finish_run last
        self.assertEqual(len(mocked_chain.call_args.args), 2)
        self.assertIs(mocked_chain.call_args.args[0],
                      mocked_group.return_value)
        mocked_chain.return_value.apply_async.assert_called_once_with()
