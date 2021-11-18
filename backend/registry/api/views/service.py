from django_filters import rest_framework as api_filters
from rest_framework.filters import OrderingFilter
from rest_framework.permissions import DjangoObjectPermissions

from extras.api import viewsets
from extras.api.pagination import StandardResultsSetPagination
from extras.api.viewsets import ModelViewSetWithPermissionChecker
from registry.api.filters.service import ServiceApiFilter, FeatureTypeApiFilter, LayerApiFilter
from registry.api.serializers.service import ServiceSerializer, FeatureTypeSerializer, LayerSerializer
from registry.models import Service, Layer, FeatureType


class ServiceViewSet(viewsets.ModelViewSet):
    queryset = Service.objects.all()
    #filterset_class = ServiceApiFilter
    filter_backends = [api_filters.DjangoFilterBackend, OrderingFilter]
    ordering_fields = ['title', 'abstract', 'id']
    #pagination_class = StandardResultsSetPagination
    # permission_classes = [DjangoObjectPermissions]

    serializers = {
        'default': ServiceSerializer
    }

    def get_serializer_class(self):
        return self.serializers.get(self.action, self.serializers['default'])

    # TODO: add to mixin (not needed for now. Will come in handy when we need to start overwriting methods)
    # def get_serialized_status_ok_response(self, _queryset, _many=True, _status=status.HTTP_200_OK):
    #    serializer = self.get_serializer(_queryset, many=_many)
    #    return Response(data=serializer.data, status=_status)

    def get_queryset(self, *args, **kwargs):
        return super().get_queryset().prefetch_related('keywords').select_related('owned_by_org', 'service_type')


class LayerViewSet(ModelViewSetWithPermissionChecker):
    queryset = Layer.objects.all()
    filterset_class = LayerApiFilter
    filter_backends = [api_filters.DjangoFilterBackend, OrderingFilter]
    ordering_fields = ['title', 'abstract', 'id']
    pagination_class = StandardResultsSetPagination
    # permission_classes = [DjangoObjectPermissions]

    serializers = {
        'default': LayerSerializer
    }

    def get_serializer_class(self):
        return self.serializers.get(self.action, self.serializers['default'])

    # TODO: add to mixin (not needed for now. Will come in handy when we need to start overwriting methods)
    # def get_serialized_status_ok_response(self, _queryset, _many=True, _status=status.HTTP_200_OK):
    #    serializer = self.get_serializer(_queryset, many=_many)
    #    return Response(data=serializer.data, status=_status)

    def get_queryset(self, *args, **kwargs):
        return super().get_queryset().prefetch_related('keywords').select_related('owned_by_org', 'service')


class FeatureTypeViewSet(ModelViewSetWithPermissionChecker):
    queryset = FeatureType.objects.all()
    filterset_class = FeatureTypeApiFilter
    filter_backends = [api_filters.DjangoFilterBackend, OrderingFilter]
    ordering_fields = ['title', 'abstract', 'id']
    pagination_class = StandardResultsSetPagination
    permission_classes = [DjangoObjectPermissions]

    serializers = {
        'default': FeatureTypeSerializer
    }

    def get_serializer_class(self):
        return self.serializers.get(self.action, self.serializers['default'])

    # TODO: add to mixin (not needed for now. Will come in handy when we need to start overwriting methods)
    # def get_serialized_status_ok_response(self, _queryset, _many=True, _status=status.HTTP_200_OK):
    #    serializer = self.get_serializer(_queryset, many=_many)
    #    return Response(data=serializer.data, status=_status)

    def get_queryset(self, *args, **kwargs):
        return super().get_queryset().prefetch_related('keywords').select_related('owned_by_org', 'service')
