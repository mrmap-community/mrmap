from django.core.exceptions import ValidationError
from extras.serializers import StringRepresentationSerializer
from registry.models import MapContext, MapContextLayer
from rest_framework.fields import ChoiceField, IntegerField
from rest_framework.serializers import HyperlinkedIdentityField
from rest_framework_json_api.relations import ResourceRelatedField
from rest_framework_json_api.serializers import ModelSerializer, Serializer


class MapContextLayerSerializer(
        StringRepresentationSerializer,
        ModelSerializer):

    url = HyperlinkedIdentityField(
        view_name='registry:mapcontextlayer-detail',
    )

    class Meta:
        model = MapContextLayer
        fields = "__all__"
        meta_fields = ("string_representation",)

    def validate(self, attrs):
        validated_data = super().validate(attrs)
        # FIXME: check if the requesting user has permissions to change the parent. If not raise PermissionDenied
        return validated_data


class MapContextDefaultSerializer(
        StringRepresentationSerializer,
        ModelSerializer):

    url = HyperlinkedIdentityField(
        view_name='registry:mapcontext-detail',
    )
    map_context_layers = ResourceRelatedField(
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
        meta_fields = ("string_representation",)

    def create(self, validated_data):
        instance = super().create(validated_data)
        # to set the map_context_layer_count attribute on a frech object, so that the map_context_layers field will not raise an AttributeError
        instance.map_context_layer_count = 0
        return instance


class MapContextIncludeSerializer(
        StringRepresentationSerializer,
        ModelSerializer):

    url = HyperlinkedIdentityField(
        view_name='registry:mapcontext-detail',
    )

    map_context_layers = ResourceRelatedField(
        queryset=MapContextLayer.objects,
        many=True,  # necessary for M2M fields & reverse FK fields
        related_link_view_name='registry:mapcontext-mapcontextlayers-list',
        related_link_url_kwarg='parent_lookup_map_context',
        self_link_view_name='registry:mapcontextlayer-relationships'
    )

    included_serializers = {
        'map_context_layers': MapContextLayerSerializer,
    }

    class Meta:
        model = MapContext
        fields = "__all__"
        meta_fields = ("string_representation",)


class MapContextLayerMoveLayerSerializer(
        Serializer):

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
