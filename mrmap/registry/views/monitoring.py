from django.db.models.query import Prefetch
from extras.permissions import DjangoObjectPermissionsOrAnonReadOnly
from extras.viewsets import NestedModelViewSet
from registry.models.monitoring import (GetCapabilitiesProbe,
                                        GetCapabilitiesProbeResult,
                                        GetMapProbe, GetMapProbeResult,
                                        WebMapServiceMonitoringRun,
                                        WebMapServiceMonitoringSetting)
from registry.serializers.monitoring import (
    GetCapabilitiesProbeResultSerializer, GetCapabilitiesProbeSerializer,
    GetMapProbeResultSerializer, GetMapProbeSerializer,
    WebMapServiceMonitoringRunSerializer,
    WebMapServiceMonitoringSettingSerializer)
from rest_framework_json_api.views import ModelViewSet


class WebMapServiceMonitoringSettingViewSetMixin:
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
    }
    filterset_fields = {
        'id': ['exact', 'icontains', 'contains', 'in'],
        'service__id': ['exact', 'icontains', 'contains', 'in'],
        'service__title': ['exact', 'icontains', 'contains'],
    }
    search_fields = ("id", "service", "service__title")
    ordering_fields = ["id", "name", "service"]


class WebMapServiceMonitoringSettingViewSet(
    WebMapServiceMonitoringSettingViewSetMixin,
    ModelViewSet
):
    pass


class NestedWebMapServiceMonitoringSettingViewSet(
    WebMapServiceMonitoringSettingViewSetMixin,
    NestedModelViewSet
):
    pass


class WebMapServiceMonitoringRunViewSetMixin():
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
        "registry_getcapabilitiesproberesults": [
            Prefetch(
                "registry_getcapabilitiesproberesults",
                queryset=GetCapabilitiesProbeResult.objects.all().select_related("run")
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


class WebMapServiceMonitoringRunViewSet(
    WebMapServiceMonitoringRunViewSetMixin,
    ModelViewSet
):
    pass


class NestedWebMapServiceMonitoringRunViewSet(
    WebMapServiceMonitoringRunViewSetMixin,
    NestedModelViewSet
):
    pass


class GetCapabilitiesProbeResultViewSetMixin():
    """ Endpoints for resource `GetCapabilitiesProbeResult`

        create:
            Endpoint to register new `GetCapabilitiesProbeResult` object
        list:
            Retrieves all registered `GetCapabilitiesProbeResult` objects
        retrieve:
            Retrieve one specific `GetCapabilitiesProbeResult` by the given id
        partial_update:
            Endpoint to update some fields of a `GetCapabilitiesProbeResult`
        destroy:
            Endpoint to remove a registered `GetCapabilitiesProbeResult` from the system
    """
    permission_classes = [DjangoObjectPermissionsOrAnonReadOnly]
    queryset = GetCapabilitiesProbeResult.objects.all()
    serializer_class = GetCapabilitiesProbeResultSerializer
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


class GetCapabilitiesProbeResultViewSet(
    GetCapabilitiesProbeResultViewSetMixin,
    ModelViewSet
):
    pass


class NestedGetCapabilitiesProbeResultViewSet(
    GetCapabilitiesProbeResultViewSetMixin,
    NestedModelViewSet
):
    pass


class GetMapProbeResultViewSetMixin():
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


class GetMapProbeResultViewSet(
    GetMapProbeResultViewSetMixin,
    ModelViewSet
):
    pass


class NestedGetMapProbeResultViewSet(
    GetMapProbeResultViewSetMixin,
    NestedModelViewSet
):
    pass


class GetCapabilitiesProbeViewSetMixin():
    """ Endpoints for resource `GetCapabilitiesProbe`

        create:
            Endpoint to register new `GetCapabilitiesProbe` object
        list:
            Retrieves all registered `GetCapabilitiesProbe` objects
        retrieve:
            Retrieve one specific `GetCapabilitiesProbe` by the given id
        partial_update:
            Endpoint to update some fields of a `GetCapabilitiesProbe`
        destroy:
            Endpoint to remove a registered `GetCapabilitiesProbe` from the system
    """
    permission_classes = [DjangoObjectPermissionsOrAnonReadOnly]
    queryset = GetCapabilitiesProbe.objects.all()
    serializer_class = GetCapabilitiesProbeSerializer

    filterset_fields = {
        'id': ['exact', 'icontains', 'contains', 'in'],
        'timeout': ['exact', 'icontains', 'contains'],
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


class GetCapabilitiesProbeViewSet(
    GetCapabilitiesProbeViewSetMixin,
    ModelViewSet
):
    pass


class NestedGetCapabilitiesProbeViewSet(
    GetCapabilitiesProbeViewSetMixin,
    NestedModelViewSet
):
    pass


class GetMapProbeViewSetMixin():
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


class GetMapProbeViewSet(
    GetMapProbeViewSetMixin,
    ModelViewSet
):
    pass


class NestedGetMapProbeViewSet(
    GetMapProbeViewSetMixin,
    NestedModelViewSet
):
    pass
