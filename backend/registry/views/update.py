from django.db.models import (Case, IntegerField, OuterRef, Prefetch, Q,
                              Subquery, Sum, Value, When)
from extras.permissions import DjangoObjectPermissionsOrAnonReadOnly
from extras.viewsets import NestedModelViewSet, PreloadNotIncludesMixin
from registry.filters.update import (CatalogueServiceUpdateJobFilterSet,
                                     FeatureTypeMappingFilterSet,
                                     LayerMappingFilterSet,
                                     WebFeatureServiceUpdateJobFilterSet,
                                     WebMapServiceUpdateJobFilterSet)
from registry.models import (CatalogueServiceUpdateJob,
                             CatalogueServiceUpdateSetting, FeatureTypeMapping,
                             LayerMapping, WebFeatureServiceUpdateJob,
                             WebFeatureServiceUpdateSetting,
                             WebMapServiceUpdateJob,
                             WebMapServiceUpdateSetting)
from registry.models.metadata import Keyword
from registry.models.monitoring import WebMapServiceMonitoringSetting
from registry.models.security import (AllowedWebMapServiceOperation,
                                      WebMapServiceProxySetting)
from registry.models.service import (Layer, WebMapService,
                                     WebMapServiceOperationUrl)
from registry.querys.historical import with_delta_size
from registry.serializers.update import (
    CatalogueServiceUpdateJobSerializer,
    CatalogueServiceUpdateSettingSerializer, FeatureTypeMappingSerializer,
    LayerMappingSerializer, WebFeatureServiceUpdateJobSerializer,
    WebFeatureServiceUpdateSettingSerializer, WebMapServiceUpdateJobSerializer,
    WebMapServiceUpdateSettingSerializer)
from rest_framework.response import Response
from rest_framework_json_api.views import ModelViewSet
from simple_history.utils import get_history_manager_for_model


class WebMapServiceUpdateSettingViewSetMixing:
    queryset = WebMapServiceUpdateSetting.objects.select_related('crontab')
    serializer_class = WebMapServiceUpdateSettingSerializer
    permission_classes = [DjangoObjectPermissionsOrAnonReadOnly]
    filterset_fields = ('service', )
    ordering_fields = ("id", "service")


class WebMapServiceUpdateSettingViewSet(
        WebMapServiceUpdateSettingViewSetMixing,
        ModelViewSet):
    """ Endpoints for resource `WebMapServiceUpdateSetting`"""


class NestedWebMapServiceUpdateSettingViewSet(
        WebMapServiceUpdateSettingViewSetMixing,
        NestedModelViewSet):
    """ Nested list endpoint for resource `WebMapServiceUpdateSetting` """


class WebMapServiceUpdateJobViewSetMixin(PreloadNotIncludesMixin):
    queryset = WebMapServiceUpdateJob.objects.all()
    serializer_class = WebMapServiceUpdateJobSerializer
    permission_classes = [DjangoObjectPermissionsOrAnonReadOnly]
    filterset_class = WebMapServiceUpdateJobFilterSet
    ordering_fields = ("id", "date_created", "done_at", "status")
    select_for_includes = {
        # "service": ["webmapservice_update_candidate"],
    }
    prefetch_for_includes = {
        "service": [
            Prefetch(
                "service",
                queryset=WebMapService.objects.select_related(
                    "proxy_setting", "webmapservice_update_candidate"
                ).prefetch_related(
                    Prefetch(
                        "keywords",
                        queryset=Keyword.objects.only("id")
                    ),
                    Prefetch(
                        "allowed_operations",
                        queryset=AllowedWebMapServiceOperation.objects.only(
                            "id", "secured_service")
                    ),
                    Prefetch(
                        "operation_urls",
                        queryset=WebMapServiceOperationUrl.objects.only(
                            "id", "service"),
                    ),
                    Prefetch(
                        "web_map_service_monitorings",
                        queryset=WebMapServiceMonitoringSetting.objects.only(
                            "id", "service"),
                    ),
                    Prefetch(
                        "web_map_service_update_settings",
                        queryset=WebMapServiceUpdateSetting.objects.only(
                            "id", "service"),
                    ),
                    Prefetch(
                        "layers",
                        queryset=Layer.objects.only(
                            "id",
                            "service_id",
                            "mptt_tree_id",
                            "mptt_lft",
                        ),
                    ),
                    "languages",
                )
            )
        ],
        "update_candidate": [
            Prefetch(
                "service__webmapservice_update_candidate",
                queryset=WebMapService.objects.select_related(
                    "proxy_setting",
                ).prefetch_related(
                    Prefetch(
                        "keywords",
                        queryset=Keyword.objects.only("id")
                    ),
                    Prefetch(
                        "allowed_operations",
                        queryset=AllowedWebMapServiceOperation.objects.only(
                            "id", "secured_service")
                    ),
                    Prefetch(
                        "operation_urls",
                        queryset=WebMapServiceOperationUrl.objects.only(
                            "id", "service"),
                    ),
                    Prefetch(
                        "web_map_service_monitorings",
                        queryset=WebMapServiceMonitoringSetting.objects.only(
                            "id", "service"),
                    ),
                    Prefetch(
                        "web_map_service_update_settings",
                        queryset=WebMapServiceUpdateSetting.objects.only(
                            "id", "service"),
                    ),
                    Prefetch(
                        "layers",
                        queryset=Layer.objects.only(
                            "id",
                            "service_id",
                            "mptt_tree_id",
                            "mptt_lft",
                        ),
                    ),
                    "languages",
                )
            )
        ],
        "mappings": [
            Prefetch(
                "mappings",
                queryset=LayerMapping.objects.select_related(
                    "job", "new_layer", "old_layer"),
            ),
        ],
    }
    prefetch_for_not_includes = {
        "mappings": [
            Prefetch(
                "mappings",
                queryset=LayerMapping.objects.only(
                    "id",
                    "job_id",
                    "new_layer_id",
                    "old_layer_id",
                ),
            ),
        ],
        "service": [
            Prefetch(
                "service",
                queryset=WebMapService.objects.only("id")
            )
        ],
        "update_candidate": [
            Prefetch(
                "service__webmapservice_update_candidate",
                queryset=WebMapService.objects.only("id")
            )
        ]

    }

    def _prefill_layer_change_aggregates(self, jobs):
        if not jobs:
            return

        reasons = [f"updatejob_id: {job.pk}" for job in jobs]
        previous_records = (
            get_history_manager_for_model(Layer)
            .filter(
                id=OuterRef("id"),
                history_date__lt=OuterRef("history_date"),
            )
            .order_by("-history_date")
        )
        history_qs = Layer.change_log.model.objects.filter(
            history_change_reason__in=reasons,
        ).annotate(
            prev_record_id=Subquery(previous_records.values("history_id")[:1])
        )
        aggregates = (
            with_delta_size(history_qs)
            .annotate(
                is_added=Case(
                    When(Q(history_type="+") |
                         Q(prev_record_id__isnull=True), then=Value(1)),
                    default=Value(0),
                    output_field=IntegerField(),
                ),
                is_deleted=Case(
                    When(history_type="-", then=Value(1)),
                    default=Value(0),
                    output_field=IntegerField(),
                ),
                is_changed=Case(
                    When(Q(history_type="~") & Q(
                        _delta_size__gt=0), then=Value(1)),
                    default=Value(0),
                    output_field=IntegerField(),
                ),
                is_unchanged=Case(
                    When(Q(history_type="~") & Q(_delta_size=0), then=Value(1)),
                    default=Value(0),
                    output_field=IntegerField(),
                ),
            )
            .values("history_change_reason")
            .annotate(
                changed_layers=Sum("is_changed"),
                unchanged_layers=Sum("is_unchanged"),
                added_layers=Sum("is_added"),
                deleted_layers=Sum("is_deleted"),
            )
        )

        totals_by_reason = {
            row["history_change_reason"]: row
            for row in aggregates
        }
        for job in jobs:
            reason = f"updatejob_id: {job.pk}"
            totals = totals_by_reason.get(reason, {})
            job._layer_change_aggregates_cache = {
                "changed_layers": totals.get("changed_layers") or 0,
                "unchanged_layers": totals.get("unchanged_layers") or 0,
                "added_layers": totals.get("added_layers") or 0,
                "deleted_layers": totals.get("deleted_layers") or 0,
            }

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        if page is not None:
            self._prefill_layer_change_aggregates(page)
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        self._prefill_layer_change_aggregates(queryset)
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        self._prefill_layer_change_aggregates([instance])
        serializer = self.get_serializer(instance)
        return Response(serializer.data)


class WebMapServiceUpdateJobViewSet(
        WebMapServiceUpdateJobViewSetMixin,
        ModelViewSet):
    """ Endpoints for resource `WebMapServiceUpdateJob`"""


class NestedWebMapServiceUpdateJobViewSet(
        WebMapServiceUpdateJobViewSetMixin,
        NestedModelViewSet):
    """ Nested list endpoint for resource `WebMapServiceUpdateJob` """


class LayerMappingViewSetMixin(PreloadNotIncludesMixin):
    queryset = LayerMapping.objects.select_related("old_layer", "new_layer")
    serializer_class = LayerMappingSerializer
    permission_classes = [DjangoObjectPermissionsOrAnonReadOnly]
    filterset_class = LayerMappingFilterSet
    ordering_fields = ("id", "job", "new_layer", "old_layer",
                       "created", "is_confirmed")
    select_for_includes = {
        "job": ["job"],
    }
    http_method_names = ["get", "patch"]  # disable PUT


class LayerMappingViewSet(
        LayerMappingViewSetMixin,
        ModelViewSet):
    """ Endpoints for resource `LayerMapping`"""


class NestedLayerMappingViewSet(
        LayerMappingViewSetMixin,
        NestedModelViewSet):
    """ Nested list endpoint for resource `LayerMapping` """


class WebFeatureServiceUpdateSettingViewSetMixing:
    queryset = WebFeatureServiceUpdateSetting.objects.select_related('crontab')
    serializer_class = WebFeatureServiceUpdateSettingSerializer
    permission_classes = [DjangoObjectPermissionsOrAnonReadOnly]
    filterset_fields = ('service', )
    ordering_fields = ("id", "service")


class WebFeatureServiceUpdateSettingViewSet(
        WebFeatureServiceUpdateSettingViewSetMixing,
        ModelViewSet):
    """ Endpoints for resource `WebFeatureServiceUpdateSetting`"""


class NestedWebFeatureServiceUpdateSettingViewSet(
        WebFeatureServiceUpdateSettingViewSetMixing,
        NestedModelViewSet):
    """ Nested list endpoint for resource `WebFeatureServiceUpdateSetting` """


class WebFeatureServiceUpdateJobViewSetMixin(PreloadNotIncludesMixin):
    queryset = WebFeatureServiceUpdateJob.objects.all()
    serializer_class = WebFeatureServiceUpdateJobSerializer
    permission_classes = [DjangoObjectPermissionsOrAnonReadOnly]
    filterset_class = WebFeatureServiceUpdateJobFilterSet
    ordering_fields = ("id", "date_created", "done_at", "status")
    select_for_includes = {
        "service": ["service"],
        "update_candidate": ["update_candidate"],
    }
    prefetch_for_includes = {
        "mappings": [
            Prefetch(
                "mappings",
                queryset=FeatureTypeMapping.objects.select_related(
                    "job",
                    "new_featuretype",
                    "old_featuretype",
                ),
            )
        ],
    }
    prefetch_for_not_includes = {
        "mappings": [
            Prefetch(
                "mappings",
                queryset=FeatureTypeMapping.objects.only(
                    "id",
                    "job_id",
                    "new_featuretype_id",
                    "old_featuretype_id",
                ),
            )
        ],
    }


class WebFeatureServiceUpdateJobViewSet(WebFeatureServiceUpdateJobViewSetMixin, ModelViewSet):
    """Endpoints for resource `WebFeatureServiceUpdateJob`"""


class NestedWebFeatureServiceUpdateJobViewSet(WebFeatureServiceUpdateJobViewSetMixin, NestedModelViewSet):
    """Nested list endpoint for resource `WebFeatureServiceUpdateJob`"""


class FeatureTypeMappingViewSetMixin(PreloadNotIncludesMixin):
    queryset = FeatureTypeMapping.objects.all()
    serializer_class = FeatureTypeMappingSerializer
    permission_classes = [DjangoObjectPermissionsOrAnonReadOnly]
    filterset_class = FeatureTypeMappingFilterSet
    ordering_fields = ("id", "job", "new_featuretype",
                       "old_featuretype", "created", "is_confirmed")
    select_for_includes = {
        "job": ["job"],
    }
    http_method_names = ["get", "patch"]  # disable PUT


class FeatureTypeMappingViewSet(FeatureTypeMappingViewSetMixin, ModelViewSet):
    """Endpoints for resource `FeatureTypeMapping`"""


class NestedFeatureTypeMappingViewSet(FeatureTypeMappingViewSetMixin, NestedModelViewSet):
    """Nested list endpoint for resource `FeatureTypeMapping`"""


class CatalogueServiceUpdateSettingViewSetMixing:
    queryset = CatalogueServiceUpdateSetting.objects.select_related('crontab')
    serializer_class = CatalogueServiceUpdateSettingSerializer
    permission_classes = [DjangoObjectPermissionsOrAnonReadOnly]
    filterset_fields = ('service', )
    ordering_fields = ("id", "service")


class CatalogueServiceUpdateSettingViewSet(
        CatalogueServiceUpdateSettingViewSetMixing,
        ModelViewSet):
    """ Endpoints for resource `CatalogueServiceUpdateSetting`"""


class NestedCatalogueServiceUpdateSettingViewSet(
        CatalogueServiceUpdateSettingViewSetMixing,
        NestedModelViewSet):
    """ Nested list endpoint for resource `CatalogueServiceUpdateSetting` """


class CatalogueServiceUpdateJobViewSetMixin:
    queryset = CatalogueServiceUpdateJob.objects.all()
    serializer_class = CatalogueServiceUpdateJobSerializer
    permission_classes = [DjangoObjectPermissionsOrAnonReadOnly]
    filterset_class = CatalogueServiceUpdateJobFilterSet
    ordering_fields = ("id", "date_created", "done_at", "status")
    select_for_includes = {
        "service": ["service"],
        "update_candidate": ["update_candidate"],
    }


class CatalogueServiceUpdateJobViewSet(CatalogueServiceUpdateJobViewSetMixin, ModelViewSet):
    """Endpoints for resource `CatalogueServiceUpdateJob`"""


class NestedCatalogueServiceUpdateJobViewSet(CatalogueServiceUpdateJobViewSetMixin, NestedModelViewSet):
    """Nested list endpoint for resource `CatalogueServiceUpdateJob`"""
