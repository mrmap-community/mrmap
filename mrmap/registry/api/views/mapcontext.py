from rest_framework import status
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet

from registry.api.serializers.mapcontext import MapContextSerializer, MapContextOWSSerializer
from registry.models import MapContext


class MapContextViewSet(ModelViewSet):
    queryset = MapContext.objects.all()
    filterset_class = None  # TODO
    pagination_class = None  # TODO
    # permission_classes = None # TODO

    serializers = {
        'default': MapContextSerializer,
        # retrieve is the name of the default method to get a MapContextInstance by a given PK.
        # We only need to replace the way the serializer is structured
        'retrieve': MapContextOWSSerializer
    }

    def get_serializer_class(self):
        return self.serializers.get(self.action, self.serializers['default'])

    def get_serialized_status_ok_response(self, _queryset, _many=True, _status=status.HTTP_200_OK):
        serializer = self.get_serializer(_queryset, many=_many)
        return Response(data=serializer.data, status=_status)

    def get_queryset(self, *args, **kwargs):
        return super().get_queryset()
