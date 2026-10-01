from django.db.models import Prefetch
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
from registry.serializers.update import (
    CatalogueServiceUpdateJobSerializer,
    CatalogueServiceUpdateSettingSerializer, FeatureTypeMappingSerializer,
    LayerMappingSerializer, WebFeatureServiceUpdateJobSerializer,
    WebFeatureServiceUpdateSettingSerializer, WebMapServiceUpdateJobSerializer,
    WebMapServiceUpdateSettingSerializer)
from rest_framework_json_api.views import ModelViewSet


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
        "service": ["service"],
        "update_candidate": ["update_candidate"],
    }
    prefetch_for_includes = {
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
    }


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
