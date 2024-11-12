from django.db.models.query import Prefetch
from extras.permissions import DjangoObjectPermissionsOrAnonReadOnly
from registry.models.monitoring import (GetCapabilititesProbe,
                                        GetCapabilititesProbeResult,
                                        GetMapProbe, GetMapProbeResult,
                                        WebMapServiceMonitoringRun,
                                        WebMapServiceMonitoringSetting)
from registry.serializers.monitoring import (
    GetCapabilititesProbeResultSerializer, GetCapabilititesProbeSerializer,
    GetMapProbeResultSerializer, GetMapProbeSerializer,
    WebMapServiceMonitoringRunSerializer,
    WebMapServiceMonitoringSettingSerializer)
from rest_framework_json_api.views import ModelViewSet


class WebMapServiceMonitoringSettingViewSet(
    ModelViewSet,
):
    """ Endpoints for resource `WebMapServiceMonitoringSetting`

        create:
            Endpoint to register new `WebMapServiceMonitoringSetting` object
        list:
            Retrieves all registered `WebMapServiceMonitoringSetting` objects
        retrieve:
            Retrieve one specific `WebMapServiceMonitoringSetting` by the given id
        partial_update:
            Endpoint to update some fields of a `WebMapServiceMonitoringSetting`
        destroy:
            Endpoint to remove a registered `WebMapServiceMonitoringSetting` from the system
    """
    permission_classes = [DjangoObjectPermissionsOrAnonReadOnly]
    queryset = WebMapServiceMonitoringSetting.objects.all()
    serializer_class = WebMapServiceMonitoringSettingSerializer
    select_for_includes = {
        "service": ["service"],
        "crontab": ["crontab"],
    }
    prefetch_for_includes = {
        "registry_getcapabilititesprobes": [
            Prefetch(
                "registry_getcapabilititesprobes",
                queryset=GetCapabilititesProbe.objects.all()
            )
        ],
        "registry_getmapprobes": [
            Prefetch(
                "registry_getmapprobes",
                queryset=GetMapProbe.objects.all()
            )
        ],
    }
    filterset_fields = {
        'id': ['exact', 'icontains', 'contains', 'in'],
        'service__id': ['exact', 'icontains', 'contains', 'in'],
        'service__title': ['exact', 'icontains', 'contains'],
    }
    search_fields = ("id", "service", "service__title")
    ordering_fields = ["id", "name", "service"]


class WebMapServiceMonitoringRunViewSet(
    ModelViewSet,
):
    """ Endpoints for resource `WebMapServiceMonitoringRun`

        create:
            Endpoint to register new `WebMapServiceMonitoringRun` object
        list:
            Retrieves all registered `WebMapServiceMonitoringRun` objects
        retrieve:
            Retrieve one specific `WebMapServiceMonitoringRun` by the given id
        partial_update:
            Endpoint to update some fields of a `WebMapServiceMonitoringRun`
        destroy:
            Endpoint to remove a registered `WebMapServiceMonitoringRun` from the system
    """
    permission_classes = [DjangoObjectPermissionsOrAnonReadOnly]
    queryset = WebMapServiceMonitoringRun.objects.all()
    serializer_class = WebMapServiceMonitoringRunSerializer
    select_for_includes = {
        "setting": ["setting"],
    }
    prefetch_for_includes = {
        "registry_getcapabilititesproberesults": [
            Prefetch(
                "registry_getcapabilititesproberesults",
                queryset=GetCapabilititesProbeResult.objects.all().select_related("run")
            )
        ],
        "registry_getmapproberesults": [
            Prefetch(
                "registry_getmapproberesults",
                queryset=GetMapProbeResult.objects.all().select_related("run")
            )
        ],
    }
    filterset_fields = {
        'id': ['exact', 'icontains', 'contains', 'in'],
        # 'success': ['exact'],
        'setting__id': ['exact', 'icontains', 'contains', 'in'],
        # 'get_capabilitites_probe_results__id': ['exact', 'icontains', 'contains', 'in'],
        # 'get_map_probe_results__id': ['exact', 'icontains', 'contains', 'in'],

    }
    search_fields = ("id", "success", "setting__service__title")
    ordering_fields = ["id", "success"]


class GetCapabilititesProbeResultViewSet(
    ModelViewSet,
):
    """ Endpoints for resource `GetCapabilititesProbeResult`

        create:
            Endpoint to register new `GetCapabilititesProbeResult` object
        list:
            Retrieves all registered `GetCapabilititesProbeResult` objects
        retrieve:
            Retrieve one specific `GetCapabilititesProbeResult` by the given id
        partial_update:
            Endpoint to update some fields of a `GetCapabilititesProbeResult`
        destroy:
            Endpoint to remove a registered `GetCapabilititesProbeResult` from the system
    """
    permission_classes = [DjangoObjectPermissionsOrAnonReadOnly]
    queryset = GetCapabilititesProbeResult.objects.all()
    serializer_class = GetCapabilititesProbeResultSerializer
    select_for_includes = {
        "run": ["run"],
    }
    filterset_fields = {
        'id': ['exact', 'icontains', 'contains', 'in'],
        'check_response_is_valid_xml_success': ['exact'],
        'check_response_does_not_contain_success': ['exact'],
        'check_response_does_contain_success': ['exact'],
    }
    search_fields = (
        "id",
        "check_response_is_valid_xml_success",
        "check_response_does_not_contain_success",
        "check_response_does_contain_success",
        "check_response_is_valid_xml_message",
        "check_response_does_not_contain_message",
        "check_response_does_contain_message"
    )
    ordering_fields = [
        "id",
        "check_response_is_valid_xml_success",
        "check_response_does_not_contain_success",
        "check_response_does_contain_success",
    ]


class GetMapProbeResultViewSet(
    ModelViewSet,
):
    """ Endpoints for resource `GetMapProbeResult`

        create:
            Endpoint to register new `GetMapProbeResult` object
        list:
            Retrieves all registered `GetMapProbeResult` objects
        retrieve:
            Retrieve one specific `GetMapProbeResult` by the given id
        partial_update:
            Endpoint to update some fields of a `GetMapProbeResult`
        destroy:
            Endpoint to remove a registered `GetMapProbeResult` from the system
    """
    permission_classes = [DjangoObjectPermissionsOrAnonReadOnly]
    queryset = GetMapProbeResult.objects.all()
    serializer_class = GetMapProbeResultSerializer
    select_for_includes = {
        "run": ["run"],
    }
    filterset_fields = {
        'id': ['exact', 'icontains', 'contains', 'in'],
        'check_response_image_success': ['exact'],
        'check_response_does_not_contain_success': ['exact'],
    }
    search_fields = (
        "id",
        "check_response_image_success",
        "check_response_does_not_contain_success",
        "check_response_image_message",
        "check_response_does_not_contain_message",
    )
    ordering_fields = [
        "id",
        "check_response_image_success",
        "check_response_does_not_contain_success",
        "check_response_image_message",
        "check_response_does_not_contain_message",
    ]


class GetCapabilititesProbeViewSet(
    ModelViewSet,
):
    """ Endpoints for resource `GetCapabilititesProbe`

        create:
            Endpoint to register new `GetCapabilititesProbe` object
        list:
            Retrieves all registered `GetCapabilititesProbe` objects
        retrieve:
            Retrieve one specific `GetCapabilititesProbe` by the given id
        partial_update:
            Endpoint to update some fields of a `GetCapabilititesProbe`
        destroy:
            Endpoint to remove a registered `GetCapabilititesProbe` from the system
    """
    permission_classes = [DjangoObjectPermissionsOrAnonReadOnly]
    queryset = GetCapabilititesProbe.objects.all()
    serializer_class = GetCapabilititesProbeSerializer
    select_for_includes = {
        "setting": ["setting"],
    }
    filterset_fields = {
        'id': ['exact', 'icontains', 'contains', 'in'],
        'timeout': ['exact', 'icontains', 'contains'],
        "setting__id": ['exact', 'icontains', 'contains', 'in'],
        'check_response_is_valid_xml': ['exact'],
        # 'check_response_does_contain': ['contains', 'contained_by', 'overlap', 'len'],

    }
    search_fields = (
        "id",
        "timeout",
        "check_response_is_valid_xml",
        "check_response_does_contain",
    )
    ordering_fields = [
        "id",
        "timeout",
        "check_response_is_valid_xml",
        "check_response_does_contain",
    ]


class GetMapProbeViewSet(
    ModelViewSet,
):
    """ Endpoints for resource `GetMapProbe`

        create:
            Endpoint to register new `GetMapProbe` object
        list:
            Retrieves all registered `GetMapProbe` objects
        retrieve:
            Retrieve one specific `GetMapProbe` by the given id
        partial_update:
            Endpoint to update some fields of a `GetMapProbe`
        destroy:
            Endpoint to remove a registered `GetMapProbe` from the system
    """
    permission_classes = [DjangoObjectPermissionsOrAnonReadOnly]
    queryset = GetMapProbe.objects.all()
    serializer_class = GetMapProbeSerializer
    select_for_includes = {
        "setting": ["setting"],
    }
    filterset_fields = {
        'id': ['exact', 'icontains', 'contains', 'in'],
        'layers__id': ['exact', 'icontains', 'contains', 'in'],
        'format__id': ['exact', 'icontains', 'contains', 'in'],
        'reference_system__id': ['exact', 'icontains', 'contains', 'in'],
        'height': ['exact', 'icontains', 'contains'],
        'width': ['exact', 'icontains', 'contains'],
        'check_response_is_image': ['exact', 'icontains', 'contains'],

    }
    search_fields = (
        "id",

    )
    ordering_fields = [
        "id",
    ]
