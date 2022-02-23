from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from extras.serializers import StringRepresentationSerializer
from registry.models import MapContext, MapContextLayer
from registry.serializers.service import LayerSerializer
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

    included_serializers = {
        'rendering_layer': LayerSerializer
    }

    class Meta:
        model = MapContextLayer
        fields = "__all__"


class MapContextLayerPostOrPatchSerializer(
        MapContextLayerSerializer):

    target = IntegerField(
        label=_('target id'),
        help_text=_('pass the id of the target node')
    )
    # https://django-mptt.readthedocs.io/en/latest/models.html?highlight=insert_node#insert-node-node-target-position-last-child-save-false
    position = ChoiceField(
        label=_('position'),
        help_text=_(
            'the tree position of the node where it should be moved to'),
        choices=['first-child', 'last-child', 'left', 'right'])

    def validate(self, attrs):
        validated_data = super().validate(attrs)
        if ('target' in validated_data and 'position' not in validated_data) or ('target' not in validated_data and 'position' in validated_data):
            raise ValidationError(
                _('if you want to use move to or insert at action, you need to pass target AND position.'))
        elif 'target' in validated_data and 'position' in validated_data:
            if 'parent' in validated_data:
                raise ValidationError(
                    _('set parent on move or insert action is not allowed'))
            try:
                validated_data['target'] = MapContextLayer.objects.get(
                    pk=validated_data['target'])
            except MapContextLayer.DoesNotExist:
                raise ValidationError(
                    'given target MapContextLayer does not exist.')

        return validated_data

    def create(self, validated_data):
        target = validated_data.pop('target')
        position = validated_data.pop('position')
        obj = super().create(validated_data=validated_data)
        if target and position:
            obj.move_to(
                target=target,
                position=position)
        return obj

    def update(self, instance, validated_data):
        target = validated_data.pop('target')
        position = validated_data.pop('position')
        if target and position:
            instance.move_to(
                target=target,
                position=position)
        return super().update(instance, validated_data)


class MapContextLayerInsertSerializer(
        MapContextLayerSerializer):

    position = ChoiceField(
        choices=['first-child', 'last-child', 'left', 'right'])


class MapContextLayerMoveLayerSerializer(
        Serializer):

    target = IntegerField()
    position = ChoiceField(
        choices=['first-child', 'last-child', 'left', 'right'])

    class Meta:
        # TODO: maybe this should be an other resource_name to differ from default crud used MapContextLayer resource
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
        required=False,
    )

    class Meta:
        model = MapContext
        fields = "__all__"

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
    )

    included_serializers = {
        'map_context_layers': MapContextLayerSerializer,
    }

    class Meta:
        model = MapContext
        fields = "__all__"
