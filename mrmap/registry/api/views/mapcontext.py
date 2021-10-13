from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet

from registry.models import MapContext


class MapContextViewSet(ModelViewSet):
    queryset = MapContext.objects.all()
    filterset_class = None
    pagination_class = None

    serializers = {
        'default': None
    }

    def get_serializer_class(self):
        return self.serializers.get(self.action, self.serializers['default'])

    def get_queryset(self, *args, **kwargs):
        return super().get_queryset(args, kwargs)

    @action(detail=False, permission_classes=())
    def list(self, request, *args, **kwargs):
        """
        Returns the existing MapContexts
        """
        queryset = self.get_queryset()
        serializer = self.get_serializer(queryset, many=True)
        return Response(data=serializer.data, status=status.HTTP_200_OK)