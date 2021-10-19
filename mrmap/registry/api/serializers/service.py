from rest_framework.fields import SerializerMethodField
from rest_framework.relations import PrimaryKeyRelatedField
from rest_framework.serializers import ModelSerializer

from registry.models import OperationUrl, Service, ServiceType, Keyword, ServiceElement, Layer, FeatureType


class LayerSerializer(ModelSerializer):

    class Meta:
        model = Layer
        fields = ['id', 'service']


class FeatureTypeSerializer(ModelSerializer):

    class Meta:
        model = Layer
        fields = ['id', 'service']


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
    # layer = SerializerMethodField()
    # feature_type = SerializerMethodField()

    class Meta:
        model = Service
        fields = [
            'id',
            'title',
            'abstract',
            'created_at',
            'type',
            # 'layer',
            # 'feature_type',
            'keywords'
        ]
        depth = 2
        # Service ---> FK ServiceType
        # OperationsUrl ---> FK service
        # ServiceElement ---> FK service

    def get_layer(self, obj):
        queryset = Layer.objects.filter(service__id=obj.id)
        return LayerSerializer(queryset, many=True).data

    def get_feature_type(self, obj):
        queryset = FeatureType.objects.filter(service__id=obj.id)
        return FeatureTypeSerializer(queryset, many=True).data

class OperationsUrlSerializer(ModelSerializer):

    class Meta:
        model = OperationUrl
        fields = '__all__'
