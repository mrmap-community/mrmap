from django.db.models import Prefetch
from extras.permissions import DjangoObjectPermissionsOrAnonReadOnly
from extras.viewsets import NestedModelViewSet, PreloadNotIncludesMixin
from registry.filters.update import (
    FeatureTypeMappingFilterSet,
    LayerMappingFilterSet,
    WebFeatureServiceUpdateJobFilterSet,
    WebMapServiceUpdateJobFilterSet,
)
from registry.models import (
    FeatureTypeMapping,
    LayerMapping,
    WebFeatureServiceUpdateJob,
    WebMapServiceUpdateJob,
)
from registry.serializers.update import (
    FeatureTypeMappingSerializer,
    LayerMappingSerializer,
    WebFeatureServiceUpdateJobSerializer,
    WebMapServiceUpdateJobSerializer,
)
from rest_framework_json_api.views import ModelViewSet


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
                    "job", "new_layer", "old_layer")
            )

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
            )
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
    queryset = LayerMapping.objects.all()
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
    ordering_fields = ("id", "job", "new_featuretype", "old_featuretype", "created", "is_confirmed")
    select_for_includes = {
        "job": ["job"],
    }
    http_method_names = ["get", "patch"]  # disable PUT


class FeatureTypeMappingViewSet(FeatureTypeMappingViewSetMixin, ModelViewSet):
    """Endpoints for resource `FeatureTypeMapping`"""


class NestedFeatureTypeMappingViewSet(FeatureTypeMappingViewSetMixin, NestedModelViewSet):
    """Nested list endpoint for resource `FeatureTypeMapping`"""
