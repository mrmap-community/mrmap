
from extras.permissions import DjangoObjectPermissionsOrAnonReadOnly
from registry.models import MapContext, MapContextLayer
from registry.serializers.mapcontext import (
    MapContextDefaultSerializer, MapContextIncludeSerializer,
    MapContextLayerMoveLayerSerializer, MapContextLayerSerializer)
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework_extensions.mixins import NestedViewSetMixin
from rest_framework_json_api.schemas.openapi import AutoSchema
from rest_framework_json_api.views import ModelViewSet, RelationshipView


class MapContextRelationshipView(RelationshipView):
    schema = AutoSchema(
        tags=['MapContext'],
    )
    queryset = MapContext.objects
    permission_classes = [DjangoObjectPermissionsOrAnonReadOnly]


class MapContextLayerRelationshipView(RelationshipView):
    schema = AutoSchema(
        tags=['MapContext'],
    )
    queryset = MapContextLayer.objects
    permission_classes = [DjangoObjectPermissionsOrAnonReadOnly]


class MapContextViewSet(NestedViewSetMixin, ModelViewSet):
    schema = AutoSchema(
        tags=['MapContext'],
    )
    queryset = MapContext.objects.with_meta()
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
        if self.request and 'include' in self.request.query_params:
            return self.serializer_classes["include"]
        return self.serializer_classes.get(
            self.action, self.serializer_classes["default"]
        )


class MapContextLayerViewSet(ModelViewSet):
    schema = AutoSchema(
        tags=['MapContext'],
    )
    queryset = MapContextLayer.objects.all()
    serializer_classes = {
        "default": MapContextLayerSerializer,
        "move_to": MapContextLayerMoveLayerSerializer,
    }
    permission_classes = [DjangoObjectPermissionsOrAnonReadOnly]

    def get_queryset(self):
        queryset = super(MapContextLayerViewSet, self).get_queryset()
        if 'parent_lookup_map_context' in self.kwargs:
            queryset = queryset.filter(
                map_context__id=self.kwargs['parent_lookup_map_context'])
        return queryset

    def get_serializer_class(self):
        return self.serializer_classes.get(self.action, self.serializer_classes['default'])

    @action(detail=True, methods=['post'])
    def move_to(self, request, pk=None):
        current_node = self.get_object()

        serializer = MapContextLayerMoveLayerSerializer(data=request.data)
        if serializer.is_valid():
            current_node.move_to(
                target=serializer.validated_data['target'], position=serializer.validated_data['position'])
            return Response(MapContextLayerSerializer(current_node, context={'request': request}).data, status=status.HTTP_200_OK)
        else:
            return Response(serializer.errors,
                            status=status.HTTP_400_BAD_REQUEST)
