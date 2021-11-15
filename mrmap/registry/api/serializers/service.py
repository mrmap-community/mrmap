from django.core.exceptions import ObjectDoesNotExist
from rest_framework.reverse import reverse
from rest_framework.serializers import ModelSerializer, HyperlinkedRelatedField
from rest_framework.fields import SerializerMethodField
from extras.api.serializers import ObjectAccessSerializer
from registry.models.service import Layer, FeatureType, Service, OperationUrl, ServiceType
from registry.models.metadata import Keyword
from registry.enums.service import OGCServiceEnum


class OperationsUrlSerializer(ModelSerializer):

    class Meta:
        model = OperationUrl
        fields = '__all__'


class LayerSerializer(ObjectAccessSerializer):
    # TODO: extreme slow lookup... Present a link to the dataset_metadata entpoint filtered by the given layer
    # dataset_metadata = HyperlinkedRelatedField(
    #     many=True,
    #     read_only=True,
    #     view_name='api:dataset_metadata-detail'
    # )
    service = HyperlinkedRelatedField(
        read_only=True,
        view_name='api:service-detail'
    )

    class Meta:
        model = Layer
        fields = [
            'id',
            'service',
            'scale_min',
            'scale_max',
            # TODO: this is causing too much queries to be made. Find out exactly why
            # 'inherit_scale_min',
            # 'inherit_scale_max',

            # TODO: extreme slow lookup... dont do this
            # 'dataset_metadata'
        ]


class FeatureTypeSerializer(ObjectAccessSerializer):
    # FIXME: extreme slow lookup... Present a link to the dataset_metadata entpoint filtered by the given ft
    # dataset_metadata = HyperlinkedRelatedField(
    #     many=True,
    #     read_only=True,
    #     view_name='api:dataset_metadata-detail'
    # )

    class Meta:
        model = Layer
        fields = [
            'id',
            'scale_min',
            'scale_max',
            # TODO: this is causing too much queries to be made. Find out exactly why
            # 'inherit_scale_min',
            # 'inherit_scale_max',
            # TODO: extreme slow lookup... dont do this
            # 'dataset_metadata'
        ]


class KeywordSerializer(ModelSerializer):

    class Meta:
        model = Keyword
        fields = '__all__'


class ServiceTypeSerializer(ModelSerializer):

    class Meta:
        model = ServiceType
        fields = ['name']


class ServiceSerializer(ObjectAccessSerializer):
    type = ServiceTypeSerializer(source='service_type')
    layers = SerializerMethodField()
    
    feature_types = SerializerMethodField()
    keywords = SerializerMethodField()

    class Meta:
        model = Service
        fields = [
            'id',
            'title',
            'abstract',
            'created_at',
            'type',
            'keywords',
            'layers',
            'feature_types',
        ]

    def get_layers(self, obj):
        return self.context['request'].build_absolute_uri(f"{reverse('api:layer-list')}?service__id={obj.pk}")

    def get_feature_types(self, obj):
        queryset = FeatureType.objects.none()

        if obj.is_service_type(OGCServiceEnum.WFS):
            queryset = obj.featuretypes.all().prefetch_related('keywords')
        return FeatureTypeSerializer(queryset, many=True, context=self.context).data

    @staticmethod
    def get_keywords(obj):
        try:
            keywords = obj.keywords
        except ObjectDoesNotExist:
            keywords = None
        if keywords:
            return KeywordSerializer(keywords, many=True).data
        return None
