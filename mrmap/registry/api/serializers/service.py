from rest_framework.serializers import ModelSerializer

from registry.models import OperationUrl, Service, ServiceType, Keyword, Layer, FeatureType


class LayerSerializer(ModelSerializer):

    class Meta:
        model = Layer
        fields = '__all__'


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


class OperationsUrlSerializer(ModelSerializer):

    class Meta:
        model = OperationUrl
        fields = '__all__'
