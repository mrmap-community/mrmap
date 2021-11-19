from registry.api.serializers.service import WebMapServiceSerializer, WebFeatureServiceSerializer, FeatureTypeSerializer, LayerSerializer
from registry.models import WebMapService, Layer, WebFeatureService, FeatureType
from rest_framework_extensions.mixins import NestedViewSetMixin
from rest_framework_json_api.views import RelationshipView, ModelViewSet


class WebMapServiceRelationshipView(RelationshipView):
    queryset = WebMapService.objects


class WebMapServiceViewSet(NestedViewSetMixin, ModelViewSet):
    queryset = WebMapService.objects.all()
    serializer_class = WebMapServiceSerializer
    prefetch_for_includes = {
        '__all__': [],
        'layers': ['layers']
    }


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


class WebFeatureServiceRelationshipView(RelationshipView):
    queryset = WebFeatureService.objects


class WebFeatureServiceViewSet(NestedViewSetMixin, ModelViewSet):
    queryset = WebFeatureService.objects.all()
    serializer_class = WebFeatureServiceSerializer
    prefetch_for_includes = {
        '__all__': [],
        'featuretypes': ['featuretypes']
    }


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
