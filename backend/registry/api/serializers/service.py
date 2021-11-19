from registry.models.service import Layer, FeatureType, WebMapService, WebFeatureService, OperationUrl
from registry.models.metadata import Keyword
from rest_framework_json_api.serializers import ModelSerializer
from rest_framework_json_api.relations import ResourceRelatedField


class OperationsUrlSerializer(ModelSerializer):

    class Meta:
        model = OperationUrl
        fields = '__all__'


class LayerSerializer(ModelSerializer):

    class Meta:
        model = Layer
        fields = '__all__'


class FeatureTypeSerializer(ModelSerializer):

    class Meta:
        model = FeatureType
        fields = '__all__'


class KeywordSerializer(ModelSerializer):

    class Meta:
        model = Keyword
        fields = '__all__'


class WebMapServiceSerializer(ModelSerializer):

    included_serializers = {
        'layers': LayerSerializer,
    }

    layers = ResourceRelatedField(
        queryset=Layer.objects,
        many=True,  # necessary for M2M fields & reverse FK fields
        related_link_view_name='registry:wms-layers-list',
        related_link_url_kwarg='parent_lookup_wms',
        self_link_view_name='registry:wms-relationships',
    )

    class Meta:
        model = WebMapService
        fields = "__all__"

    class JSONAPIMeta:
        include_resources = ['layers']


class WebFeatureServiceSerializer(ModelSerializer):

    included_serializers = {
        'featuretypes': FeatureType,
    }

    featuretypes = ResourceRelatedField(
        queryset=FeatureType.objects,
        many=True,  # necessary for M2M fields & reverse FK fields
        related_link_view_name='registry:wfs-featuretypes-list',
        related_link_url_kwarg='parent_lookup_wfs',
        self_link_view_name='registry:wfs-relationships',
    )

    class Meta:
        model = WebFeatureService
        fields = "__all__"

    class JSONAPIMeta:
        include_resources = ['featuretypes']
