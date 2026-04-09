from extras.permissions import DjangoObjectPermissionsOrAnonReadOnly
from extras.viewsets import NestedModelViewSet, PreloadNotIncludesMixin
from registry.models.update import LayerMapping, WebMapServiceUpdateJob
from registry.serializers.update import (LayerMappingSerializer,
                                         WebMapServiceUpdateJobSerializer)
from rest_framework_json_api.views import ModelViewSet


class WebMapServiceUpdateJobViewSetMixin(PreloadNotIncludesMixin):
    queryset = WebMapServiceUpdateJob.objects.all()
    serializer_class = WebMapServiceUpdateJobSerializer
    permission_classes = [DjangoObjectPermissionsOrAnonReadOnly]
    filterset_fields = ("service", "status", "date_created", "done_at")
    ordering_fields = ("id", "date_created", "done_at", "status")


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
    filterset_fields = ("job", "new_layer", "old_layer",
                        "created", "is_confirmed")
    ordering_fields = ("id", "job", "new_layer", "old_layer",
                       "created", "is_confirmed")


class LayerMappingViewSet(
        LayerMappingViewSetMixin,
        ModelViewSet):
    """ Endpoints for resource `LayerMapping`"""


class NestedLayerMappingViewSet(
        LayerMappingViewSetMixin,
        NestedModelViewSet):
    """ Nested list endpoint for resource `LayerMapping` """
