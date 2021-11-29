
from rest_framework.serializers import Serializer
from rest_framework_json_api.schemas.openapi import AutoSchema
from rest_framework_extensions.mixins import NestedViewSetMixin
from rest_framework_json_api.views import ModelViewSet, RelationshipView
from registry.api.serializers.mapcontext import MapContextLayerMoveLayerSerializer, MapContextSerializer, MapContextLayerSerializer
from registry.models import MapContext, MapContextLayer
from rest_framework.decorators import action
from rest_framework import status
from rest_framework.response import Response

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
    serializer_classes = {
        "default": MapContextLayerSerializer,
        "move_to": MapContextLayerMoveLayerSerializer,
    }

    def get_queryset(self):
        queryset = super(MapContextLayerViewSet, self).get_queryset()
        if 'map_context_pk' in self.kwargs:
            map_context_pk = self.kwargs['map_context_pk']
            queryset = queryset.filter(map_context__pk=map_context_pk)
        return queryset

    def get_serializer_class(self):
        return self.serializer_classes.get(self.action, self.serializer_classes['default'])

    @action(detail=True, methods=['post'])
    def move_to(self, request, pk=None):
        current_node = self.get_object()

        serializer = MapContextLayerMoveLayerSerializer(data=request.data)
        if serializer.is_valid():
            current_node.move_to(target=serializer.validated_data['target'], position=serializer.validated_data['position'])
            return Response(MapContextLayerSerializer(current_node, context={'request': request}).data, status=status.HTTP_200_OK)
        else:
            return Response(serializer.errors,
                            status=status.HTTP_400_BAD_REQUEST)