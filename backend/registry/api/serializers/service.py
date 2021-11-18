from rest_framework.serializers import ModelSerializer
from extras.api.serializers import LinksSerializerMixin, ObjectAccessSerializer
from registry.models.service import Layer, FeatureType, Service, OperationUrl, ServiceType
from registry.models.metadata import Keyword
from rest_framework_json_api.relations import ResourceRelatedField


class OperationsUrlSerializer(ModelSerializer):

    class Meta:
        model = OperationUrl
        fields = '__all__'


class LayerSerializer(ObjectAccessSerializer):

    class Meta:
        model = Layer
        fields = '__all__'


class FeatureTypeSerializer(ObjectAccessSerializer):

    class Meta:
        model = FeatureType
        fields = '__all__'


class KeywordSerializer(ModelSerializer):

    class Meta:
        model = Keyword
        fields = '__all__'


class ServiceTypeSerializer(ModelSerializer):

    class Meta:
        model = ServiceType
        fields = ['name']


class ServiceSerializer(LinksSerializerMixin, ObjectAccessSerializer):

    class Meta:
        model = Service
        fields = "__all__"

    layers = ResourceRelatedField(
        queryset=Layer.objects,
        many=True,  # necessary for M2M fields & reverse FK fields
        related_link_view_name='registry:service-layers-list',
        related_link_url_kwarg='parent_lookup_service',
        self_link_view_name='registry:service-relationships',
    )

    featuretypes = ResourceRelatedField(
        queryset=FeatureType.objects,
        many=True,  # necessary for M2M fields & reverse FK fields
        related_link_view_name='registry:service-featuretypes-list',
        related_link_url_kwarg='parent_lookup_service',
        self_link_view_name='registry:service-relationships',
    )
