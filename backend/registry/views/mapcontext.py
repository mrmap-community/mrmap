
from extras.openapi import CustomAutoSchema
from extras.permissions import DjangoObjectPermissionsOrAnonReadOnly
from extras.viewsets import NestedModelViewSet
from registry.models import MapContext, MapContextLayer
from registry.serializers.mapcontext import (
    MapContextDefaultSerializer, MapContextIncludeSerializer,
    MapContextLayerMoveLayerSerializer, MapContextLayerSerializer)
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response
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


class MapContextLayerViewSetMixin():
    schema = CustomAutoSchema(
        tags=['MapContext'],
    )
    queryset = MapContextLayer.objects.all()
    serializer_classes = {
        "default": MapContextLayerSerializer,
        "move_to": MapContextLayerMoveLayerSerializer,
    }
    permission_classes = [DjangoObjectPermissionsOrAnonReadOnly]

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
