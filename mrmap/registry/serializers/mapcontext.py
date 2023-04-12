from django.core.exceptions import ValidationError
from django.http import HttpRequest
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from extras.serializers import StringRepresentationSerializer
from registry.models import MapContext, MapContextLayer
from registry.serializers.service import LayerSerializer
from rest_framework.fields import CharField, ChoiceField
from rest_framework_json_api.relations import ResourceRelatedField
from rest_framework_json_api.serializers import (HyperlinkedIdentityField,
                                                 ModelSerializer,
                                                 SerializerMethodField)

POSITION_CHOICES = (
    ("first-sibling", _("the new node will be the new leftmost sibling")),
    ("left", _("the new node will take the node’s place, which will be moved to the right 1 position")),
    ("right", _("the new node will be inserted at the right of the node")),
    ("last-sibling", _("the new node will be the new rightmost sibling")),
    ("sorted-sibling", _("the new node will be at the right position according to the value of node_order_by")),
)


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

    # https://django-treebeard.readthedocs.io/en/latest/api.html#treebeard.models.Node.add_sibling
    pos = ChoiceField(
        choices=POSITION_CHOICES,
        label=_('position'),
        help_text=_(
            'The position, relative to the current node object, where the new node will be inserted'),
        required=False,
        write_only=True)

    included_serializers = {
        'rendering_layer': LayerSerializer
    }

    class Meta:
        model = MapContextLayer
        fields = "__all__"
        read_only_fields = ("lft", "rgt", "tree_id", "depth")

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

    def create(self, validated_data):
        parent = validated_data['parent']

        return super().create(validated_data)

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
    ogc_mapcontext_url = SerializerMethodField(
        read_only=True,
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

    def get_ogc_mapcontext_url(self, instance):
        return reverse('ows-context-detail', args=[instance.pk])


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
