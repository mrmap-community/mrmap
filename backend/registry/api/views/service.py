from django_filters import rest_framework as api_filters
from rest_framework.filters import OrderingFilter
from rest_framework.permissions import DjangoObjectPermissions

from extras.api import viewsets
from extras.api.pagination import StandardResultsSetPagination
from extras.api.viewsets import ModelViewSetWithPermissionChecker
from registry.api.filters.service import ServiceApiFilter, FeatureTypeApiFilter, LayerApiFilter
from registry.api.serializers.service import ServiceSerializer, FeatureTypeSerializer, LayerSerializer
from registry.models import Service, Layer, FeatureType
from rest_framework_extensions.mixins import NestedViewSetMixin
from rest_framework_json_api.views import RelationshipView


class ServiceRelationshipView(RelationshipView):
    queryset = Service.objects


class ServiceViewSet(NestedViewSetMixin, viewsets.ModelViewSet):
    queryset = Service.objects.all()
    serializer_class = ServiceSerializer
    #filterset_class = ServiceApiFilter
    #filter_backends = [api_filters.DjangoFilterBackend, OrderingFilter]
    #ordering_fields = ['title', 'abstract', 'id']
    #pagination_class = StandardResultsSetPagination
    # permission_classes = [DjangoObjectPermissions]

    # serializers = {
    #     'default': ServiceSerializer
    # }

    # def get_serializer_class(self):
    #     return self.serializers.get(self.action, self.serializers['default'])

    # TODO: add to mixin (not needed for now. Will come in handy when we need to start overwriting methods)
    # def get_serialized_status_ok_response(self, _queryset, _many=True, _status=status.HTTP_200_OK):
    #    serializer = self.get_serializer(_queryset, many=_many)
    #    return Response(data=serializer.data, status=_status)

    # def get_queryset(self, *args, **kwargs):
        # return super().get_queryset().prefetch_related('keywords').select_related('owned_by_org', 'service_type')


class LayerViewSet(NestedViewSetMixin, viewsets.ModelViewSet):
    queryset = Layer.objects.all()
    serializer_class = LayerSerializer

    def get_queryset(self):
        queryset = super(LayerViewSet, self).get_queryset()

        # if this viewset is accessed via the 'service-layers-list' route,
        # it wll have been passed the `service_pk` kwarg and the queryset
        # needs to be filtered accordingly; if it was accessed via the
        # unnested '/services' route, the queryset should include all layers
        if 'service_pk' in self.kwargs:
            service_pk = self.kwargs['service_pk']
            queryset = queryset.filter(service__pk=service_pk)

        return queryset


    #filterset_class = LayerApiFilter
    #filter_backends = [api_filters.DjangoFilterBackend, OrderingFilter]
    #ordering_fields = ['title', 'abstract', 'id']
    #pagination_class = StandardResultsSetPagination
    # permission_classes = [DjangoObjectPermissions]

    # serializers = {
    #     'default': LayerSerializer
    # }

    # def get_serializer_class(self):
    #     return self.serializers.get(self.action, self.serializers['default'])

    # def get_queryset(self, *args, **kwargs):
    #     return super().get_queryset().prefetch_related('keywords').select_related('owned_by_org', 'service')


class FeatureTypeViewSet(NestedViewSetMixin, ModelViewSetWithPermissionChecker):
    queryset = FeatureType.objects.all()
    serializer_class = FeatureTypeSerializer
    # filterset_class = FeatureTypeApiFilter
    # filter_backends = [api_filters.DjangoFilterBackend, OrderingFilter]
    # ordering_fields = ['title', 'abstract', 'id']
    # pagination_class = StandardResultsSetPagination
    # permission_classes = [DjangoObjectPermissions]

    # serializers = {
    #     'default': FeatureTypeSerializer
    # }

    # def get_serializer_class(self):
    #     return self.serializers.get(self.action, self.serializers['default'])

    # # TODO: add to mixin (not needed for now. Will come in handy when we need to start overwriting methods)
    # # def get_serialized_status_ok_response(self, _queryset, _many=True, _status=status.HTTP_200_OK):
    # #    serializer = self.get_serializer(_queryset, many=_many)
    # #    return Response(data=serializer.data, status=_status)

    # def get_queryset(self, *args, **kwargs):
    #     return super().get_queryset().prefetch_related('keywords').select_related('owned_by_org', 'service')
