"""Domain steps of the monitoring probe preview and apply scenarios.

The endpoints `api/registry/{wms,wfs}/<id>/monitoring-probe-preview` and
`.../monitoring-probes` propose probes from the stored capabilities and persist
the candidates an API client selects from them onto an existing monitoring
setting. These steps set up the state the plain JSON endpoints need — stored
capabilities, a setting, the object permissions of the actor — and assert what
the apply owes the database: idempotent writes which only ever touch the
generated probes of the selected setting.

Both generated service kinds share the vocabulary: the kind is chosen by the
capabilities step a scenario starts with, which is what decides the models the
other steps read.
"""
import json

from behave import given, then
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django_celery_beat.models import CrontabSchedule
from guardian.shortcuts import assign_perm
from registry.enums.monitoring import ProbeOriginEnum
from registry.models.monitoring import (
    GetCapabilitiesProbe, GetFeatureInfoProbe, GetMapProbe,
    WebFeatureServiceDescribeFeatureTypeProbe,
    WebFeatureServiceGetCapabilitiesProbe, WebFeatureServiceGetFeatureProbe,
    WebFeatureServiceMonitoringSetting, WebMapServiceMonitoringSetting)
from registry.models.service import WebFeatureService, WebMapService

WMS_ID = 'cd16cc1f-3abb-4625-bb96-fbe80dbe23e3'
WFS_ID = '9cc4889d-0cd4-4c3b-8975-58de6d30db41'

#: the models and permissions of each generated service kind, keyed by the
#: kind the capabilities step of a scenario selects
KIND = {
    'wms': {
        'service_model': WebMapService,
        'service_pk': WMS_ID,
        'setting_model': WebMapServiceMonitoringSetting,
        'permissions': ('view_webmapservice', 'change_webmapservice',
                        'change_webmapservicemonitoringsetting'),
    },
    'wfs': {
        'service_model': WebFeatureService,
        'service_pk': WFS_ID,
        'setting_model': WebFeatureServiceMonitoringSetting,
        'permissions': ('view_webfeatureservice', 'change_webfeatureservice',
                        'change_webfeatureservicemonitoringsetting'),
    },
}

#: the probe model of every generatable probe type
PROBE_MODEL = {
    'GetCapabilities': GetCapabilitiesProbe,
    'GetMap': GetMapProbe,
    'GetFeatureInfo': GetFeatureInfoProbe,
    'WfsGetCapabilities': WebFeatureServiceGetCapabilitiesProbe,
    'GetFeature': WebFeatureServiceGetFeatureProbe,
    'DescribeFeatureType': WebFeatureServiceDescribeFeatureTypeProbe,
}

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

#: the feature types the WFS capabilities below advertises
GML = 'application/gml+xml; version=3.2'


def _wfs_operation(name, formats=()):
    """One OWS Common operation with its GET endpoint and output formats."""
    values = ''.join(f'<ows:Value>{value}</ows:Value>' for value in formats)
    parameter = (f'<ows:Parameter name="outputFormat"><ows:AllowedValues>'
                 f'{values}</ows:AllowedValues></ows:Parameter>'
                 if values else '')
    return (f'<ows:Operation name="{name}"><ows:DCP><ows:HTTP>'
            f'<ows:Get xlink:href="https://registered.example/wfs?"/>'
            f'</ows:HTTP></ows:DCP>{parameter}</ows:Operation>')


def _wfs_feature_type(name):
    """One advertised feature type with its default CRS and output format."""
    return f"""
        <wfs:FeatureType>
            <wfs:Name>{name}</wfs:Name>
            <wfs:Title>{name}</wfs:Title>
            <wfs:DefaultCRS>urn:ogc:def:crs:EPSG::4326</wfs:DefaultCRS>
            <wfs:OutputFormats><wfs:Format>{GML}</wfs:Format>
            </wfs:OutputFormats>
        </wfs:FeatureType>"""


WFS_CAPABILITIES = """
    <wfs:WFS_Capabilities version="2.0.0" serviceType="WFS"
        xmlns:wfs="http://www.opengis.net/wfs/2.0"
        xmlns:ows="http://www.opengis.net/ows/1.1"
        xmlns:xlink="http://www.w3.org/1999/xlink">
        <ows:OperationsMetadata>
            {get_capabilities}
            {get_feature}
            {describe}
        </ows:OperationsMetadata>
        <wfs:FeatureTypeList>
            {feature_types}
        </wfs:FeatureTypeList>
    </wfs:WFS_Capabilities>""".format(
    get_capabilities=_wfs_operation('GetCapabilities', ['text/xml']),
    get_feature=_wfs_operation('GetFeature', [GML]),
    describe=_wfs_operation('DescribeFeatureType', [GML]),
    feature_types=''.join(_wfs_feature_type(name)
                          for name in ('node2', 'node3', 'wfs1-node1'))
).encode()


def _document(kind):
    return WFS_CAPABILITIES if kind == 'wfs' else CAPABILITIES


def _candidate(preview, probe_type, identifier=None):
    """The full preview probe of one type (optionally of one target)."""
    for probe in preview['probes']:
        if probe['probeType'] != probe_type:
            continue
        target = probe.get('targetLayer') or probe.get('targetFeatureType')
        if identifier is None and probe_type == 'GetCapabilities':
            return probe
        if target and target['identifier'] == identifier:
            return probe
    raise AssertionError(f"preview has no {probe_type} probe")


def _apply_body(context, probes):
    return json.dumps({
        'setting': str(context.setting.pk),
        'preset': getattr(context, 'preset', 'standard'),
        'probes': probes,
    })


@given('the WMS stores a capabilities document')
def store_wms_capabilities(context):
    _store_capabilities(context, 'wms')


@given('the WFS stores a capabilities document')
def store_wfs_capabilities(context):
    _store_capabilities(context, 'wfs')


def _store_capabilities(context, kind):
    context.kind = kind
    spec = KIND[kind]
    context.service = spec['service_model'].objects.get(pk=spec['service_pk'])
    context.service.xml_backup_file = SimpleUploadedFile(
        'probes.xml', _document(kind))
    context.service.save()


@given('a monitoring setting exists for the service')
def create_monitoring_setting(context):
    context.setting = KIND[context.kind]['setting_model'].objects.create(
        service=context.service, enabled=False,
        crontab=CrontabSchedule.objects.create(minute='*/5', hour='*'))


@given('{username} may change the service and the monitoring setting')
def grant_object_permissions(context, username):
    user = get_user_model().objects.get(username=username)
    for permission in KIND[context.kind]['permissions']:
        target = (context.setting
                  if permission.endswith('monitoringsetting')
                  else context.service)
        assign_perm(permission, user, target)


@given('I fetch the monitoring probe preview for the service')
def fetch_preview(context):
    url = (f'http://localhost:8000/api/registry/{context.kind}/'
           f'{context.service.pk}/monitoring-probe-preview')
    preset = getattr(context, 'preset', None)
    if preset:
        url = f'{url}?preset={preset}'
    response = context.client.get(url, HTTP_ACCEPT='application/json')
    assert response.status_code == 200, response.content
    context.preview = response.json()


@given('the preview and the apply use the "{preset}" preset')
def choose_preset(context, preset):
    context.preset = preset


@given('I select the GetCapabilities probe and the GetMap probe of layer '
       '"{identifier}" from the preview')
def select_wms_probes(context, identifier):
    context.payload = _apply_body(context, _bodies([
        _candidate(context.preview, 'GetCapabilities'),
        _candidate(context.preview, 'GetMap', identifier)]))


@given('I select the GetCapabilities probe and the GetFeature probe of feature '
       'type "{identifier}" from the preview')
def select_wfs_probes(context, identifier):
    context.payload = _apply_body(context, _bodies([
        _candidate(context.preview, 'GetCapabilities'),
        _candidate(context.preview, 'GetFeature', identifier)]))


@given('I select the GetFeature and the DescribeFeatureType probe of feature '
       'type "{identifier}" from the preview')
def select_comprehensive_wfs_probes(context, identifier):
    context.payload = _apply_body(context, _bodies([
        _candidate(context.preview, 'GetFeature', identifier),
        _candidate(context.preview, 'DescribeFeatureType', identifier)]))


def _bodies(probes):
    """The candidate entries the apply endpoint takes."""
    return [{'candidateId': probe['candidateId'],
             'probeType': probe['probeType'],
             'parameters': probe['parameters']}
            for probe in probes]


@given('an apply payload with a fabricated candidate')
@given('an apply payload with a fabricated {probe_type} candidate')
def fabricated_payload(context, probe_type='GetMap'):
    context.payload = _apply_body(context, [
        {'candidateId': 'f' * 20, 'probeType': probe_type,
         'parameters': {}}])


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
    model = PROBE_MODEL[probe_type]
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


@then('the preview proposes "{count}" {probe_type} probes')
def count_proposed(context, count, probe_type):
    proposed = [probe for probe in context.preview['probes']
                if probe['probeType'] == probe_type]
    assert len(proposed) == int(count), [
        probe['probeType'] for probe in context.preview['probes']]


@then('the preview offers the versions "{versions}"')
def assert_supported_versions(context, versions):
    # the generator only offers the versions whose requests it can really
    # build and execute — see the honest version matrix of the WFS generator
    expected = [item.strip() for item in versions.split(',') if item.strip()]
    assert context.preview['supportedVersions'] == expected, \
        context.preview['supportedVersions']


@then('the preview skips the feature type "{identifier}" as "{reason}"')
def assert_skipped(context, identifier, reason):
    skipped = [skip for skip in context.preview['skipped']
               if skip.get('featureType') == identifier]
    assert [skip['reason'] for skip in skipped] == [reason], skipped


@then('the proposed GetFeature request asks for "{count}" features at most')
def assert_bounded_request(context, count):
    probe = _candidate(context.preview, 'GetFeature', 'node2')
    assert probe['parameters']['maxFeatures'] == int(count), probe['parameters']
    assert probe['supported']['maxFeatures'] >= int(count), probe['supported']
