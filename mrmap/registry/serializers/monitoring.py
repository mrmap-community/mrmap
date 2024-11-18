from django.utils.translation import gettext_lazy as _
from django_celery_beat.models import CrontabSchedule
from extras.serializers import StringRepresentationSerializer
from registry.models.metadata import ReferenceSystem
from registry.models.monitoring import (GetCapabilitiesProbe,
                                        GetCapabilitiesProbeResult,
                                        GetMapProbe, GetMapProbeResult,
                                        WebMapServiceMonitoringRun,
                                        WebMapServiceMonitoringSetting)
from registry.models.service import Layer, WebMapService
from rest_framework.fields import IntegerField
from rest_framework_json_api.relations import ResourceRelatedField
from rest_framework_json_api.serializers import (BooleanField,
                                                 HyperlinkedIdentityField,
                                                 ModelSerializer)


class WebMapServiceMonitoringSettingSerializer(
    StringRepresentationSerializer,
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
    crontab = ResourceRelatedField(
        label=_("crontab"),
        help_text=_("the crontab configuration for this setting."),
        queryset=CrontabSchedule.objects
    )
    get_capabilitites_probes = ResourceRelatedField(
        many=True,
        required=False,
        queryset=GetCapabilitiesProbe.objects,
        label=_("Get Capabilitites Probes"),
        help_text=_("Add probes to check get capabilitites"),
    )
    get_map_probes = ResourceRelatedField(
        many=True,
        required=False,
        queryset=GetMapProbe.objects,
        label=_("Get Map Probes"),
        help_text=_("Add probes to check get map"),
    )

    class Meta:
        model = WebMapServiceMonitoringSetting
        fields = ('url', 'name', 'service', 'crontab',
                  "get_capabilitites_probes", "get_map_probes")


class WebMapServiceMonitoringRunSerializer(
    StringRepresentationSerializer,
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
        queryset=WebMapService.objects,
    )
    get_capabilitites_probe_results = ResourceRelatedField(
        source="registry_getcapabilitiesproberesult",
        many=True,
        queryset=GetCapabilitiesProbeResult.objects,
        label=_("Get Capabilities Probe Results"),
        help_text=_("results for get capabilities requests"),
    )
    get_map_probe_results = ResourceRelatedField(
        source="registry_getmapproberesult",
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
            'get_map_probe_results'
        )


class GetCapabilitiesProbeResultSerializer(
    StringRepresentationSerializer,
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


class GetCapabilitiesProbeSerializer(
    StringRepresentationSerializer,
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
            'timeout',
            "check_response_is_valid_xml",
            "check_response_does_contain"
        )


class GetMapProbeSerializer(
    StringRepresentationSerializer,
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
            'timeout',
            'layers',
            'reference_system',
            'height',
            'width',
            'bbox_lat_lon',
            "check_response_is_image",
        )
