
from rest_framework_json_api.schemas.openapi import AutoSchema
from rest_framework_extensions.mixins import NestedViewSetMixin
from rest_framework_json_api.views import ModelViewSet, RelationshipView
from registry.api.serializers.mapcontext import MapContextSerializer, MapContextLayerSerializer
from registry.models import MapContext, MapContextLayer


class MapContextRelationshipView(RelationshipView):
    schema = AutoSchema(
        tags=['MapContext'],
    )
    queryset = MapContext.objects

class MapContextLayerRelationshipView(RelationshipView):
    schema = AutoSchema(
        tags=['MapContext'],
    )
    queryset = MapContextLayer.objects

class MapContextViewSet(NestedViewSetMixin, ModelViewSet):
    schema = AutoSchema(
        tags=['MapContext'],
    )
    queryset = MapContext.objects.all()
    serializer_class = MapContextSerializer
    prefetch_for_includes = {
        '__all__': [],
        'map_context_layers': ['map_context_layers']
    }


class MapContextLayerViewSet(ModelViewSet):
    schema = AutoSchema(
        tags=['MapContext'],
    )
    queryset = MapContextLayer.objects.all()
    serializer_class = MapContextLayerSerializer

    def get_queryset(self):
        queryset = super(MapContextLayerViewSet, self).get_queryset()
        if 'map_context_pk' in self.kwargs:
            map_context_pk = self.kwargs['map_context_pk']
            queryset = queryset.filter(map_context__pk=map_context_pk)
        return queryset
