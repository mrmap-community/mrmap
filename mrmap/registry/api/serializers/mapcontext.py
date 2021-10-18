from rest_framework.fields import SerializerMethodField
from rest_framework.serializers import ModelSerializer, CharField

from registry.api.serializers.service import OperationsUrlSerializer
from registry.models import MapContext, MapContextLayer, OperationUrl


class MapContextPropertiesSerializer(ModelSerializer):

    class Meta:
        model = MapContext
        fields = '__all__'


class MapContextLayerSerializer(ModelSerializer):
    context_layer_operations = SerializerMethodField()

    class Meta:
        model = MapContextLayer
        fields = [
            'id',
            'parent',
            'title',
            # 'max_extent', # TODO
            'context_layer_operations'
        ]

    @staticmethod
    def get_max_extent(obj):
        pass
        # TODO

    @staticmethod
    def get_context_layer_operations(obj):
        map_context_layer = MapContextLayer.objects.filter(map_context_id=obj.id)
        layer = map_context_layer.get().layer
        service = layer.service
        operations = OperationUrl.objects.filter(service__id=service.id)
        return OperationsUrlSerializer(operations, many=True).data


class MapContextSerializer(ModelSerializer):
    type = CharField(default='FeatureCollection')
    id = SerializerMethodField()
    # properties = MapContextPropertiesSerializer()
    map_context_layers = MapContextPropertiesSerializer()

    class Meta:
        model = MapContext
        fields = [
            'type',
            'id',
            # 'properties',
            'mSap_context_layers'
        ]

    @staticmethod
    def get_id(obj):
        return obj.get_absolute_url()

    @staticmethod
    def get_map_extent(obj):
        pass
        # TODO

    @staticmethod
    def get_map_context_layers(obj):
        queryset = MapContextLayer.objects.filter(map_context_id=obj.id)
        return MapContextLayerSerializer(queryset, many=True).data
