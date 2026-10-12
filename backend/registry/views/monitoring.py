from django.db.models import Prefetch
from extras.permissions import DjangoObjectPermissionsOrAnonReadOnly
from extras.viewsets import NestedModelViewSet
from registry.models.monitoring import (
    CatalogueServiceGetCapabilitiesProbe,
    CatalogueServiceGetCapabilitiesProbeResult,
    CatalogueServiceGetRecordsProbe, CatalogueServiceGetRecordsProbeResult,
    CatalogueServiceMonitoringRun, CatalogueServiceMonitoringSetting,
    GetCapabilitiesProbe,
    GetCapabilitiesProbeResult,
    GetMapProbe, GetMapProbeResult,
    WebFeatureServiceGetCapabilitiesProbe,
    WebFeatureServiceGetCapabilitiesProbeResult,
    WebFeatureServiceGetFeatureProbe,
    WebFeatureServiceGetFeatureProbeResult, WebFeatureServiceMonitoringRun,
    WebFeatureServiceMonitoringSetting,
    WebMapServiceMonitoringRun,
    WebMapServiceMonitoringSetting)
from registry.serializers.monitoring import (
    CatalogueServiceGetCapabilitiesProbeResultSerializer,
    CatalogueServiceGetCapabilitiesProbeSerializer,
    CatalogueServiceGetRecordsProbeResultSerializer,
    CatalogueServiceGetRecordsProbeSerializer,
    CatalogueServiceMonitoringRunSerializer,
    CatalogueServiceMonitoringSettingSerializer,
    GetCapabilitiesProbeResultSerializer, GetCapabilitiesProbeSerializer,
    GetMapProbeResultSerializer, GetMapProbeSerializer,
    WebFeatureServiceGetCapabilitiesProbeResultSerializer,
    WebFeatureServiceGetCapabilitiesProbeSerializer,
    WebFeatureServiceGetFeatureProbeResultSerializer,
    WebFeatureServiceGetFeatureProbeSerializer,
    WebFeatureServiceMonitoringRunSerializer,
    WebFeatureServiceMonitoringSettingSerializer,
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
    queryset = WebMapServiceMonitoringSetting.objects.select_related('crontab')
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


class WebMapServiceMonitoringRunViewSetMixin:
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
    queryset = WebMapServiceMonitoringRun.objects.with_is_successful()
    serializer_class = WebMapServiceMonitoringRunSerializer
    select_for_includes = {
        "setting": ["setting"],
    }
    prefetch_for_includes = {
        "getcapabilitiesproberesults": [
            Prefetch(
                "registry_getcapabilitiesproberesults",
                queryset=GetCapabilitiesProbeResult.objects.all().select_related("run")
            )
        ],
        "getmapproberesults": [
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
    ordering_fields = ["id", "success", "date_done", "date_created"]


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


class GetCapabilitiesProbeResultViewSetMixin:
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


class GetMapProbeResultViewSetMixin:
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


class GetCapabilitiesProbeViewSetMixin:
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


class GetMapProbeViewSetMixin:
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


class WebFeatureServiceMonitoringSettingViewSetMixin:
    """ Endpoints for resource `WebFeatureServiceMonitoringSetting`

        create:
            Endpoint to register new `WebFeatureServiceMonitoringSetting` object
        list:
            Retrieves all registered `WebFeatureServiceMonitoringSetting` objects
        retrieve:
            Retrieve one specific `WebFeatureServiceMonitoringSetting` by the given id
        partial_update:
            Endpoint to update some fields of a `WebFeatureServiceMonitoringSetting`
        destroy:
            Endpoint to remove a registered `WebFeatureServiceMonitoringSetting` from the system
    """
    permission_classes = [DjangoObjectPermissionsOrAnonReadOnly]
    queryset = WebFeatureServiceMonitoringSetting.objects.select_related('crontab')
    serializer_class = WebFeatureServiceMonitoringSettingSerializer
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


class WebFeatureServiceMonitoringSettingViewSet(
    WebFeatureServiceMonitoringSettingViewSetMixin,
    ModelViewSet
):
    pass


class NestedWebFeatureServiceMonitoringSettingViewSet(
    WebFeatureServiceMonitoringSettingViewSetMixin,
    NestedModelViewSet
):
    pass


class WebFeatureServiceMonitoringRunViewSetMixin:
    """ Endpoints for resource `WebFeatureServiceMonitoringRun`

        create:
            Endpoint to register new `WebFeatureServiceMonitoringRun` object
        list:
            Retrieves all registered `WebFeatureServiceMonitoringRun` objects
        retrieve:
            Retrieve one specific `WebFeatureServiceMonitoringRun` by the given id
        partial_update:
            Endpoint to update some fields of a `WebFeatureServiceMonitoringRun`
        destroy:
            Endpoint to remove a registered `WebFeatureServiceMonitoringRun` from the system
    """
    permission_classes = [DjangoObjectPermissionsOrAnonReadOnly]
    queryset = WebFeatureServiceMonitoringRun.objects.with_is_successful()
    serializer_class = WebFeatureServiceMonitoringRunSerializer
    select_for_includes = {
        "setting": ["setting"],
    }
    prefetch_for_includes = {
        "getcapabilitiesproberesults": [
            Prefetch(
                "registry_webfeatureservicegetcapabilitiesproberesults",
                queryset=WebFeatureServiceGetCapabilitiesProbeResult.objects.all().select_related("run")
            )
        ],
        "getfeatureproberesults": [
            Prefetch(
                "registry_webfeatureservicegetfeatureproberesults",
                queryset=WebFeatureServiceGetFeatureProbeResult.objects.all().select_related("run")
            )
        ],
    }
    filterset_fields = {
        'id': ['exact', 'icontains', 'contains', 'in'],
        'setting__id': ['exact', 'icontains', 'contains', 'in'],
    }
    search_fields = ("id", "success", "setting__service__title")
    ordering_fields = ["id", "success", "date_done", "date_created"]


class WebFeatureServiceMonitoringRunViewSet(
    WebFeatureServiceMonitoringRunViewSetMixin,
    ModelViewSet
):
    pass


class NestedWebFeatureServiceMonitoringRunViewSet(
    WebFeatureServiceMonitoringRunViewSetMixin,
    NestedModelViewSet
):
    pass


class ContentCheckProbeResultViewSetMixin:
    """ Common configuration for all probe results which store the outcome of
        xml content checks (`XmlContentCheckResult`).

        The endpoints are read only in purpose; results are written by the
        monitoring runs.
    """
    permission_classes = [DjangoObjectPermissionsOrAnonReadOnly]
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


class ContentCheckProbeViewSetMixin:
    """ Common configuration for all probes which validate a service request."""
    permission_classes = [DjangoObjectPermissionsOrAnonReadOnly]
    select_for_includes = {
        "setting": ["setting"],
    }
    filterset_fields = {
        'id': ['exact', 'icontains', 'contains', 'in'],
        'setting__id': ['exact', 'icontains', 'contains', 'in'],
    }
    search_fields = (
        "id",
    )
    ordering_fields = [
        "id",
    ]


class WebFeatureServiceGetCapabilitiesProbeResultViewSet(
    ContentCheckProbeResultViewSetMixin,
    ModelViewSet
):
    """ Endpoints for resource `WebFeatureServiceGetCapabilitiesProbeResult`"""
    queryset = WebFeatureServiceGetCapabilitiesProbeResult.objects.all()
    serializer_class = WebFeatureServiceGetCapabilitiesProbeResultSerializer


class NestedWebFeatureServiceGetCapabilitiesProbeResultViewSet(
    ContentCheckProbeResultViewSetMixin,
    NestedModelViewSet
):
    """ Nested endpoints for resource `WebFeatureServiceGetCapabilitiesProbeResult`"""
    queryset = WebFeatureServiceGetCapabilitiesProbeResult.objects.all()
    serializer_class = WebFeatureServiceGetCapabilitiesProbeResultSerializer


class WebFeatureServiceGetFeatureProbeResultViewSet(
    ContentCheckProbeResultViewSetMixin,
    ModelViewSet
):
    """ Endpoints for resource `WebFeatureServiceGetFeatureProbeResult`"""
    queryset = WebFeatureServiceGetFeatureProbeResult.objects.all()
    serializer_class = WebFeatureServiceGetFeatureProbeResultSerializer


class NestedWebFeatureServiceGetFeatureProbeResultViewSet(
    ContentCheckProbeResultViewSetMixin,
    NestedModelViewSet
):
    """ Nested endpoints for resource `WebFeatureServiceGetFeatureProbeResult`"""
    queryset = WebFeatureServiceGetFeatureProbeResult.objects.all()
    serializer_class = WebFeatureServiceGetFeatureProbeResultSerializer


class WebFeatureServiceGetCapabilitiesProbeViewSet(
    ContentCheckProbeViewSetMixin,
    ModelViewSet
):
    """ Endpoints for resource `WebFeatureServiceGetCapabilitiesProbe`"""
    queryset = WebFeatureServiceGetCapabilitiesProbe.objects.all()
    serializer_class = WebFeatureServiceGetCapabilitiesProbeSerializer


class NestedWebFeatureServiceGetCapabilitiesProbeViewSet(
    ContentCheckProbeViewSetMixin,
    NestedModelViewSet
):
    """ Nested endpoints for resource `WebFeatureServiceGetCapabilitiesProbe`"""
    queryset = WebFeatureServiceGetCapabilitiesProbe.objects.all()
    serializer_class = WebFeatureServiceGetCapabilitiesProbeSerializer


class WebFeatureServiceGetFeatureProbeViewSet(
    ContentCheckProbeViewSetMixin,
    ModelViewSet
):
    """ Endpoints for resource `WebFeatureServiceGetFeatureProbe`"""
    queryset = WebFeatureServiceGetFeatureProbe.objects.all()
    serializer_class = WebFeatureServiceGetFeatureProbeSerializer


class NestedWebFeatureServiceGetFeatureProbeViewSet(
    ContentCheckProbeViewSetMixin,
    NestedModelViewSet
):
    """ Nested endpoints for resource `WebFeatureServiceGetFeatureProbe`"""
    queryset = WebFeatureServiceGetFeatureProbe.objects.all()
    serializer_class = WebFeatureServiceGetFeatureProbeSerializer


class CatalogueServiceMonitoringSettingViewSetMixin:
    """ Endpoints for resource `CatalogueServiceMonitoringSetting`

        create:
            Endpoint to register new `CatalogueServiceMonitoringSetting` object
        list:
            Retrieves all registered `CatalogueServiceMonitoringSetting` objects
        retrieve:
            Retrieve one specific `CatalogueServiceMonitoringSetting` by the given id
        partial_update:
            Endpoint to update some fields of a `CatalogueServiceMonitoringSetting`
        destroy:
            Endpoint to remove a registered `CatalogueServiceMonitoringSetting` from the system
    """
    permission_classes = [DjangoObjectPermissionsOrAnonReadOnly]
    queryset = CatalogueServiceMonitoringSetting.objects.select_related('crontab')
    serializer_class = CatalogueServiceMonitoringSettingSerializer
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


class CatalogueServiceMonitoringSettingViewSet(
    CatalogueServiceMonitoringSettingViewSetMixin,
    ModelViewSet
):
    pass


class NestedCatalogueServiceMonitoringSettingViewSet(
    CatalogueServiceMonitoringSettingViewSetMixin,
    NestedModelViewSet
):
    pass


class CatalogueServiceMonitoringRunViewSetMixin:
    """ Endpoints for resource `CatalogueServiceMonitoringRun`

        create:
            Endpoint to register new `CatalogueServiceMonitoringRun` object
        list:
            Retrieves all registered `CatalogueServiceMonitoringRun` objects
        retrieve:
            Retrieve one specific `CatalogueServiceMonitoringRun` by the given id
        partial_update:
            Endpoint to update some fields of a `CatalogueServiceMonitoringRun`
        destroy:
            Endpoint to remove a registered `CatalogueServiceMonitoringRun` from the system
    """
    permission_classes = [DjangoObjectPermissionsOrAnonReadOnly]
    queryset = CatalogueServiceMonitoringRun.objects.with_is_successful()
    serializer_class = CatalogueServiceMonitoringRunSerializer
    select_for_includes = {
        "setting": ["setting"],
    }
    prefetch_for_includes = {
        "getcapabilitiesproberesults": [
            Prefetch(
                "registry_catalogueservicegetcapabilitiesproberesults",
                queryset=CatalogueServiceGetCapabilitiesProbeResult.objects.all().select_related("run")
            )
        ],
        "getrecordsproberesults": [
            Prefetch(
                "registry_catalogueservicegetrecordsproberesults",
                queryset=CatalogueServiceGetRecordsProbeResult.objects.all().select_related("run")
            )
        ],
    }
    filterset_fields = {
        'id': ['exact', 'icontains', 'contains', 'in'],
        'setting__id': ['exact', 'icontains', 'contains', 'in'],
    }
    search_fields = ("id", "success", "setting__service__title")
    ordering_fields = ["id", "success", "date_done", "date_created"]


class CatalogueServiceMonitoringRunViewSet(
    CatalogueServiceMonitoringRunViewSetMixin,
    ModelViewSet
):
    pass


class NestedCatalogueServiceMonitoringRunViewSet(
    CatalogueServiceMonitoringRunViewSetMixin,
    NestedModelViewSet
):
    pass


class CatalogueServiceGetCapabilitiesProbeResultViewSet(
    ContentCheckProbeResultViewSetMixin,
    ModelViewSet
):
    """ Endpoints for resource `CatalogueServiceGetCapabilitiesProbeResult`"""
    queryset = CatalogueServiceGetCapabilitiesProbeResult.objects.all()
    serializer_class = CatalogueServiceGetCapabilitiesProbeResultSerializer


class NestedCatalogueServiceGetCapabilitiesProbeResultViewSet(
    ContentCheckProbeResultViewSetMixin,
    NestedModelViewSet
):
    """ Nested endpoints for resource `CatalogueServiceGetCapabilitiesProbeResult`"""
    queryset = CatalogueServiceGetCapabilitiesProbeResult.objects.all()
    serializer_class = CatalogueServiceGetCapabilitiesProbeResultSerializer


class CatalogueServiceGetRecordsProbeResultViewSet(
    ContentCheckProbeResultViewSetMixin,
    ModelViewSet
):
    """ Endpoints for resource `CatalogueServiceGetRecordsProbeResult`"""
    queryset = CatalogueServiceGetRecordsProbeResult.objects.all()
    serializer_class = CatalogueServiceGetRecordsProbeResultSerializer


class NestedCatalogueServiceGetRecordsProbeResultViewSet(
    ContentCheckProbeResultViewSetMixin,
    NestedModelViewSet
):
    """ Nested endpoints for resource `CatalogueServiceGetRecordsProbeResult`"""
    queryset = CatalogueServiceGetRecordsProbeResult.objects.all()
    serializer_class = CatalogueServiceGetRecordsProbeResultSerializer


class CatalogueServiceGetCapabilitiesProbeViewSet(
    ContentCheckProbeViewSetMixin,
    ModelViewSet
):
    """ Endpoints for resource `CatalogueServiceGetCapabilitiesProbe`"""
    queryset = CatalogueServiceGetCapabilitiesProbe.objects.all()
    serializer_class = CatalogueServiceGetCapabilitiesProbeSerializer


class NestedCatalogueServiceGetCapabilitiesProbeViewSet(
    ContentCheckProbeViewSetMixin,
    NestedModelViewSet
):
    """ Nested endpoints for resource `CatalogueServiceGetCapabilitiesProbe`"""
    queryset = CatalogueServiceGetCapabilitiesProbe.objects.all()
    serializer_class = CatalogueServiceGetCapabilitiesProbeSerializer


class CatalogueServiceGetRecordsProbeViewSet(
    ContentCheckProbeViewSetMixin,
    ModelViewSet
):
    """ Endpoints for resource `CatalogueServiceGetRecordsProbe`"""
    queryset = CatalogueServiceGetRecordsProbe.objects.all()
    serializer_class = CatalogueServiceGetRecordsProbeSerializer


class NestedCatalogueServiceGetRecordsProbeViewSet(
    ContentCheckProbeViewSetMixin,
    NestedModelViewSet
):
    """ Nested endpoints for resource `CatalogueServiceGetRecordsProbe`"""
    queryset = CatalogueServiceGetRecordsProbe.objects.all()
    serializer_class = CatalogueServiceGetRecordsProbeSerializer
