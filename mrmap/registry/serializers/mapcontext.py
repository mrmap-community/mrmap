from django.core.exceptions import ValidationError
from django.http import HttpRequest
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from extras.serializers import StringRepresentationSerializer
from registry.models import MapContext, MapContextLayer
from registry.serializers.service import LayerSerializer
from rest_framework.fields import CharField, IntegerField
from rest_framework_json_api.relations import ResourceRelatedField
from rest_framework_json_api.serializers import (HyperlinkedIdentityField,
                                                 ModelSerializer,
                                                 SerializerMethodField)
from treebeard.ns_tree import NS_Node as NestedSetNode


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
    # https://django-treebeard.readthedocs.io/en/latest/api.html#treebeard.models.Node.move
    position = IntegerField(
        label=_('position'),
        help_text=_(
            'the tree position of the node where it should be moved to'),
        required=False,
        write_only=True)

    parent = ResourceRelatedField(
        queryset=MapContextLayer.objects,
        # related_link_view_name='registry:mapcontext-mapcontextlayers-list',
        # related_link_url_kwarg='parent_lookup_map_context',
        required=False,
    )

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
        parent: NestedSetNode = validated_data.pop("parent", None)
        if parent:
            children_count = parent.get_children_count()
            position = validated_data.pop("position", children_count)

            if position == 0:
                related_sibling: NestedSetNode = parent.get_children()[:1]
                related_sibling.add_sibling(
                    pos="first-sibling", **validated_data)

            elif position == children_count:
                # The new node will be the new rightmost child.
                parent.add_child(**validated_data)
            else:
                # new child somewhere between
                related_sibling: NestedSetNode = parent.get_children()[
                    position]
                related_sibling.add_sibling(pos="right", **validated_data)
        else:
            # new root node of a new tree
            node_class: NestedSetNode = self._meta.model
            node_class.add_root(**validated_data)

        # return super().create(validated_data)

    def update(self, instance: NestedSetNode, validated_data):
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
                    instance.move(
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
