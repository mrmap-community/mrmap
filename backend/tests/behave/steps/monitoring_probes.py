"""Domain steps of the monitoring probe apply scenarios.

The apply endpoint of `api/registry/wms/<id>/monitoring-probes` consumes the
candidates of the monitoring probe preview and persists them onto an existing
monitoring setting. These steps set up the state the plain JSON endpoint needs
— stored capabilities, a setting, the object permissions of the actor — and
assert what the apply owes the database: idempotent writes which only ever
touch the generated probes of the selected setting.
"""
import json

from behave import given, then
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django_celery_beat.models import CrontabSchedule
from guardian.shortcuts import assign_perm
from registry.enums.monitoring import ProbeOriginEnum
from registry.models.monitoring import (GetCapabilitiesProbe, GetMapProbe,
                                        WebMapServiceMonitoringSetting)
from registry.models.service import WebMapService

WMS_ID = 'cd16cc1f-3abb-4625-bb96-fbe80dbe23e3'

PREVIEW_URL = (f'http://localhost:8000/api/registry/wms/{WMS_ID}'
               '/monitoring-probe-preview')

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


def _candidate(preview, probe_type, identifier=None):
    """The full preview probe of one type (optionally of one layer)."""
    for probe in preview['probes']:
        if probe['probeType'] != probe_type:
            continue
        target = probe.get('targetLayer')
        if identifier is None and probe_type == 'GetCapabilities':
            return probe
        if target and target['identifier'] == identifier:
            return probe
    raise AssertionError(f"preview has no {probe_type} probe")


def _apply_body(context, probes):
    return json.dumps({
        'setting': str(context.setting.pk),
        'preset': 'standard',
        'probes': probes,
    })


@given('the WMS stores a capabilities document')
def store_capabilities(context):
    context.wms = WebMapService.objects.get(pk=WMS_ID)
    context.wms.xml_backup_file = SimpleUploadedFile('probes.xml',
                                                     CAPABILITIES)
    context.wms.save()


@given('a monitoring setting exists for the service')
def create_monitoring_setting(context):
    context.setting = WebMapServiceMonitoringSetting.objects.create(
        service=context.wms, enabled=False,
        crontab=CrontabSchedule.objects.create(minute='*/5', hour='*'))


@given('{username} may change the service and the monitoring setting')
def grant_object_permissions(context, username):
    user = get_user_model().objects.get(username=username)
    assign_perm('view_webmapservice', user, context.wms)
    assign_perm('change_webmapservice', user, context.wms)
    assign_perm('change_webmapservicemonitoringsetting', user,
                context.setting)


@given('I fetch the monitoring probe preview for the service')
def fetch_preview(context):
    response = context.client.get(PREVIEW_URL,
                                  HTTP_ACCEPT='application/json')
    assert response.status_code == 200, response.content
    context.preview = response.json()


@given('I select the GetCapabilities probe and the GetMap probe of layer '
       '"{identifier}" from the preview')
def select_probes(context, identifier):
    probes = [_candidate(context.preview, 'GetCapabilities'),
              _candidate(context.preview, 'GetMap', identifier)]
    context.payload = _apply_body(context, [
        {'candidateId': probe['candidateId'],
         'probeType': probe['probeType'],
         'parameters': probe['parameters']}
        for probe in probes])


@given('an apply payload with a fabricated candidate')
def fabricated_payload(context):
    context.payload = _apply_body(context, [
        {'candidateId': 'f' * 20, 'probeType': 'GetMap', 'parameters': {}}])


@given('the generated GetMap probe of layer "{identifier}" is customized to '
       'width "{width}"')
def customize_probe(context, identifier, width):
    probe = GetMapProbe.objects.get(
        setting=context.setting, origin=ProbeOriginEnum.GENERATED,
        layers__identifier=identifier)
    probe.width = int(width)
    probe.save()


@then('the setting has "{count}" generated {probe_type} probes')
def count_generated(context, count, probe_type):
    model = {'GetMap': GetMapProbe,
             'GetCapabilities': GetCapabilitiesProbe}[probe_type]
    assert model.objects.filter(
        setting=context.setting,
        origin=ProbeOriginEnum.GENERATED).count() == int(count)


@then('the generated GetMap probe of layer "{identifier}" still has width '
      '"{width}"')
def assert_width(context, identifier, width):
    probe = GetMapProbe.objects.get(
        setting=context.setting, origin=ProbeOriginEnum.GENERATED,
        layers__identifier=identifier)
    assert probe.width == int(width), probe.width


@then('the setting is not enabled')
def assert_not_enabled(context):
    context.setting.refresh_from_db()
    assert not context.setting.enabled
