from django.core.exceptions import ValidationError
from django.http import HttpRequest
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from extras.serializers import (StringRepresentationSerializer,
                                SystemInfoSerializerMixin)
from registry.models import MapContext, MapContextLayer
from registry.serializers.service import LayerSerializer
from rest_framework.fields import CharField, IntegerField
from rest_framework_json_api.relations import ResourceRelatedField
from rest_framework_json_api.serializers import (HyperlinkedIdentityField,
                                                 ModelSerializer,
                                                 SerializerMethodField)


class MapContextLayerSerializer(
        StringRepresentationSerializer,
        SystemInfoSerializerMixin,
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
    mptt_tree_id = IntegerField(
        # queryset=Tree.objects,
        label=_("tree id"),
        # model=Tree,
        read_only=True
    )
    mptt_parent = ResourceRelatedField(
        queryset=MapContextLayer.objects,
        label=_("parent"),
        help_text=_("the parent of this node"),
        model=MapContextLayer,
    )
    mptt_lft = IntegerField(
        label=_('mptt left value'),
        read_only=True
    )
    mptt_rgt = IntegerField(
        label=_('mptt right value'),
        read_only=True
    )
    mptt_depth = IntegerField(
        label=_('mptt depth value'),
        read_only=True
    )

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
                # move/insert action detected
                parent = validated_data.get(
                    'mptt_parent', self.instance.mptt_parent)
                if not parent:
                    raise ValidationError(_('root node can not be moved'))
                else:
                    validated_data['mptt_parent'] = parent
                child_layers_count = parent.chilren.count()
                if position > child_layers_count or position < 0:
                    raise ValidationError(
                        {"position": _('position index out of range')})
        return validated_data

    def update(self, instance, validated_data):
        position = validated_data.pop('position', None)
        if isinstance(position, int):
            parent = validated_data['mptt_parent']
            child_layers = parent.chilren.all()
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

    def create(self, validated_data):
        position = validated_data.pop('position', None)
        node = MapContextLayer(**validated_data)
        parent = validated_data['mptt_parent']
        if isinstance(position, int):
            parent = validated_data['mptt_parent']
            child_layers = parent.chilren.all()
            child_layers_count = child_layers.count()
            if position == 0:
                # first child
                node.insert_at(parent, 'first-child')
            elif position == child_layers_count:
                # last child
                node.insert_at(parent, 'last-child')
            else:
                # new child somewhere between
                target = child_layers[position]
                node.insert_at(target, 'left')
        else:
            return node.insert_at(parent)

    def get_mptt_tree_id(self, instance):
        return instance.mptt_tree_id


class MapContextDefaultSerializer(
        StringRepresentationSerializer,
        SystemInfoSerializerMixin,
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
        SystemInfoSerializerMixin,
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
        fields = "__all__"
