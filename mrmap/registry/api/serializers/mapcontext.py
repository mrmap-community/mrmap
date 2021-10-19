from rest_framework.reverse import reverse
from rest_framework.fields import SerializerMethodField, ModelField
from rest_framework.serializers import ModelSerializer, CharField, HyperlinkedModelSerializer, HyperlinkedIdentityField

from registry.api.serializers.service import OperationsUrlSerializer
from registry.models import MapContext, MapContextLayer, OperationUrl, Layer


class MapContextPropertiesSerializer(ModelSerializer):
    lang = CharField(default='de')
    subtitle = ModelField(model_field=MapContext()._meta.get_field('abstract'))
    updated = ModelField(model_field=MapContext()._meta.get_field('last_modified_at'))
    authors = SerializerMethodField()
    publisher = SerializerMethodField()
    creator = CharField(default='MrMap')  # format is unclear, see 7.1.1 vs 7.1.1.9
    links = SerializerMethodField()

    class Meta:
        model = MapContext
        fields = [
            'lang',  # 7.1.1.2 language
            'title',  # 7.1.1.4 title
            'subtitle',  # 7.1.1.5 abstract
            'updated',  # 7.1.1.6 updateDate (TODO: get rid of fractional seconds)
            'authors',  # 7.1.1.7 author
            'publisher',  # 7.1.1.8 publisher
            'creator',  # 7.1.1.9 creator
            # TODO 'rights', # 7.1.1.10 rights
            # TODO 'categories', # 7.1.1.15 keyword
            'links',  # 7.1.1.1 specReference + TODO: 7.1.1.14 contextMetadata
        ]

    @staticmethod
    def get_authors(obj):
        if not obj.created_by_user:
            return
        name = obj.created_by_user.username
        if obj.created_by_user.last_name:
            name = obj.created_by_user.last_name
            if obj.created_by_user.first_name:
                name = obj.created_by_user.first_name + " " + name
        author = {
            'name': name
        }
        if obj.created_by_user.email:
            author['email'] = obj.created_by_user.email
        return {
            'authors': [author]
        }

    @staticmethod
    def get_publisher(obj):
        if not obj.owned_by_org:
            return
        return obj.owned_by_org.name

    @staticmethod
    def get_links(obj):
        # NOTE: The structure specified in 7.1.1.1 differs from the example in Annex B, but the example seems more
        # reasonable.
        return {
            'profiles': [{'href': 'http://www.opengis.net/spec/owc-geojson/1.0/req/core',
                          'title': 'This file is compliant with version 1.0 of OGC Context'}]
        }


class MapContextLayerSerializer(ModelSerializer):
    # "http://localhost:8001/api/v1/registry/mapcontexts/1.json"
    # "http://localhost:8001/api/v1/registry/mapcontexts/1/layer/1"
    id = SerializerMethodField()
    type = CharField(default='Feature')
    context_layer_operations = SerializerMethodField()

    class Meta:
        model = MapContextLayer
        fields = [
            'id',
            'type',
            'parent',
            'name',
            # 'max_extent', # TODO
            'context_layer_operations'
        ]

    def get_id(self, obj):
        return self.context['request'].build_absolute_uri(
            reverse('api:mapcontext-detail', args=[obj.map_context_id]) + "layer/" + str(obj.id))

    @staticmethod
    def get_max_extent(obj):
        pass
        # TODO

    @staticmethod
    def get_context_layer_operations(obj):
        layer = obj.layer
        service = layer.service
        operations = OperationUrl.objects.filter(service__id=service.id)
        return OperationsUrlSerializer(operations, many=True).data


class MapContextSerializer(HyperlinkedModelSerializer):
    type = CharField(default='FeatureCollection')
    id = HyperlinkedIdentityField(view_name="api:mapcontext-detail")
    properties = MapContextPropertiesSerializer(source='*')
    features = SerializerMethodField()

    class Meta:
        model = MapContext
        fields = [
            'type',
            'id',  # 7.1.1.3 id
            'properties',
            # TODO 'bbox',  # 7.1.1.11 areaOfInterest
            # TODO 'date',  # 7.1.1.12 timeIntervalOfInterest
            'features'  # 7.1.1.13 resource
        ]

    def get_features(self, obj):
        queryset = MapContextLayer.objects.filter(map_context_id=obj.id)
        serializer = MapContextLayerSerializer(queryset, many=True, context=self.context)
        return serializer.data
