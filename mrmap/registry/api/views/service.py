from django_filters import rest_framework as api_filters

from rest_framework import status
from rest_framework.viewsets import ModelViewSet
from rest_framework.response import Response

from registry.api.filters.service import ServiceFilter
from registry.api.serializers.service import ServiceSerializer
from registry.models import Service


class ServiceViewSet(ModelViewSet):
    queryset = Service.objects.all()
    filterset_class = ServiceFilter
    filter_backends = [api_filters.DjangoFilterBackend]
    # pagination_class = None  # TODO
    # permission_classes = None # TODO

    serializers = {
        'default': ServiceSerializer
    }

    def get_serializer_class(self):
        return self.serializers.get(self.action, self.serializers['default'])

    def get_serialized_status_ok_response(self, _queryset, _many=True, _status=status.HTTP_200_OK):
        serializer = self.get_serializer(_queryset, many=_many)
        return Response(data=serializer.data, status=_status)

    def get_queryset(self, *args, **kwargs):
        return super().get_queryset()
