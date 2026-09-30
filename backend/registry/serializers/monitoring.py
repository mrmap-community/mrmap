from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from extras.fields import CrontabStringField
from extras.serializers import (StringRepresentationSerializer,
                                SystemInfoSerializerMixin)
from registry.models.metadata import ReferenceSystem
from registry.models.monitoring import (GetCapabilitiesProbe,
                                        GetCapabilitiesProbeResult,
                                        GetMapProbe, GetMapProbeResult,
                                        WebMapServiceMonitoringRun,
                                        WebMapServiceMonitoringSetting)
from registry.models.service import Layer, WebMapService
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


class WebMapServiceMonitoringSettingSerializer(
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

    def get_run_overdue(self, obj) -> bool:
        current_time = timezone.now()
        if obj.expires is not None and obj.expires <= current_time:
            return False
        expected_at = obj.next_run_expected_at
        return expected_at is not None and expected_at < current_time

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
