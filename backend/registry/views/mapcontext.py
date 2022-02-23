
from extras.openapi import CustomAutoSchema
from extras.permissions import DjangoObjectPermissionsOrAnonReadOnly
from extras.viewsets import NestedModelViewSet, SerializerClassesMixin
from registry.models import MapContext, MapContextLayer
from registry.serializers.mapcontext import (
    MapContextDefaultSerializer, MapContextIncludeSerializer,
    MapContextLayerPostOrPatchSerializer, MapContextLayerSerializer)
from rest_framework_json_api.views import ModelViewSet


class MapContextViewSet(ModelViewSet):
    schema = CustomAutoSchema(
        tags=['MapContext'],
    )
    queryset = MapContext.objects.all()
    serializer_classes = {
        'default': MapContextDefaultSerializer,
        'include': MapContextIncludeSerializer
    }
    prefetch_for_includes = {
        '__all__': [],
        'map_context_layers': ['map_context_layers']
    }
    permission_classes = [DjangoObjectPermissionsOrAnonReadOnly]

    def get_serializer_class(self):
        # if we detect include as queryparam, we need to switch the serializer,
        # cause the default serializer uses HyperlinkedRelatedField to render related fields.
        if self.request and 'include' in self.request.query_params:
            return self.serializer_classes["include"]
        return self.serializer_classes.get(
            self.action, self.serializer_classes["default"]
        )


class MapContextLayerViewSetMixin(SerializerClassesMixin):
    schema = CustomAutoSchema(
        tags=['MapContextLayer'],

    )
    queryset = MapContextLayer.objects.all()
    serializer_classes = {
        "default": MapContextLayerSerializer,
        "post": MapContextLayerPostOrPatchSerializer,
        "patch": MapContextLayerPostOrPatchSerializer,

    }
    permission_classes = [DjangoObjectPermissionsOrAnonReadOnly]


class MapContextLayerViewSet(
    MapContextLayerViewSetMixin,
    ModelViewSet
):
    pass


class NestedMapContextLayerViewSet(
    MapContextLayerViewSetMixin,
    NestedModelViewSet
):
    pass
