from rest_framework.reverse import reverse
from rest_framework.fields import SerializerMethodField
from rest_framework.serializers import ModelSerializer, CharField, HyperlinkedModelSerializer, HyperlinkedIdentityField

from registry.api.serializers.service import OperationsUrlSerializer
from registry.models import MapContext, MapContextLayer, OperationUrl, Layer


class MapContextPropertiesSerializer(ModelSerializer):
    class Meta:
        model = MapContext
        fields = ['title', 'abstract']


class MapContextLayerSerializer(ModelSerializer):
    # "http://localhost:8001/api/v1/registry/mapcontexts/1.json"
    # "http://localhost:8001/api/v1/registry/mapcontexts/1/layer/1"
    id = SerializerMethodField()
    type = CharField(default='Feature')
    context_layer_operations = SerializerMethodField()

    class Meta:
        model = MapContextLayer
        fields = [
            'id',
            'type',
            'parent',
            'name',
            # 'max_extent', # TODO
            'context_layer_operations'
        ]

    def get_id(self, obj):
        return self.context['request'].build_absolute_uri(
            reverse('api:mapcontext-detail', args=[obj.map_context_id]) + "layer/" + str(obj.id))

    @staticmethod
    def get_max_extent(obj):
        pass
        # TODO

    @staticmethod
    def get_context_layer_operations(obj):
        layer = obj.layer
        service = layer.service
        operations = OperationUrl.objects.filter(service__id=service.id)
        return OperationsUrlSerializer(operations, many=True).data


class MapContextSerializer(HyperlinkedModelSerializer):
    id = HyperlinkedIdentityField(view_name="api:mapcontext-detail")
    type = CharField(default='FeatureCollection')
    properties = SerializerMethodField()
    features = SerializerMethodField()

    class Meta:
        model = MapContext
        fields = [
            'id',
            'type',
            'properties',
            'features'
        ]

    @staticmethod
    def get_map_extent(obj):
        pass
        # TODO

    def get_properties(self, obj):
        # TODO use MapContextPropertiesSerializer
        props = {
            # Spec: Title for the Context document (String type, not empty), One (mandatory)
            'title': obj.title
        }
        if obj.abstract:
            # Spec: Description of the Context document purpose or content (String type, not empty)
            # Zero or one (optional)
            props['subtitle'] = obj.abstract
        return props

    def get_features(self, obj):
        queryset = MapContextLayer.objects.filter(map_context_id=obj.id)
        serializer = MapContextLayerSerializer(queryset, many=True, context=self.context)
        return serializer.data
