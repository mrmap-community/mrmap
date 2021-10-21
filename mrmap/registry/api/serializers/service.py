from rest_framework.serializers import ModelSerializer

from registry.models.service import Layer, FeatureType, Service, OperationUrl, ServiceType
from registry.models.metadata import Keyword


class OperationsUrlSerializer(ModelSerializer):

    class Meta:
        model = OperationUrl
        fields = '__all__'


class LayerSerializer(ModelSerializer):

    class Meta:
        model = Layer
        fields = ['id', 'scale_min', 'scale_max', 'inherit_scale_min', 'inherit_scale_max']


class FeatureTypeSerializer(ModelSerializer):

    class Meta:
        model = Layer
        fields = '__all__'


class KeywordSerializer(ModelSerializer):

    class Meta:
        model = Keyword
        fields = '__all__'


class ServiceTypeSerializer(ModelSerializer):

    class Meta:
        model = ServiceType
        fields = ['name']


class ServiceSerializer(ModelSerializer):
    type = ServiceTypeSerializer(source='service_type')

    class Meta:
        model = Service
        fields = [
            'id',
            'title',
            'abstract',
            'created_at',
            'type',
            'keywords'
        ]

    @staticmethod
    def get_layer(obj):
        queryset = Layer.objects.filter(service__id=obj.id)
        return LayerSerializer(queryset, many=True).data

    @staticmethod
    def get_feature_type(obj):
        queryset = FeatureType.objects.filter(service__id=obj.id)
        return FeatureTypeSerializer(queryset, many=True).data
