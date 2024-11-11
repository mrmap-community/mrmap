from django.utils.translation import gettext_lazy as _
from extras.serializers import StringRepresentationSerializer
from registry.models.monitoring import (GetCapabilititesProbe,
                                        GetCapabilititesProbeResult,
                                        GetMapProbe, GetMapProbeResult,
                                        WebMapServiceMonitoringRun,
                                        WebMapServiceMonitoringSetting)
from registry.models.service import Layer, WebMapService
from rest_framework_json_api.relations import ResourceRelatedField
from rest_framework_json_api.serializers import (BooleanField,
                                                 HyperlinkedIdentityField,
                                                 ModelSerializer)

from mrmap.registry.models.metadata import ReferenceSystem


class WebMapServiceMonitoringSettingSerializer(
    StringRepresentationSerializer,
    ModelSerializer
):
    url = HyperlinkedIdentityField(
        view_name='registry:wms-monitoring-setting-detail',
    )
    service = ResourceRelatedField(
        label=_("web map service"),
        help_text=_("the web map service for that this settings are."),
        model=WebMapService,
    )
    crontab = ResourceRelatedField(
        label=_("crontab"),
        help_text=_("the crontab configuration for this setting."),
        model=WebMapService,
    )

    class Meta:
        model = WebMapServiceMonitoringSetting
        fields = ('url', 'name', 'service', 'crontab')


class WebMapServiceMonitoringRunSerializer(
    StringRepresentationSerializer,
    ModelSerializer
):
    url = HyperlinkedIdentityField(
        view_name='registry:wms-monitoring-run-detail',
    )
    success = BooleanField(
        label=_("Success"),
        help_text=_("false if any probe has failed"),
        read_only=True
    )
    setting = ResourceRelatedField(
        label=_("monitoring setting"),
        help_text=_("the setting which to used for this run."),
        model=WebMapService,
    )
    registry_getcapabilititesproberesults = ResourceRelatedField(
        many=True,
        queryset=GetCapabilititesProbeResult.objects,
        label=_("Get Capabilities Probe Results"),
        help_text=_("results for get capabilities requests"),
    )
    registry_getmapproberesults = ResourceRelatedField(
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
            'registry_getcapabilititesproberesults',
            'registry_getmapproberesults'
        )


class GetCapabilititesProbeResultSerializer(
    StringRepresentationSerializer,
    ModelSerializer
):
    url = HyperlinkedIdentityField(
        view_name='registry:wms-monitoring-getcapresult-detail',
    )
    run = ResourceRelatedField(
        label=_("monitoring setting"),
        help_text=_("the setting which to used for this run."),
        model=WebMapServiceMonitoringRun,
    )

    class Meta:
        model = GetCapabilititesProbeResult
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
        view_name='registry:wms-monitoring-getmapresult-detail',
    )
    run = ResourceRelatedField(
        label=_("monitoring setting"),
        help_text=_("the setting which to used for this run."),
        model=WebMapServiceMonitoringRun,
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


class GetCapabilititesProbeSerializer(
    StringRepresentationSerializer,
    ModelSerializer
):
    url = HyperlinkedIdentityField(
        view_name='registry:wms-monitoring-getmapprobe-detail',
    )

    class Meta:
        model = GetCapabilititesProbe
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
        view_name='registry:wms-monitoring-getmapprobe-detail',
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
