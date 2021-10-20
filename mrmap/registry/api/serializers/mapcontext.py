from collections import OrderedDict

from rest_framework.reverse import reverse
from rest_framework.fields import SerializerMethodField, ModelField
from rest_framework.serializers import ModelSerializer, CharField, HyperlinkedModelSerializer, HyperlinkedIdentityField

from extras.api.serializers import NonNullModelSerializer
from registry.models import MapContext, MapContextLayer


class MapContextLayerPropertiesSerializer(NonNullModelSerializer):
    title = ModelField(model_field=MapContextLayer()._meta.get_field('name'))
    abstract = ModelField(model_field=MapContextLayer()._meta.get_field('title'))
    offerings = SerializerMethodField()
    folder = SerializerMethodField()

    class Meta:
        model = MapContextLayer
        fields = [
            'title',  # 7.1.2.2 title
            'abstract',  # 7.1.2.3 abstract
            # TODO 'updated' # 7.1.2.4 updateDate
            # TODO 'authors' # 7.1.2.5 author
            # TODO 'publisher' # 7.1.2.6 publisher
            # TODO 'rights' # 7.1.2.7 rights
            # TODO 'date' # 7.1.2.9 temporalExtent
            # TODO 'links' # 7.1.2.10 preview + 7.1.2.11 contentDescription + 7.1.2.12 contentByRef + 7.1.2.15 resourceMetadata
            'offerings',  # 7.1.2.13 offering
            # TODO 'active' # 7.1.2.14 active
            # TODO 'categories' # 7.1.2.16 keyword
            # TODO 'minScaleDenominator' # 7.1.2.17 minScaleDenominator
            # TODO 'maxScaleDenominator' # 7.1.2.18 maxScaleDenominator
            'folder',  # 7.1.2.19 folder
            # TODO '*', # 7.1.2.20 extension
        ]

    @staticmethod
    def __get_wms_offering(wms_layer):
        return {
            'code': 'http://www.opengis.net/spec/owc-geojson/1.0/req/wms',
            'operations': [{
                "code": "GetCapabilities",
                "method": "GET",
                "type": "application/xml",
                "href": f"{wms_layer.service.url}service=WMS&request=GetCapabilities"
            }, {
                "code": "GetMap",
                "method": "GET",
                "type": "image/jpeg",  # TODO
                "href": f"{wms_layer.service.url}service=WMS&version=1.3.0&request=GetMap&layer={wms_layer.identifier}"
                # TODO full request url
            }]
        }

    @staticmethod
    def get_offerings(obj):
        offerings = [MapContextLayerPropertiesSerializer.__get_wms_offering(obj.layer)]
        return offerings

    @staticmethod
    def get_folder(obj):
        folder = None
        while obj.parent and obj.parent.name != "/":
            obj = obj.parent
            if folder:
                folder = obj.name + "/" + folder
            else:
                folder = obj.name
        return folder


class MapContextLayerSerializer(ModelSerializer):
    type = CharField(default='Feature')
    id = SerializerMethodField()
    properties = MapContextLayerPropertiesSerializer(source='*')

    class Meta:
        model = MapContextLayer
        fields = [
            'type',
            'id',  # 7.1.2.1 id
            'properties',
            # TODO 'geometry'  # 7.1.2.8 geospatialExtent
        ]

    def get_id(self, obj):
        return self.context['request'].build_absolute_uri(
            reverse('api:mapcontext-detail', args=[obj.map_context_id]) + "layer/" + str(obj.id) + "/")


class MapContextPropertiesSerializer(ModelSerializer):
    lang = CharField(default='de')
    subtitle = ModelField(model_field=MapContext()._meta.get_field('abstract'))
    updated = ModelField(model_field=MapContext()._meta.get_field('last_modified_at'))
    authors = SerializerMethodField()
    publisher = SerializerMethodField()
    generator = SerializerMethodField()
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
            'generator',  # 7.1.1.9 creator / 7.1.7.1 creatorApplication
            # TODO 'display',  # 7.1.9 DataType OWC:Creator/OWC:CreatorDisplay
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
        return [author]

    @staticmethod
    def get_publisher(obj):
        if not obj.owned_by_org:
            return
        return obj.owned_by_org.name

    @staticmethod
    def get_generator(obj):
        return {
            'title': 'MrMap',
            'uri': 'https://mrmap-community.github.io/mrmap/develop/',  # TODO actual link
            'version': '1.0'  # TODO actual version
        }

    @staticmethod
    def get_links(obj):
        # NOTE: The structure specified in 7.1.1.1 differs from the example in Annex B, but the example seems more
        # reasonable.
        return {
            'profiles': [{'href': 'http://www.opengis.net/spec/owc-geojson/1.0/req/core',
                          'title': 'This file is compliant with version 1.0 of OGC Context'}]
        }


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
            # TODO '*',  # 7.1.1.16 extension
        ]

    def get_features(self, obj):
        queryset = MapContextLayer.objects.filter(map_context_id=obj.id).filter(layer__isnull=False)
        serializer = MapContextLayerSerializer(queryset, many=True, context=self.context)
        return serializer.data
