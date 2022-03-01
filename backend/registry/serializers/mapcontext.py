from django.core.exceptions import ValidationError
from django.http import HttpRequest
from django.utils.translation import gettext_lazy as _
from extras.serializers import StringRepresentationSerializer
from registry.models import MapContext, MapContextLayer
from registry.serializers.service import LayerSerializer
from rest_framework.fields import CharField, IntegerField
from rest_framework_json_api.relations import ResourceRelatedField
from rest_framework_json_api.serializers import (HyperlinkedIdentityField,
                                                 ModelSerializer)


class MapContextLayerSerializer(
        StringRepresentationSerializer,
        ModelSerializer):

    title = CharField(
        label=_('title'),
        help_text=_('an identifying name for this map context layer'),
        required=True
    )
    # description = CharField(
    #     label=_("description"),
    #     help_text=_("a short description for this map context layer")
    # )
    url = HyperlinkedIdentityField(
        view_name='registry:mapcontextlayer-detail',
    )

    # https://django-mptt.readthedocs.io/en/latest/models.html?highlight=insert_node#insert-node-node-target-position-last-child-save-false
    position = IntegerField(
        label=_('position'),
        help_text=_(
            'the tree position of the node where it should be moved to'),
        required=False,
        write_only=True)

    included_serializers = {
        'rendering_layer': LayerSerializer
    }

    class Meta:
        model = MapContextLayer
        fields = "__all__"

    def validate(self, attrs):
        validated_data = super().validate(attrs)
        request: HttpRequest = self.context.get('request', None)
        if request and request.method.lower() == 'patch':
            position = validated_data.get('position', None)
            if isinstance(position, int):
                # move action detected
                parent = validated_data.get('parent', self.instance.parent)
                if not parent:
                    raise ValidationError(_('root node can not be moved'))
                else:
                    validated_data['parent'] = parent
                child_layers_count = parent.child_layers.count()
                if position > child_layers_count or position < 0:
                    raise ValidationError(
                        {"position": _('position index out of range')})
        return validated_data

    def update(self, instance, validated_data):
        position = validated_data.pop('position', None)
        if isinstance(position, int):
            parent = validated_data['parent']
            child_layers = parent.child_layers.all()
            child_layers_count = child_layers.count()
            if position == 0:
                # first child
                instance.move_to(
                    target=parent,
                    position='first-child')
            elif position == child_layers_count:
                # last child
                instance.move_to(
                    target=parent,
                    position='last-child')
            else:
                # new child somewhere between
                target = child_layers[position]
                if target != instance:
                    instance.move_to(
                        target=target,
                        position='left')
        return super().update(instance, validated_data)


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
