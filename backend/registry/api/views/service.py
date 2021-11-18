from registry.api.serializers.service import ServiceSerializer, FeatureTypeSerializer, LayerSerializer
from registry.models import Service, Layer, FeatureType
from rest_framework_extensions.mixins import NestedViewSetMixin
from rest_framework_json_api.views import RelationshipView, ModelViewSet


class ServiceRelationshipView(RelationshipView):
    queryset = Service.objects


class ServiceViewSet(NestedViewSetMixin, ModelViewSet):
    queryset = Service.objects.all()
    serializer_class = ServiceSerializer


class LayerViewSet(NestedViewSetMixin, ModelViewSet):
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


class FeatureTypeViewSet(NestedViewSetMixin, ModelViewSet):
    queryset = FeatureType.objects.all()
    serializer_class = FeatureTypeSerializer

    def get_queryset(self):
        queryset = super(FeatureTypeViewSet, self).get_queryset()

        # if this viewset is accessed via the 'service-layers-list' route,
        # it wll have been passed the `service_pk` kwarg and the queryset
        # needs to be filtered accordingly; if it was accessed via the
        # unnested '/services' route, the queryset should include all layers
        if 'service_pk' in self.kwargs:
            service_pk = self.kwargs['service_pk']
            queryset = queryset.filter(service__pk=service_pk)

        return queryset
