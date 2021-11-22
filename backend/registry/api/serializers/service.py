from registry.models.service import OgcService, Layer, FeatureType, WebMapService, WebFeatureService, OperationUrl
from rest_framework_json_api.serializers import ModelSerializer, PolymorphicModelSerializer
from rest_framework_json_api.relations import ResourceRelatedField, HyperlinkedRelatedField


class OperationsUrlSerializer(ModelSerializer):

    class Meta:
        model = OperationUrl
        fields = '__all__'


class LayerSerializer(ModelSerializer):

    class Meta:
        model = Layer
        fields = '__all__'


class WebMapServiceSerializer(ModelSerializer):

    included_serializers = {
        'layers': LayerSerializer,
    }

    layers = HyperlinkedRelatedField(
        queryset=Layer.objects,
        many=True,  # necessary for M2M fields & reverse FK fields
        related_link_view_name='registry:wms-layers-list',
        related_link_url_kwarg='parent_lookup_service',
        self_link_view_name='registry:wms-relationships',
    )

    class Meta:
        model = WebMapService
        fields = "__all__"

    class JSONAPIMeta:
        include_resources = ['layers']


class FeatureTypeSerializer(ModelSerializer):

    class Meta:
        model = FeatureType
        fields = '__all__'


class WebFeatureServiceSerializer(ModelSerializer):

    included_serializers = {
        'featuretypes': FeatureTypeSerializer,
    }

    featuretypes = ResourceRelatedField(
        queryset=FeatureType.objects,
        many=True,  # necessary for M2M fields & reverse FK fields
        related_link_view_name='registry:wfs-featuretypes-list',
        related_link_url_kwarg='parent_lookup_service',
        self_link_view_name='registry:wfs-relationships',
    )

    class Meta:
        model = WebFeatureService
        fields = "__all__"

    class JSONAPIMeta:
        include_resources = ['featuretypes']


class OgcServiceSerializer(PolymorphicModelSerializer):
    polymorphic_serializers = [WebMapServiceSerializer, WebFeatureServiceSerializer]

    class Meta:
        model = OgcService
        fields = "__all__"


class OgcServiceCreateSerializer(ModelSerializer):

    # TODO: implement included serializer for ServiceAuthentication
    # included_serializers = {
    #     'auth': ServiceAuthentication,
    # }

    class Meta:
        model = OgcService
        fields = ("get_capabilities_url", "owned_by_org")
