from camel_converter import to_camel
from django.db.models import Count, Exists, F, OuterRef, Prefetch, Q, Subquery, Sum
from django.db.models import Value as V
from django.db.models.functions import Coalesce
from django.db.models.sql.constants import LOUTER
from django_cte import CTE, with_cte
from drf_spectacular.utils import OpenApiParameter, OpenApiTypes, extend_schema, extend_schema_view
from django.http import HttpResponse, JsonResponse
from guardian.core import ObjectPermissionChecker
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.renderers import JSONRenderer
from extras.permissions import DjangoObjectPermissionsOrAnonReadOnly
from extras.viewsets import (AsyncCreateMixin, ExtendedPreloadIncludesMixin,
                             HistoryInformationViewSetMixin,
                             NestedModelViewSet,
                             ObjectPermissionCheckerViewSetMixin,
                             PreloadNotIncludesMixin, SerializerClassesMixin,
                             SparseFieldMixin)
from notify.models import BackgroundProcess, ProcessNameEnum
from registry.enums.harvesting import CollectingStatenEnum, HarvestingPhaseEnum
from registry.filters.service import (CatalogueServiceFilterSet,
                                      FeatureTypeFilterSet, LayerFilterSet,
                                      WebFeatureServiceFilterSet,
                                      WebMapServiceFilterSet)
from registry.models import (FeatureType, Layer, WebFeatureService,
                             WebMapService)
from registry.models.harvest import (HarvestedMetadataRelation,
                                     HarvestingJob, PeriodicHarvestingJob)
from registry.models.metadata import (DatasetMetadataRecord, Keyword, Language,
                                      MimeType, ReferenceSystem, Style,
                                      TimeExtent)
from registry.models.monitoring import (CatalogueServiceMonitoringSetting,
                                        WebFeatureServiceMonitoringSetting,
                                        WebMapServiceMonitoringSetting)
from registry.models.security import (AllowedWebFeatureServiceOperation,
                                      AllowedWebMapServiceOperation,
                                      WebFeatureServiceProxySetting,
                                      WebMapServiceProxySetting)
from registry.models.service import (CatalogueService,
                                     CatalogueServiceOperationUrl,
                                     WebFeatureServiceOperationUrl,
                                     WebMapServiceOperationUrl)
from registry.models.update import WebMapServiceUpdateSetting
from registry.querys.alerts import (SERVICE_KIND_OF, alerts_requested,
                                    has_alert_annotations)
from registry.querys.service import LayerPrefetch
from registry.querys.explorer import ServiceExplorerMixin
from registry.serializers.service import (
    CatalogueServiceCreateSerializer, CatalogueServiceOperationUrlSerializer,
    CatalogueServiceSerializer, FeatureTypeSerializer, LayerSerializer,
    WebFeatureServiceCreateSerializer, WebFeatureServiceSerializer,
    WebMapServiceCreateSerializer, WebMapServiceListSerializer,
    WebMapServiceOperationUrlSerializer, WebMapServiceSerializer)
from registry.tasks.service import build_ogc_service
from registry.helper.preview import PreviewError, feature_preview_image, preview
from rest_framework_json_api.views import ModelViewSet


# The relations of a service that is only serialized because it was included in the
# answer of another resource: the service itself is answered in full, but its own
# relations are answered as related resources, which need the id of the related
# object and, for a relation of the other side, the column that points back to the
# service. The names of the relations are prefixed with "service__", so that the
# same list can be used while the service of an object is prefetched.
WMS_SERVICE_RELATIONS = [
    Prefetch("service__keywords", queryset=Keyword.objects.only("id")),
    Prefetch("service__languages", queryset=Language.objects.only("value")),
    Prefetch(
        "service__layers",
        queryset=Layer.objects.only("id", "service_id", "mptt_tree_id", "mptt_lft"),
    ),
    Prefetch(
        "service__allowed_operations",
        queryset=AllowedWebMapServiceOperation.objects.only("id", "secured_service"),
    ),
    Prefetch(
        "service__proxy_setting",
        queryset=WebMapServiceProxySetting.objects.only("id"),
    ),
    Prefetch(
        "service__web_map_service_monitorings",
        queryset=WebMapServiceMonitoringSetting.objects.only("id", "service"),
    ),
    Prefetch(
        "service__web_map_service_update_settings",
        queryset=WebMapServiceUpdateSetting.objects.only("id", "service"),
    ),
]
WMS_OPERATION_URLS_AS_RELATION = Prefetch(
    "service__operation_urls",
    queryset=WebMapServiceOperationUrl.objects.only("id", "service"),
)
WFS_SERVICE_RELATIONS = [
    Prefetch("service__keywords", queryset=Keyword.objects.only("id")),
    Prefetch("service__languages", queryset=Language.objects.only("value")),
    Prefetch(
        "service__featuretypes",
        queryset=FeatureType.objects.only("id", "service_id"),
    ),
    Prefetch(
        "service__web_feature_service_monitorings",
        queryset=WebFeatureServiceMonitoringSetting.objects.only(
            "id", "service"),
    ),
]
WFS_OPERATION_URLS_AS_RELATION = Prefetch(
    "service__operation_urls",
    queryset=WebFeatureServiceOperationUrl.objects.only("id", "service"),
)
# the mime types of an operation url are never serialized, they are only answered
# as related resources of the operation url
MIME_TYPES_AS_RELATION = Prefetch(
    "mime_types", queryset=MimeType.objects.only("id"))


class ServiceAlertAnnotationMixin:
    """Annotates the alerts of a service to the queryset which answers them.

    The alerts of a service are answered by a subquery per attribute, so they are
    only annotated to a query which asks for them: a request which answers the
    attributes of a service, narrows the services by them or orders the services
    by them - see `alerts_requested()`.
    """

    def with_alerts_if_requested(self, qs):
        """Annotate the alerts of the services which the request wants.

        Args:
            qs: the queryset of one kind of service to annotate

        Returns:
            QuerySet: the queryset, annotated if the request asks for alerts
        """
        kind = SERVICE_KIND_OF.get(qs.model)
        if kind is None or not alerts_requested(self.request,
                                                kind.service.__name__,
                                                kind.attributes):
            return qs
        return qs.with_alert_information()

    def filter_queryset(self, queryset):
        """Annotate the alerts before the filters and the sort of a request.

        The filters and the sort of a request name the annotations of the alerts,
        so those have to be annotated before they are applied. A viewset applies
        them not only to the queryset which answers the request, but as well to
        the queryset it holds, when it checks the permissions of the services it
        answers, see `ObjectPermissionCheckerViewSetMixin`.

        Args:
            queryset: the queryset of one kind of service to filter

        Returns:
            QuerySet: the queryset the request is answered with
        """
        if not has_alert_annotations(queryset):
            queryset = self.with_alerts_if_requested(queryset)
        return super().filter_queryset(queryset)


class ServicePreviewMixin:
    @classmethod
    def get_extra_actions(cls):
        actions = super().get_extra_actions()
        # Nested relationship viewsets inherit the service UI customizations,
        # but preview addresses only the canonical registered-service endpoint.
        if issubclass(cls, NestedModelViewSet):
            return [item for item in actions if item.__name__ not in {"preview", "preview_image"}]
        return actions

    @extend_schema(
        parameters=[OpenApiParameter(name, OpenApiTypes.STR, description=description)
                    for name, description in (
                        ("selection", "Registered layer/feature-type identifier."),
                        ("bbox", "WGS84 west,south,east,north. Omit for stored discovery only."),
                        ("width", "Image width, at most 2048 pixels."),
                        ("height", "Image height, at most 2048 pixels."),
                        ("identify", "true for WMS GetFeatureInfo."),
                        ("x", "Identify pixel column."), ("y", "Identify pixel row."),
                        ("start", "CSW 1-based record position; pages contain at most 25 records."))],
        responses={200: OpenApiTypes.OBJECT, 400: OpenApiTypes.OBJECT,
                   403: OpenApiTypes.OBJECT, 422: OpenApiTypes.OBJECT,
                   423: OpenApiTypes.OBJECT, 502: OpenApiTypes.OBJECT},
        description="Read-only live preview. Stored discovery; bounded upstream reads. No registry writes.",
    )
    @action(detail=True, methods=["get"], renderer_classes=[JSONRenderer], filter_backends=[])
    def preview(self, request, *args, **kwargs):
        service = self.get_object()
        # DRF's default read-only object permission map is empty; previews also
        # explicitly require view permission on the registered service.
        if not ObjectPermissionChecker(request.user).has_perm(
                f"view_{service.__class__.__name__.lower()}", service):
            raise PermissionDenied
        try:
            result = preview(service, request, request.query_params)
            result["source"] = str(service.title)
            return JsonResponse(result, headers={"Cache-Control": "no-store"})
        except PreviewError as error:
            return JsonResponse({"error": error.code}, status=error.status,
                                headers={"Cache-Control": "no-store"})


class PreviewImageRenderer(JSONRenderer):
    """Accept PNG requests while keeping DRF permission errors in JSON."""
    media_type = "image/png"
    format = "png"

    def render(self, data, accepted_media_type=None, renderer_context=None):
        if renderer_context:
            renderer_context["response"]["Content-Type"] = "application/json"
        return super().render(data, accepted_media_type, renderer_context)


@extend_schema_view(preview=extend_schema(operation_id="preview_WebMapService"))
class WebMapServiceViewSet(
    ServicePreviewMixin,
    ServiceAlertAnnotationMixin,
    ServiceExplorerMixin,
    SerializerClassesMixin,
    AsyncCreateMixin,
    ObjectPermissionCheckerViewSetMixin,
    ExtendedPreloadIncludesMixin,
    PreloadNotIncludesMixin,
    HistoryInformationViewSetMixin,
    ModelViewSet,
):
    """ Endpoints for resource `WebMapService`

        create:
            Endpoint to register new `WebMapServices` object
        list:
            Retrieves all registered `WebMapServices` objects
        retrieve:
            Retrieve one specific `WebMapServices` by the given id
        partial_update:
            Endpoint to update some fields of a registered `WebMapServices`
        destroy:
            Endpoint to remove a registered `WebMapServices` from the system
    """
    queryset = WebMapService.objects.all()
    serializer_classes = {
        "default": WebMapServiceSerializer,
        "list": WebMapServiceListSerializer,
        "create": WebMapServiceCreateSerializer,
    }
    select_for_includes = {
        "proxy_setting": ["proxy_setting"],
        "service_contact": ["service_contact"],
        "metadata_contact": ["metadata_contact"],
    }
    prefetch_for_includes = {
        "layers": [
            lambda request: LayerPrefetch(request)
        ],
        "keywords": ["keywords"],
        "operation_urls": [
            Prefetch(
                "operation_urls",
                queryset=WebMapServiceOperationUrl.objects.select_related(
                    "service",
                ).prefetch_related(MIME_TYPES_AS_RELATION),
            )
        ],
    }
    prefetch_for_not_includes = {
        "layers": [
            Prefetch(
                "layers",
                queryset=Layer.objects.only(
                    "id",
                    "service_id",
                    "mptt_tree_id",
                    "mptt_lft",
                ),
            )
        ],
        "keywords": [
            Prefetch("keywords", queryset=Keyword.objects.only("id"))
        ],
        "allowed_operations": [
            Prefetch(
                "allowed_operations",
                queryset=AllowedWebMapServiceOperation.objects.only(
                    "id", "secured_service")
            )
        ],
        "operation_urls": [
            Prefetch(
                "operation_urls",
                queryset=WebMapServiceOperationUrl.objects.only(
                    "id", "service"),
            )
        ],
        "proxy_setting": [
            Prefetch(
                "proxy_setting",
                queryset=WebMapServiceProxySetting.objects.only(
                    "id", )
            )
        ],
        "web_map_service_monitoring_settings": [
            Prefetch(
                "web_map_service_monitorings",
                queryset=WebMapServiceMonitoringSetting.objects.only(
                    "id", "service"),
            )
        ],
        "web_map_service_update_settings": [
            Prefetch(
                "web_map_service_update_settings",
                queryset=WebMapServiceUpdateSetting.objects.only(
                    "id", "service"),
            )
        ],
        "languages": [
            Prefetch("languages", queryset=Language.objects.only("value"))
        ],
    }
    filterset_class = WebMapServiceFilterSet
    search_fields = ("id", "title", "abstract", "keywords__keyword")
    ordering_fields = ["id", "title", "abstract", "hits",
                       "date_stamp", "has_alert", "monitoring_failed_at",
                       "update_review_required_at", "update_failed_at"]
    permission_classes = [DjangoObjectPermissionsOrAnonReadOnly]
    task_function = build_ogc_service

    def get_task_kwargs(self, request, serializer):
        background_process = BackgroundProcess.objects.create(
            phase="Background process created",
            process_type=ProcessNameEnum.REGISTERING.value,
            description=f'Register new service with url {serializer.validated_data["get_capabilities_url"]}'  # noqa
        )

        return {
            "get_capabilities_url": serializer.validated_data["get_capabilities_url"],
            "collect_metadata_records": serializer.validated_data["collect_metadata_records"],
            "service_auth_pk": serializer.service_auth.id if hasattr(serializer, "service_auth") else None,
            "http_request": {
                "path": request.path,
                "method": request.method,
                "content_type": request.content_type,
                "data": request.GET,
                "user_pk": request.user.pk,
            },
            "background_process_pk": background_process.pk
        }

    def get_queryset(self, *args, **kwargs):
        qs = super().get_queryset(*args, **kwargs)
        fields_snake = self.request.GET.get(
            "fields[WebMapService]", "").split(',')
        fields = [to_camel(field) for field in fields_snake if field.strip()]

        if not fields or "camouflage" in fields:
            qs = qs.annotate(
                camouflage=Coalesce(
                    F("proxy_setting__camouflage"), V(False)),
            )
        if not fields or "logResponse" in fields:
            qs = qs.annotate(
                log_response=Coalesce(
                    F("proxy_setting__log_response"), V(False)),
            )
        if not fields or "isSecured" in fields:
            qs = qs.annotate(
                is_secured=Exists(
                    AllowedWebMapServiceOperation.objects.filter(
                        secured_service__id__exact=OuterRef("pk"),
                    )
                ),
            )
        if not fields or "isSpatialSecured" in fields:
            qs = qs.annotate(
                is_spatial_secured=Exists(
                    AllowedWebMapServiceOperation.objects.filter(
                        secured_service__id__exact=OuterRef("pk"),
                        allowed_area__isnull=False
                    )
                )
            )

        qs = self.with_alerts_if_requested(qs)
        return qs


class ServiceElementHistoryInformationViewSetMixin(HistoryInformationViewSetMixin):
    def get_queryset(self, *args, **kwargs):
        qs = super().get_queryset(*args, **kwargs)
        service_model = qs.model._meta.get_field('service').related_model
        creation_history = service_model.change_log.model.objects.filter(
            history_relation_id=OuterRef('service_id'), history_type='+',
        ).order_by('history_date', 'history_id')
        # A correlated subquery avoids loading each child's service or history
        # separately, including when only createdAt is requested.
        return qs.annotate(service_created_at=Subquery(
            creation_history.values('history_date')[:1],
        ))


class LayerViewSetMixin(
    PreloadNotIncludesMixin,
    ServiceElementHistoryInformationViewSetMixin,
):
    queryset = Layer.objects.all().select_related("mptt_tree")
    serializer_class = LayerSerializer
    filterset_class = LayerFilterSet
    search_fields = ("id", "title", "abstract", "keywords__keyword")
    select_for_includes = {
        "service": ["service", "service__service_contact", "service__metadata_contact"],
        "service.operation_urls": ["service", "service__service_contact",
                                   "service__metadata_contact"]
    }
    prefetch_for_includes = {
        # the service of a layer is serialized, all relations of that service are
        # only answered as related resources
        "service": [*WMS_SERVICE_RELATIONS, WMS_OPERATION_URLS_AS_RELATION],
        "service.operation_urls": [
            # only the operation urls are serialized, their mime types and the other
            # relations of the service are answered as related resources
            Prefetch(
                "service__operation_urls",
                queryset=WebMapServiceOperationUrl.objects.prefetch_related(
                    MIME_TYPES_AS_RELATION
                ),
            ),
            *WMS_SERVICE_RELATIONS
        ],
        "styles": ["styles"],
        "keywords": ["keywords"],
        "reference_systems": ["reference_systems"],
        "dataset_metadata": ["registry_datasetmetadatarecord_metadata_records"]
    }
    prefetch_for_not_includes = {
        "mptt_parent": [
            # TODO optimize queryset with defer
            Prefetch(
                "mptt_parent",
                queryset=Layer.objects.select_related(
                    "mptt_tree").only("id", "mptt_tree")
            )
        ],
        "styles": [
            Prefetch("styles", queryset=Style.objects.only("id", "layer_id"))
        ],
        "keywords": [
            Prefetch("keywords", queryset=Keyword.objects.only("id"))
        ],
        "reference_systems": [
            Prefetch(
                "reference_systems", queryset=ReferenceSystem.objects.only("id")
            )
        ],
        "dataset_metadata": [
            Prefetch(
                "registry_datasetmetadatarecord_metadata_records", queryset=DatasetMetadataRecord.objects.only("id")
            )
        ],
        "languages": [
            Prefetch("languages", queryset=Language.objects.only("value"))
        ]
    }
    permission_classes = [DjangoObjectPermissionsOrAnonReadOnly]
    ordering_fields = ["id", "title", "abstract",
                       "hits", "scale_max", "scale_min", "date_stamp", "mptt_lft", "mptt_rgt", "mptt_depth"]

    def get_queryset(self, *args, **kwargs):
        # we need to call the speficic queryset method here on runtime.
        # If the queryset is defined on class level, the query is pregenerated on appserver startup, and no request ist present.
        qs = super().get_queryset(*args, **kwargs)
        qs = qs.with_inherited_attributes_cte()
        return qs


class LayerViewSet(
        LayerViewSetMixin,
        ModelViewSet):
    """ Endpoints for resource `Layer`

        list:
            Retrieves all registered `Layer` objects
        retrieve:
            Retrieve one specific `Layer` by the given id
        partial_update:
            Endpoint to update some fields of a registered `Layer`

    """
    # removes create and delete endpoints, cause this two actions are made by the mrmap system it self in registrion or update processing of the service.
    # delete is only provided on the service endpoint it self, which implicit removes all related objects
    http_method_names = ["get", "patch", "head", "options"]


class NestedLayerViewSet(
        LayerViewSetMixin,
        NestedModelViewSet):
    """ Nested list endpoint for resource `Layer`

        list:
            Retrieves all registered `Layer` objects

    """


class WebMapServiceOperationUrlViewSetMixin(
):
    queryset = WebMapServiceOperationUrl.objects.all()
    serializer_class = WebMapServiceOperationUrlSerializer
    search_fields = ("id", "service")
    permission_classes = [DjangoObjectPermissionsOrAnonReadOnly]
    ordering_fields = ["id"]


class WebMapServiceOperationUrlViewSet(
    WebMapServiceOperationUrlViewSetMixin,
    ModelViewSet
):
    """ Endpoints for resource `WebMapServiceOperationUrl`

        list:
            Retrieves all registered `WebMapServiceOperationUrl` objects
        retrieve:
            Retrieve one specific `WebMapServiceOperationUrl` by the given id
        partial_update:
            Endpoint to update some fields of a registered `WebMapServiceOperationUrl`

    """
    # removes create and delete endpoints, cause this two actions are made by the mrmap system it self in registrion or update processing of the service.
    # delete is only provided on the service endpoint it self, which implicit removes all related objects
    http_method_names = ["get", "patch", "head", "options"]


class NestedWebMapServiceOperationUrlViewSet(
    WebMapServiceOperationUrlViewSetMixin,
    NestedModelViewSet
):
    """ Nested list endpoint for resource `WebMapServiceOperationUrl`

        list:
            Retrieves all registered `WebMapServiceOperationUrl` objects

    """


@extend_schema_view(preview=extend_schema(operation_id="preview_WebFeatureService"))
class WebFeatureServiceViewSet(
    ServicePreviewMixin,
    ServiceAlertAnnotationMixin,
    ServiceExplorerMixin,
    SerializerClassesMixin,
    AsyncCreateMixin,
    ObjectPermissionCheckerViewSetMixin,
    PreloadNotIncludesMixin,
    HistoryInformationViewSetMixin,
    ModelViewSet,
):
    """ Endpoints for resource `WebFeatureService`

        create:
            Endpoint to register new `WebFeatureService` object
        list:
            Retrieves all registered `WebFeatureService` objects
        retrieve:
            Retrieve one specific `WebFeatureService` by the given id
        partial_update:
            Endpoint to update some fields of a registered `WebFeatureService`
        destroy:
            Endpoint to remove a registered `WebFeatureService` from the system
    """
    queryset = WebFeatureService.objects.all()
    serializer_classes = {
        "default": WebFeatureServiceSerializer,
        "create": WebFeatureServiceCreateSerializer,
    }

    @extend_schema(
        operation_id="preview_image_WebFeatureService",
        parameters=[
            OpenApiParameter(name, OpenApiTypes.INT,
                             description="Thumbnail dimension in pixels, from 1 to 2048.")
            for name in ("width", "height")
        ],
        responses={(200, "image/png"): OpenApiTypes.BINARY,
                   (400, "application/json"): OpenApiTypes.OBJECT,
                   (403, "application/json"): OpenApiTypes.OBJECT,
                   (422, "application/json"): OpenApiTypes.OBJECT,
                   (423, "application/json"): OpenApiTypes.OBJECT,
                   (502, "application/json"): OpenApiTypes.OBJECT},
        description="Read-only PNG thumbnail of an automatically selected, bounded WFS feature sample.",
    )
    @action(detail=True, methods=["get"], url_path="preview-image",
            renderer_classes=[PreviewImageRenderer, JSONRenderer], filter_backends=[])
    def preview_image(self, request, *args, **kwargs):
        service = self.get_object()
        if not ObjectPermissionChecker(request.user).has_perm("view_webfeatureservice", service):
            raise PermissionDenied
        try:
            content = feature_preview_image(service, request, request.query_params)
            return HttpResponse(content, content_type="image/png", headers={"Cache-Control": "no-store"})
        except PreviewError as error:
            return JsonResponse({"error": error.code}, status=error.status,
                                headers={"Cache-Control": "no-store"})

    select_for_includes = {
        "proxy_setting": ["proxy_setting"],
        "service_contact": ["service_contact"],
        "metadata_contact": ["metadata_contact"],
    }
    prefetch_for_includes = {
        "featuretypes": [
            # the feature types are serialized, their relations are only answered as
            # related resources
            Prefetch(
                "featuretypes",
                queryset=FeatureType.objects.prefetch_related(
                    Prefetch("keywords", queryset=Keyword.objects.only("id")),
                    Prefetch("reference_systems",
                             queryset=ReferenceSystem.objects.only("id")),
                    Prefetch("output_formats",
                             queryset=MimeType.objects.only("id")),
                ),
            ),
        ],
        "keywords": ["keywords"],
        "allowed_operations": [
            Prefetch(
                "allowed_operations",
                queryset=AllowedWebFeatureServiceOperation.objects.select_related(
                    "secured_service")
            )
        ],
        "operation_urls": [
            Prefetch(
                "operation_urls",
                queryset=WebFeatureServiceOperationUrl.objects.select_related(
                    "service"
                ).prefetch_related(MIME_TYPES_AS_RELATION),
            )
        ],
    }
    prefetch_for_not_includes = {
        "featuretypes": [
            Prefetch(
                "featuretypes",
                queryset=FeatureType.objects.only(
                    "id",
                    "service_id",
                )
            ),
        ],
        "keywords": [
            Prefetch("keywords", queryset=Keyword.objects.only("id"))
        ],
        "allowed_operations": [
            Prefetch(
                "allowed_operations",
                queryset=AllowedWebFeatureServiceOperation.objects.only(
                    "id", "secured_service")
            )
        ],
        "operation_urls": [
            Prefetch(
                "operation_urls",
                queryset=WebFeatureServiceOperationUrl.objects.only(
                    "id", "service"),
            )
        ],
        "proxy_setting": [
            Prefetch(
                "proxy_setting",
                queryset=WebFeatureServiceProxySetting.objects.only(
                    "id", )
            )
        ],
        "web_feature_service_monitoring_settings": [
            Prefetch(
                "web_feature_service_monitorings",
                queryset=WebFeatureServiceMonitoringSetting.objects.only(
                    "id", "service"),
            )
        ],
        "languages": [
            Prefetch("languages", queryset=Language.objects.only("value"))
        ]
    }
    filterset_class = WebFeatureServiceFilterSet
    search_fields = ("id", "title", "abstract", "keywords__keyword")
    ordering_fields = ["id", "title", "abstract", "hits",
                       "date_stamp", "has_alert", "monitoring_failed_at",
                       "update_review_required_at", "update_failed_at"]
    permission_classes = [DjangoObjectPermissionsOrAnonReadOnly]
    task_function = build_ogc_service

    def get_task_kwargs(self, request, serializer):
        background_process = BackgroundProcess.objects.create(
            phase="Background process created",
            process_type=ProcessNameEnum.REGISTERING.value,
            description=f'Register new service with url {serializer.validated_data["get_capabilities_url"]}'  # noqa
        )

        return {
            "get_capabilities_url": serializer.validated_data["get_capabilities_url"],
            "collect_metadata_records": serializer.validated_data["collect_metadata_records"],
            "service_auth_pk": serializer.service_auth.id if hasattr(serializer, "service_auth") else None,
            "http_request": {
                "path": request.path,
                "method": request.method,
                "content_type": request.content_type,
                "data": request.GET,
                "user_pk": request.user.pk,
            },
            "background_process_pk": background_process.pk
        }

    def get_queryset(self, *args, **kwargs):
        qs = super().get_queryset(*args, **kwargs)
        fields_snake = self.request.GET.get(
            "fields[WebFeatureService]", "").split(',')
        fields = [to_camel(field) for field in fields_snake if field.strip()]

        if not fields or "camouflage" in fields:
            qs = qs.annotate(
                camouflage=Coalesce(
                    F("proxy_setting__camouflage"), V(False)),
            )
        if not fields or "logResponse" in fields:
            qs = qs.annotate(
                log_response=Coalesce(
                    F("proxy_setting__log_response"), V(False)),
            )
        if not fields or "isSecured" in fields:
            qs = qs.annotate(
                is_secured=Exists(
                    AllowedWebFeatureServiceOperation.objects.filter(
                        secured_service__id__exact=OuterRef("pk"),
                    )
                ),
            )
        if not fields or "isSpatialSecured" in fields:
            qs = qs.annotate(
                is_spatial_secured=Exists(
                    AllowedWebFeatureServiceOperation.objects.filter(
                        secured_service__id__exact=OuterRef("pk"),
                        allowed_area__isnull=False
                    )
                )
            )

        qs = self.with_alerts_if_requested(qs)
        return qs


class FeatureTypeViewSetMixin(
    PreloadNotIncludesMixin,
    ServiceElementHistoryInformationViewSetMixin,
):
    # the default reference system is always serialized
    queryset = FeatureType.objects.all().select_related(
        "default_reference_system")
    serializer_class = FeatureTypeSerializer
    filterset_class = FeatureTypeFilterSet
    search_fields = ("id", "title", "abstract", "keywords__keyword")
    ordering_fields = ["id", "title", "abstract", "hits", "date_stamp"]

    select_for_includes = {
        "service": ["service", "service__service_contact", "service__metadata_contact"],
        "service.operation_urls": ["service", "service__service_contact",
                                   "service__metadata_contact"]
    }
    prefetch_for_includes = {
        # the service of a feature type is serialized, all relations of that service
        # are only answered as related resources
        "service": [*WFS_SERVICE_RELATIONS, WFS_OPERATION_URLS_AS_RELATION],
        "service.operation_urls": [
            # only the operation urls are serialized, their mime types and the other
            # relations of the service are answered as related resources
            Prefetch(
                "service__operation_urls",
                queryset=WebFeatureServiceOperationUrl.objects.prefetch_related(
                    MIME_TYPES_AS_RELATION
                ),
            ),
            *WFS_SERVICE_RELATIONS
        ],
        "output_formats": ["output_formats"],
        "keywords": ["keywords"],
        "reference_systems": ["reference_systems"],
    }
    prefetch_for_not_includes = {
        "keywords": [
            Prefetch("keywords", queryset=Keyword.objects.only("id"))
        ],
        "reference_systems": [
            Prefetch(
                "reference_systems", queryset=ReferenceSystem.objects.only("id")
            )
        ],
        "output_formats": [
            Prefetch(
                "output_formats", queryset=MimeType.objects.only("id")
            )
        ],
        "time_extents": [
            Prefetch("time_extents", queryset=TimeExtent.objects.only("id"))
        ],
        "languages": [
            Prefetch("languages", queryset=Language.objects.only("value"))
        ]
    }
    permission_classes = [DjangoObjectPermissionsOrAnonReadOnly]


class FeatureTypeViewSet(
    FeatureTypeViewSetMixin,
    ModelViewSet
):
    """ Endpoints for resource `FeatureType`

        list:
            Retrieves all registered `FeatureType` objects
        retrieve:
            Retrieve one specific `FeatureType` by the given id
        partial_update:
            Endpoint to update some fields of a registered `FeatureType`

    """
    # removes create and delete endpoints, cause this two actions are made by the mrmap system it self in registrion or update processing of the service.
    # delete is only provided on the service endpoint it self, which implicit removes all related objects
    http_method_names = ["get", "patch", "head", "options"]


class NestedFeatureTypeViewSet(
    FeatureTypeViewSetMixin,
    NestedModelViewSet
):
    """ Nested list endpoint for resource `FeatureType`

        list:
            Retrieves all registered `FeatureType` objects

    """


class CatalogueServiceViewSetMixin(
    ServiceAlertAnnotationMixin,
    ServiceExplorerMixin,
    SerializerClassesMixin,
    AsyncCreateMixin,
    ObjectPermissionCheckerViewSetMixin,
    PreloadNotIncludesMixin,
    SparseFieldMixin,
    HistoryInformationViewSetMixin,
):
    """ Endpoints for resource `CatalogueService`

        create:
            Endpoint to register new `CatalogueService` object
        list:
            Retrieves all registered `CatalogueService` objects
        retrieve:
            Retrieve one specific `CatalogueService` by the given id
        partial_update:
            Endpoint to update some fields of a registered `CatalogueService`
        destroy:
            Endpoint to remove a registered `CatalogueService` from the system
    """
    queryset = CatalogueService.objects.all()
    serializer_classes = {
        "default": CatalogueServiceSerializer,
        "create": CatalogueServiceCreateSerializer,
    }
    search_fields = ("id", "title", "abstract", "keywords__keyword")
    filterset_class = CatalogueServiceFilterSet
    ordering_fields = ["id", "title", "abstract", "hits",
                       "date_stamp", "has_alert", "monitoring_failed_at",
                       "update_review_required_at", "update_failed_at",
                       "harvest_failed_at"]
    select_for_includes = {
        # "__all__": ["created_by"],
        "service_contact": ["service_contact"],
        "metadata_contact": ["metadata_contact"],

    }
    prefetch_for_includes = {
        # "__all__": [""],
        "keywords": ["keywords"],
        "operation_urls": [
            Prefetch(
                "operation_urls",
                queryset=CatalogueServiceOperationUrl.objects.select_related(
                    "service"
                ).prefetch_related(MIME_TYPES_AS_RELATION),
            )
        ],
    }
    prefetch_for_not_includes = {
        "keywords": [
            Prefetch(
                "keywords",
                queryset=Keyword.objects.only("id")
            )
        ],
        "harvested_datasets": [
            Prefetch(
                "registry_datasetmetadatarecord_metadata_records",
                queryset=DatasetMetadataRecord.objects.only("id"))
        ],
        "operation_urls": [
            Prefetch(
                "operation_urls",
                queryset=CatalogueServiceOperationUrl.objects.only(
                    "id", "service_id"),
            )
        ],
        "harvesting_jobs": [
            Prefetch(
                "harvesting_jobs",
                queryset=HarvestingJob.objects.only("id", "service")
            )
        ],
        "periodic_harvesting_jobs": [
            Prefetch(
                "periodic_harvesting_jobs",
                queryset=PeriodicHarvestingJob.objects.only("id", "service")
            )
        ],
        "catalogue_service_monitoring_settings": [
            Prefetch(
                "catalogue_service_monitorings",
                queryset=CatalogueServiceMonitoringSetting.objects.only(
                    "id", "service"),
            )
        ],
        "languages": [
            Prefetch("languages", queryset=Language.objects.only("value"))
        ]
    }
    permission_classes = [DjangoObjectPermissionsOrAnonReadOnly]
    task_function = build_ogc_service

    def with_running_harvesting_job(self, qs):
        running_harvesting_job_needed = self.check_sparse_fields_contains(
            "runningHarvestingJob")
        if running_harvesting_job_needed:
            qs = qs.prefetch_related(
                Prefetch(
                    "harvesting_jobs",
                    queryset=HarvestingJob.objects.filter(
                        done_at=None,
                        phase__lt=HarvestingPhaseEnum.COMPLETED.value
                    ).only("id", "service"),
                    to_attr="running_harvesting_job"
                ))

        return qs

    def with_harvesting_stats(self, qs):
        harvested_total_count_needed = self.check_sparse_fields_contains(
            "harvestedTotalCount")
        harvested_dataset_count_needed = self.check_sparse_fields_contains(
            "harvestedDatasetCount") or harvested_total_count_needed
        harvested_service_count_needed = self.check_sparse_fields_contains(
            "harvestedServiceCount") or harvested_total_count_needed

        # --- step 1: aggregate per harvesting_job_id ---
        job_level_kwargs = {}
        if harvested_dataset_count_needed:
            job_level_kwargs["dataset_count"] = Count(
                "id",
                filter=Q(dataset_metadata_record__isnull=False),
            )
        if harvested_service_count_needed:
            job_level_kwargs["service_count"] = Count(
                "id",
                filter=Q(service_metadata_record__isnull=False),
            )
        relation_agg = CTE(
            HarvestedMetadataRelation.objects
            .filter(~Q(collecting_state=CollectingStatenEnum.DUPLICATED.value))
            .values("harvesting_job_id")
            .annotate(**job_level_kwargs),
            name="relation_agg",
        )

        # --- step 2: join by harvestingjob + aggregation per service id
        cte_kwargs = {}
        if harvested_dataset_count_needed:
            cte_kwargs.update({
                "dataset_count": Sum(relation_agg.col.dataset_count)
            })
        if harvested_service_count_needed:
            cte_kwargs.update({
                "service_count": Sum(relation_agg.col.service_count)
            })
        cte = CTE(
            relation_agg.join(
                HarvestingJob,
                id=relation_agg.col.harvesting_job_id,
            )
            .values("service_id")
            .annotate(**cte_kwargs),
            name="cte",
        )

        if harvested_total_count_needed or harvested_dataset_count_needed or harvested_service_count_needed:
            qs = with_cte(
                cte,
                relation_agg,
                select=cte.join(model_or_queryset=qs,
                                id=cte.col.service_id,
                                _join_type=LOUTER
                                )
            )

        # --- step 3: annotation of the final values
        annotate_kwargs = {}
        if harvested_total_count_needed:
            annotate_kwargs.update({
                "harvested_dataset_count": Coalesce(cte.col.dataset_count, 0),
                "harvested_service_count": Coalesce(cte.col.service_count, 0),
                "harvested_total_count": Coalesce(F("harvested_dataset_count"), 0) + Coalesce(F("harvested_service_count"), 0)
            })
        if harvested_dataset_count_needed:
            annotate_kwargs.update({
                "harvested_dataset_count": Coalesce(cte.col.dataset_count, 0)
            })
        if harvested_service_count_needed:
            annotate_kwargs.update({
                "harvested_service_count": Coalesce(cte.col.service_count, 0),
            })
        if annotate_kwargs:
            qs = qs.annotate(**annotate_kwargs)
        return qs

    def get_queryset(self, *args, **kwargs):
        qs = super().get_queryset(*args, **kwargs)
        qs = self.with_harvesting_stats(qs)
        qs = self.with_running_harvesting_job(qs)
        qs = self.with_alerts_if_requested(qs)
        return qs

    def get_task_kwargs(self, request, serializer):
        background_process = BackgroundProcess.objects.create(
            phase="Background process created",
            process_type=ProcessNameEnum.REGISTERING.value,
            description=f'Register new service with url {serializer.validated_data["get_capabilities_url"]}'  # noqa
        )
        return {
            "get_capabilities_url": serializer.validated_data["get_capabilities_url"],
            "collect_metadata_records": False,  # CSW has no remote metadata records
            "service_auth_pk": serializer.service_auth.id if hasattr(serializer, "service_auth") else None,
            "http_request": {
                "path": request.path,
                "method": request.method,
                "content_type": request.content_type,
                "data": request.GET,
                "user_pk": request.user.pk,
            },
            "background_process_pk": background_process.pk
        }


@extend_schema_view(preview=extend_schema(operation_id="preview_CatalogueService"))
class CatalogueServiceViewSet(
    ServicePreviewMixin,
    CatalogueServiceViewSetMixin,
    ModelViewSet
):
    pass


class NestedCatalogueServiceViewSet(
    CatalogueServiceViewSetMixin,
    NestedModelViewSet
):
    pass


class CatalogueServiceOperationUrlViewSetMixin(
):
    queryset = CatalogueServiceOperationUrl.objects.all()
    serializer_class = CatalogueServiceOperationUrlSerializer
    search_fields = ("id", "service")
    permission_classes = [DjangoObjectPermissionsOrAnonReadOnly]
    ordering_fields = ["id"]


class CatalogueServiceOperationUrlViewSet(
    CatalogueServiceOperationUrlViewSetMixin,
    ModelViewSet
):
    """ Endpoints for resource `CatalogueServiceOperationUrl`

        list:
            Retrieves all registered `CatalogueServiceOperationUrl` objects
        retrieve:
            Retrieve one specific `CatalogueServiceOperationUrl` by the given id
        partial_update:
            Endpoint to update some fields of a registered `CatalogueServiceOperationUrl`

    """
    # removes create and delete endpoints, cause this two actions are made by the mrmap system it self in registrion or update processing of the service.
    # delete is only provided on the service endpoint it self, which implicit removes all related objects
    http_method_names = ["get", "patch", "head", "options"]


class NestedCatalogueServiceOperationUrlViewSet(
    CatalogueServiceOperationUrlViewSetMixin,
    NestedModelViewSet
):
    """ Nested list endpoint for resource `CatalogueServiceOperationUrl`

        list:
            Retrieves all registered `CatalogueServiceOperationUrl` objects

    """


class NestedWebMapServiceViewSet(NestedModelViewSet, WebMapServiceViewSet):
    http_method_names = ["get", "head", "options"]


class NestedWebFeatureServiceViewSet(NestedModelViewSet, WebFeatureServiceViewSet):
    http_method_names = ["get", "head", "options"]
