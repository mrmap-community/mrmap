from rest_framework.serializers import HyperlinkedIdentityField
from registry.models import MapContext, MapContextLayer
from rest_framework_json_api.serializers import ModelSerializer
from rest_framework_json_api.relations import HyperlinkedRelatedField


class MapContextLayerSerializer(ModelSerializer):

    url = HyperlinkedIdentityField(
        view_name='registry:mapcontextlayer-detail',
    )

    class Meta:
        model = MapContextLayer
        fields = "__all__"


class MapContextSerializer(ModelSerializer):

    url = HyperlinkedIdentityField(
        view_name='registry:mapcontext-detail',
    )

    map_context_layers = HyperlinkedRelatedField(
        queryset=MapContextLayer.objects,
        many=True,  # necessary for M2M fields & reverse FK fields
        related_link_view_name='registry:mapcontext-mapcontextlayers-list',
        related_link_url_kwarg='parent_lookup_map_context',
        self_link_view_name='registry:mapcontextlayer-relationships',
        required=False,
    )

    included_serializers = {
        'map_context_layers': MapContextLayerSerializer,
    }

    class Meta:
        model = MapContext
        fields = "__all__"
