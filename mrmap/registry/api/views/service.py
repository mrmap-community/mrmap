from django_filters import rest_framework as api_filters
from rest_framework.filters import OrderingFilter

from rest_framework import status
from rest_framework.permissions import DjangoModelPermissions
from rest_framework.viewsets import ModelViewSet
from rest_framework.response import Response

from extras.api.pagination import StandardResultsSetPagination
from registry.api.filters.service import ServiceApiFilter, FeatureTypeApiFilter, LayerApiFilter
from registry.api.serializers.service import ServiceSerializer, FeatureTypeSerializer, LayerSerializer
from registry.models import Service, Layer, FeatureType


class ServiceViewSet(ModelViewSet):
    queryset = Service.objects.all()
    filterset_class = ServiceApiFilter
    filter_backends = [api_filters.DjangoFilterBackend, OrderingFilter]
    ordering_fields = ['title', 'abstract', 'id']
    pagination_class = StandardResultsSetPagination
    permission_classes = [DjangoModelPermissions]

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


class LayerViewSet(ModelViewSet):
    queryset = Layer.objects.all()
    filterset_class = LayerApiFilter
    filter_backends = [api_filters.DjangoFilterBackend, OrderingFilter]
    ordering_fields = ['title', 'abstract', 'id']
    pagination_class = StandardResultsSetPagination
    permission_classes = [DjangoModelPermissions]

    serializers = {
        'default': LayerSerializer
    }

    def get_serializer_class(self):
        return self.serializers.get(self.action, self.serializers['default'])

    def get_serialized_status_ok_response(self, _queryset, _many=True, _status=status.HTTP_200_OK):
        serializer = self.get_serializer(_queryset, many=_many)
        return Response(data=serializer.data, status=_status)

    def get_queryset(self, *args, **kwargs):
        return super().get_queryset()


class FeatureTypeViewSet(ModelViewSet):
    queryset = FeatureType.objects.all()
    filterset_class = FeatureTypeApiFilter
    filter_backends = [api_filters.DjangoFilterBackend, OrderingFilter]
    ordering_fields = ['title', 'abstract', 'id']
    pagination_class = StandardResultsSetPagination
    permission_classes = [DjangoModelPermissions]

    serializers = {
        'default': FeatureTypeSerializer
    }

    def get_serializer_class(self):
        return self.serializers.get(self.action, self.serializers['default'])

    def get_serialized_status_ok_response(self, _queryset, _many=True, _status=status.HTTP_200_OK):
        serializer = self.get_serializer(_queryset, many=_many)
        return Response(data=serializer.data, status=_status)

    def get_queryset(self, *args, **kwargs):
        return super().get_queryset()
