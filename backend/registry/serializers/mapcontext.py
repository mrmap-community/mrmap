from django.core.exceptions import ValidationError
from registry.models import MapContext, MapContextLayer
from rest_framework.fields import (CharField, ChoiceField, IntegerField,
                                   ModelField)
from rest_framework.serializers import HyperlinkedIdentityField
from rest_framework_json_api.relations import HyperlinkedRelatedField
from rest_framework_json_api.serializers import ModelSerializer, Serializer


class MapContextLayerSerializer(ModelSerializer):

    url = HyperlinkedIdentityField(
        view_name='registry:mapcontextlayer-detail',
    )

    class Meta:
        model = MapContextLayer
        fields = "__all__"


class MapContextDefaultSerializer(ModelSerializer):

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

    class Meta:
        model = MapContext
        fields = "__all__"


class MapContextIncludeSerializer(ModelSerializer):

    url = HyperlinkedIdentityField(
        view_name='registry:mapcontext-detail',
    )
    included_serializers = {
        'map_context_layers': MapContextLayerSerializer,
    }

    class Meta:
        model = MapContext
        fields = "__all__"


class MapContextLayerMoveLayerSerializer(Serializer):

    target = IntegerField()
    position = ChoiceField(
        choices=['first-child', 'last-child', 'left', 'right'])

    class Meta:
        resource_name = 'MapContextLayer'

    def validate(self, attrs):
        validated_data = super().validate(attrs)

        try:
            validated_data['target'] = MapContextLayer.objects.get(
                pk=validated_data['target'])
        except MapContextLayer.DoesNotExist:
            raise ValidationError(
                'given target MapContextLayer does not exist.')

        return validated_data
