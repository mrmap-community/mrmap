from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from extras.fields import CrontabStringField
from extras.serializers import (StringRepresentationSerializer,
                                SystemInfoSerializerMixin)
from registry.models.metadata import ReferenceSystem
from registry.models.monitoring import (
    CatalogueServiceGetCapabilitiesProbe,
    CatalogueServiceGetCapabilitiesProbeResult,
    CatalogueServiceGetRecordsProbe,
    CatalogueServiceGetRecordsProbeResult,
    CatalogueServiceMonitoringRun, CatalogueServiceMonitoringSetting,
    GetCapabilitiesProbe,
    GetCapabilitiesProbeResult,
    GetMapProbe, GetMapProbeResult,
    WebFeatureServiceGetCapabilitiesProbe,
    WebFeatureServiceGetCapabilitiesProbeResult,
    WebFeatureServiceGetFeatureProbe,
    WebFeatureServiceGetFeatureProbeResult,
    WebFeatureServiceMonitoringRun,
    WebFeatureServiceMonitoringSetting,
    WebMapServiceMonitoringRun,
    WebMapServiceMonitoringSetting)
from registry.models.service import (CatalogueService, FeatureType, Layer,
                                     WebFeatureService, WebMapService)
from rest_framework.fields import DateTimeField, IntegerField, SerializerMethodField
from rest_framework_json_api.relations import ResourceRelatedField
from rest_framework_json_api.serializers import (BooleanField,
                                                 HyperlinkedIdentityField,
                                                 ModelSerializer)


class GetCapabilitiesProbeSerializer(
    StringRepresentationSerializer,
    SystemInfoSerializerMixin,
    ModelSerializer
):
    url = HyperlinkedIdentityField(
        view_name='registry:webmapservicemonitoring-getcapabilities-probe-detail',
    )
    timeout = IntegerField(
        default=30
    )

    class Meta:
        model = GetCapabilitiesProbe
        fields = (
            'url',
            'setting',
            'timeout',
            "check_response_is_valid_xml",
            "check_response_does_contain",
            'check_response_does_not_contain',
        )


class GetMapProbeSerializer(
    StringRepresentationSerializer,
    SystemInfoSerializerMixin,
    ModelSerializer
):
    url = HyperlinkedIdentityField(
        view_name='registry:webmapservicemonitoring-getmap-probe-detail',
    )
    timeout = IntegerField(
        default=30
    )
    layers = ResourceRelatedField(
        label=_("layers"),
        help_text=_("the setting which to used for this run."),
        many=True,
        queryset=Layer.objects,
    )
    reference_system = ResourceRelatedField(
        label=_("monitoring setting"),
        help_text=_("the setting which to used for this run."),
        many=True,
        queryset=ReferenceSystem.objects,
    )

    class Meta:
        model = GetMapProbe
        fields = (
            'url',
            'setting',
            'timeout',
            'layers',
            'reference_system',
            'height',
            'width',
            'bbox_lat_lon',
            "check_response_is_image",
            'check_response_does_not_contain',
        )


class MonitoringSettingSerializerMixin:
    """Mixin which reports the scheduled execution of a monitoring setting.

    Concrete serializers declare the `run_overdue` field themselves, as
    django-rest-framework only collects declared fields of serializer classes.
    """

    def get_run_overdue(self, obj) -> bool:
        current_time = timezone.now()
        if obj.expires is not None and obj.expires <= current_time:
            return False
        expected_at = obj.next_run_expected_at
        return expected_at is not None and expected_at < current_time


class WebMapServiceMonitoringSettingSerializer(
    MonitoringSettingSerializerMixin,
    StringRepresentationSerializer,
    SystemInfoSerializerMixin,
    ModelSerializer
):
    url = HyperlinkedIdentityField(
        view_name='registry:webmapservicemonitoringsetting-detail',
    )
    service = ResourceRelatedField(
        label=_("web map service"),
        help_text=_("the web map service for that this settings are."),
        queryset=WebMapService.objects,
    )
    schedule_interval = CrontabStringField(
        source='crontab',
        label=_("schedule interval"),
        help_text=_(
            "the schedule interval for this setting (e.g. '*/5 * * * *')."),
    )
    get_capabilitites_probes = ResourceRelatedField(
        many=True,
        source='registry_getcapabilitiesprobes',
        required=False,
        read_only=True,
    )
    get_map_probes = ResourceRelatedField(
        many=True,
        source='registry_getmapprobes',
        required=False,
        read_only=True,
    )

    last_run_at = DateTimeField(read_only=True, allow_null=True)
    next_run_expected_at = DateTimeField(read_only=True, allow_null=True)
    run_overdue = SerializerMethodField()

    class Meta:
        model = WebMapServiceMonitoringSetting
        fields = ('url', 'service', 'schedule_interval',
                  "get_capabilitites_probes", "get_map_probes", "enabled",
                  "last_run_at", "next_run_expected_at", "run_overdue")


class WebMapServiceMonitoringRunSerializer(
    StringRepresentationSerializer,
    SystemInfoSerializerMixin,
    ModelSerializer
):
    url = HyperlinkedIdentityField(
        view_name='registry:webmapservicemonitoringrun-detail',
    )
    success = BooleanField(
        label=_("Success"),
        help_text=_("false if any probe has failed"),
        read_only=True
    )
    setting = ResourceRelatedField(
        label=_("monitoring setting"),
        help_text=_("the setting which to used for this run."),
        queryset=WebMapServiceMonitoringSetting.objects,
    )
    get_capabilitites_probe_results = ResourceRelatedField(
        source="registry_getcapabilitiesproberesults",
        many=True,
        queryset=GetCapabilitiesProbeResult.objects,
        label=_("Get Capabilities Probe Results"),
        help_text=_("results for get capabilities requests"),
    )
    get_map_probe_results = ResourceRelatedField(
        source="registry_getmapproberesults",
        many=True,
        queryset=GetMapProbeResult.objects,
        label=_("Get Map Probe Results"),
        help_text=_("results for get map requests"),
    )

    class Meta:
        model = WebMapServiceMonitoringRun
        fields = (
            'url',
            'success',
            'setting',
            'get_capabilitites_probe_results',
            'get_map_probe_results',
            'date_created',
            'date_done'
        )


class GetCapabilitiesProbeResultSerializer(
    StringRepresentationSerializer,
    SystemInfoSerializerMixin,
    ModelSerializer
):
    url = HyperlinkedIdentityField(
        view_name='registry:webmapservicemonitoring-getcapabilities-probe-result-detail',
    )

    run = ResourceRelatedField(
        label=_("monitoring setting"),
        help_text=_("the setting which to used for this run."),
        queryset=WebMapServiceMonitoringRun.objects,
    )

    class Meta:
        model = GetCapabilitiesProbeResult
        fields = (
            'url',
            'run',
            'check_response_is_valid_xml_success',
            'check_response_is_valid_xml_message',
            'check_response_does_not_contain_success',
            'check_response_does_not_contain_message',
            'check_response_does_contain_success',
            'check_response_does_contain_message'
        )


class GetMapProbeResultSerializer(
    StringRepresentationSerializer,
    SystemInfoSerializerMixin,
    ModelSerializer
):
    url = HyperlinkedIdentityField(
        view_name='registry:webmapservicemonitoring-getmap-probe-result-detail',
    )
    run = ResourceRelatedField(
        label=_("monitoring setting"),
        help_text=_("the setting which to used for this run."),
        queryset=WebMapServiceMonitoringRun.objects,
    )

    class Meta:
        model = GetMapProbeResult
        fields = (
            'url',
            'run',
            'check_response_image_success',
            'check_response_image_message',
            'check_response_does_not_contain_success',
            'check_response_does_not_contain_message'
        )


class WebFeatureServiceMonitoringSettingSerializer(
    MonitoringSettingSerializerMixin,
    StringRepresentationSerializer,
    SystemInfoSerializerMixin,
    ModelSerializer
):
    url = HyperlinkedIdentityField(
        view_name='registry:webfeatureservicemonitoringsetting-detail',
    )
    service = ResourceRelatedField(
        label=_("web feature service"),
        help_text=_("the web feature service for that this settings are."),
        queryset=WebFeatureService.objects,
    )
    schedule_interval = CrontabStringField(
        source='crontab',
        label=_("schedule interval"),
        help_text=_(
            "the schedule interval for this setting (e.g. '*/5 * * * *')."),
    )
    get_capabilities_probes = ResourceRelatedField(
        many=True,
        source='registry_webfeatureservicegetcapabilitiesprobes',
        required=False,
        read_only=True,
    )
    get_feature_probes = ResourceRelatedField(
        many=True,
        source='registry_webfeatureservicegetfeatureprobes',
        required=False,
        read_only=True,
    )

    last_run_at = DateTimeField(read_only=True, allow_null=True)
    next_run_expected_at = DateTimeField(read_only=True, allow_null=True)
    run_overdue = SerializerMethodField()

    class Meta:
        model = WebFeatureServiceMonitoringSetting
        fields = ('url', 'service', 'schedule_interval',
                  "get_capabilities_probes", "get_feature_probes", "enabled",
                  "last_run_at", "next_run_expected_at", "run_overdue")


class WebFeatureServiceMonitoringRunSerializer(
    StringRepresentationSerializer,
    SystemInfoSerializerMixin,
    ModelSerializer
):
    url = HyperlinkedIdentityField(
        view_name='registry:webfeatureservicemonitoringrun-detail',
    )
    success = BooleanField(
        label=_("Success"),
        help_text=_("false if any probe has failed"),
        read_only=True
    )
    setting = ResourceRelatedField(
        label=_("monitoring setting"),
        help_text=_("the setting which to used for this run."),
        queryset=WebFeatureServiceMonitoringSetting.objects,
    )
    get_capabilities_probe_results = ResourceRelatedField(
        source="registry_webfeatureservicegetcapabilitiesproberesults",
        many=True,
        queryset=WebFeatureServiceGetCapabilitiesProbeResult.objects,
        label=_("Get Capabilities Probe Results"),
        help_text=_("results for get capabilities requests"),
    )
    get_feature_probe_results = ResourceRelatedField(
        source="registry_webfeatureservicegetfeatureproberesults",
        many=True,
        queryset=WebFeatureServiceGetFeatureProbeResult.objects,
        label=_("Get Feature Probe Results"),
        help_text=_("results for get feature requests"),
    )

    class Meta:
        model = WebFeatureServiceMonitoringRun
        fields = (
            'url',
            'success',
            'setting',
            'get_capabilities_probe_results',
            'get_feature_probe_results',
            'date_created',
            'date_done'
        )


class WebFeatureServiceGetCapabilitiesProbeSerializer(
    StringRepresentationSerializer,
    SystemInfoSerializerMixin,
    ModelSerializer
):
    url = HyperlinkedIdentityField(
        view_name='registry:webfeatureservicemonitoring-getcapabilities-probe-detail',
    )
    timeout = IntegerField(
        default=30
    )

    class Meta:
        model = WebFeatureServiceGetCapabilitiesProbe
        fields = (
            'url',
            'setting',
            'timeout',
            "check_response_is_valid_xml",
            "check_response_does_contain",
            'check_response_does_not_contain',
        )


class WebFeatureServiceGetFeatureProbeSerializer(
    StringRepresentationSerializer,
    SystemInfoSerializerMixin,
    ModelSerializer
):
    url = HyperlinkedIdentityField(
        view_name='registry:webfeatureservicemonitoring-getfeature-probe-detail',
    )
    timeout = IntegerField(
        default=30
    )
    feature_types = ResourceRelatedField(
        label=_("feature types"),
        help_text=_("the feature types which shall be requested."),
        many=True,
        queryset=FeatureType.objects,
    )
    reference_system = ResourceRelatedField(
        label=_("reference system"),
        help_text=_("the reference system of the requested features."),
        many=False,
        queryset=ReferenceSystem.objects,
        required=False,
        allow_null=True,
    )

    class Meta:
        model = WebFeatureServiceGetFeatureProbe
        fields = (
            'url',
            'setting',
            'timeout',
            'feature_types',
            'reference_system',
            'max_features',
            "check_response_is_valid_xml",
            "check_response_does_contain",
            'check_response_does_not_contain',
        )


class WebFeatureServiceGetCapabilitiesProbeResultSerializer(
    StringRepresentationSerializer,
    SystemInfoSerializerMixin,
    ModelSerializer
):
    url = HyperlinkedIdentityField(
        view_name='registry:webfeatureservicemonitoring-getcapabilities-probe-result-detail',
    )
    run = ResourceRelatedField(
        label=_("monitoring run"),
        help_text=_("the run which executed the probe."),
        queryset=WebFeatureServiceMonitoringRun.objects,
    )

    class Meta:
        model = WebFeatureServiceGetCapabilitiesProbeResult
        fields = (
            'url',
            'run',
            'check_response_is_valid_xml_success',
            'check_response_is_valid_xml_message',
            'check_response_does_contain_success',
            'check_response_does_contain_message',
            'check_response_does_not_contain_success',
            'check_response_does_not_contain_message'
        )


class WebFeatureServiceGetFeatureProbeResultSerializer(
    StringRepresentationSerializer,
    SystemInfoSerializerMixin,
    ModelSerializer
):
    url = HyperlinkedIdentityField(
        view_name='registry:webfeatureservicemonitoring-getfeature-probe-result-detail',
    )
    run = ResourceRelatedField(
        label=_("monitoring run"),
        help_text=_("the run which executed the probe."),
        queryset=WebFeatureServiceMonitoringRun.objects,
    )

    class Meta:
        model = WebFeatureServiceGetFeatureProbeResult
        fields = (
            'url',
            'run',
            'check_response_is_valid_xml_success',
            'check_response_is_valid_xml_message',
            'check_response_does_contain_success',
            'check_response_does_contain_message',
            'check_response_does_not_contain_success',
            'check_response_does_not_contain_message'
        )


class CatalogueServiceMonitoringSettingSerializer(
    MonitoringSettingSerializerMixin,
    StringRepresentationSerializer,
    SystemInfoSerializerMixin,
    ModelSerializer
):
    url = HyperlinkedIdentityField(
        view_name='registry:catalogueservicemonitoringsetting-detail',
    )
    service = ResourceRelatedField(
        label=_("catalogue service"),
        help_text=_("the catalogue service for that this settings are."),
        queryset=CatalogueService.objects,
    )
    schedule_interval = CrontabStringField(
        source='crontab',
        label=_("schedule interval"),
        help_text=_(
            "the schedule interval for this setting (e.g. '*/5 * * * *')."),
    )
    get_capabilities_probes = ResourceRelatedField(
        many=True,
        source='registry_catalogueservicegetcapabilitiesprobes',
        required=False,
        read_only=True,
    )
    get_records_probes = ResourceRelatedField(
        many=True,
        source='registry_catalogueservicegetrecordsprobes',
        required=False,
        read_only=True,
    )

    last_run_at = DateTimeField(read_only=True, allow_null=True)
    next_run_expected_at = DateTimeField(read_only=True, allow_null=True)
    run_overdue = SerializerMethodField()

    class Meta:
        model = CatalogueServiceMonitoringSetting
        fields = ('url', 'service', 'schedule_interval',
                  "get_capabilities_probes", "get_records_probes", "enabled",
                  "last_run_at", "next_run_expected_at", "run_overdue")


class CatalogueServiceMonitoringRunSerializer(
    StringRepresentationSerializer,
    SystemInfoSerializerMixin,
    ModelSerializer
):
    url = HyperlinkedIdentityField(
        view_name='registry:catalogueservicemonitoringrun-detail',
    )
    success = BooleanField(
        label=_("Success"),
        help_text=_("false if any probe has failed"),
        read_only=True
    )
    setting = ResourceRelatedField(
        label=_("monitoring setting"),
        help_text=_("the setting which to used for this run."),
        queryset=CatalogueServiceMonitoringSetting.objects,
    )
    get_capabilities_probe_results = ResourceRelatedField(
        source="registry_catalogueservicegetcapabilitiesproberesults",
        many=True,
        queryset=CatalogueServiceGetCapabilitiesProbeResult.objects,
        label=_("Get Capabilities Probe Results"),
        help_text=_("results for get capabilities requests"),
    )
    get_records_probe_results = ResourceRelatedField(
        source="registry_catalogueservicegetrecordsproberesults",
        many=True,
        queryset=CatalogueServiceGetRecordsProbeResult.objects,
        label=_("Get Records Probe Results"),
        help_text=_("results for get records requests"),
    )

    class Meta:
        model = CatalogueServiceMonitoringRun
        fields = (
            'url',
            'success',
            'setting',
            'get_capabilities_probe_results',
            'get_records_probe_results',
            'date_created',
            'date_done'
        )


class CatalogueServiceGetCapabilitiesProbeSerializer(
    StringRepresentationSerializer,
    SystemInfoSerializerMixin,
    ModelSerializer
):
    url = HyperlinkedIdentityField(
        view_name='registry:catalogueservicemonitoring-getcapabilities-probe-detail',
    )
    timeout = IntegerField(
        default=30
    )

    class Meta:
        model = CatalogueServiceGetCapabilitiesProbe
        fields = (
            'url',
            'setting',
            'timeout',
            "check_response_is_valid_xml",
            "check_response_does_contain",
            'check_response_does_not_contain',
        )


class CatalogueServiceGetRecordsProbeSerializer(
    StringRepresentationSerializer,
    SystemInfoSerializerMixin,
    ModelSerializer
):
    url = HyperlinkedIdentityField(
        view_name='registry:catalogueservicemonitoring-getrecords-probe-detail',
    )
    timeout = IntegerField(
        default=30
    )

    class Meta:
        model = CatalogueServiceGetRecordsProbe
        fields = (
            'url',
            'setting',
            'timeout',
            'type_names',
            'result_type',
            'element_set_name',
            'max_records',
            "check_response_is_valid_xml",
            "check_response_does_contain",
            'check_response_does_not_contain',
        )


class CatalogueServiceGetCapabilitiesProbeResultSerializer(
    StringRepresentationSerializer,
    SystemInfoSerializerMixin,
    ModelSerializer
):
    url = HyperlinkedIdentityField(
        view_name='registry:catalogueservicemonitoring-getcapabilities-probe-result-detail',
    )
    run = ResourceRelatedField(
        label=_("monitoring run"),
        help_text=_("the run which executed the probe."),
        queryset=CatalogueServiceMonitoringRun.objects,
    )

    class Meta:
        model = CatalogueServiceGetCapabilitiesProbeResult
        fields = (
            'url',
            'run',
            'check_response_is_valid_xml_success',
            'check_response_is_valid_xml_message',
            'check_response_does_contain_success',
            'check_response_does_contain_message',
            'check_response_does_not_contain_success',
            'check_response_does_not_contain_message'
        )


class CatalogueServiceGetRecordsProbeResultSerializer(
    StringRepresentationSerializer,
    SystemInfoSerializerMixin,
    ModelSerializer
):
    url = HyperlinkedIdentityField(
        view_name='registry:catalogueservicemonitoring-getrecords-probe-result-detail',
    )
    run = ResourceRelatedField(
        label=_("monitoring run"),
        help_text=_("the run which executed the probe."),
        queryset=CatalogueServiceMonitoringRun.objects,
    )

    class Meta:
        model = CatalogueServiceGetRecordsProbeResult
        fields = (
            'url',
            'run',
            'check_response_is_valid_xml_success',
            'check_response_is_valid_xml_message',
            'check_response_does_contain_success',
            'check_response_does_contain_message',
            'check_response_does_not_contain_success',
            'check_response_does_not_contain_message'
        )
