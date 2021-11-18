from django.core.exceptions import ObjectDoesNotExist
from rest_framework.reverse import reverse
from rest_framework.serializers import ModelSerializer, HyperlinkedRelatedField
from rest_framework.fields import SerializerMethodField
from extras.api.serializers import LinksSerializerMixin, ObjectAccessSerializer
from registry.models.service import Layer, FeatureType, Service, OperationUrl, ServiceType
from registry.models.metadata import Keyword
from registry.enums.service import OGCServiceEnum
from rest_framework_json_api.relations import ResourceRelatedField


class OperationsUrlSerializer(ModelSerializer):

    class Meta:
        model = OperationUrl
        fields = '__all__'


class LayerSerializer(ObjectAccessSerializer):
    # TODO: extreme slow lookup... Present a link to the dataset_metadata entpoint filtered by the given layer
    # dataset_metadata = HyperlinkedRelatedField(
    #     many=True,
    #     read_only=True,
    #     view_name='api:dataset_metadata-detail'
    # )
    # service = HyperlinkedRelatedField(
    #     read_only=True,
    #     view_name='api:service-detail'
    # )

    class Meta:
        model = Layer
        fields = '__all__'


class FeatureTypeSerializer(ObjectAccessSerializer):
    # FIXME: extreme slow lookup... Present a link to the dataset_metadata entpoint filtered by the given ft
    # dataset_metadata = HyperlinkedRelatedField(
    #     many=True,
    #     read_only=True,
    #     view_name='api:dataset_metadata-detail'
    # )

    class Meta:
        model = FeatureType
        fields = '__all__'


class KeywordSerializer(ModelSerializer):

    class Meta:
        model = Keyword
        fields = '__all__'


class ServiceTypeSerializer(ModelSerializer):

    class Meta:
        model = ServiceType
        fields = ['name']


class ServiceSerializer(LinksSerializerMixin, ObjectAccessSerializer):
    #type = ServiceTypeSerializer(source='service_type')

    class Meta:
        model = Service
        fields = "__all__"

    layers = ResourceRelatedField(
        queryset=Layer.objects,
        many=True,  # necessary for M2M fields & reverse FK fields
        related_link_view_name='registry:service-layers-list',
        related_link_url_kwarg='parent_lookup_service',
        self_link_view_name='registry:service-relationships',
    )

    featuretypes = ResourceRelatedField(
        queryset=FeatureType.objects,
        many=True,  # necessary for M2M fields & reverse FK fields
        related_link_view_name='registry:service-featuretypes-list',
        related_link_url_kwarg='parent_lookup_service',
        self_link_view_name='registry:service-relationships',
    )


    # def get_links(self, obj):
    #     links = []
    #     from django.db.models.fields.related_descriptors import ReverseManyToOneDescriptor

    #     for field in self.links_fields:
    #         if isinstance(obj.__class__.layers, ReverseManyToOneDescriptor):
    #             query_param = f"{obj.__class__.layers.rel.remote_field.name}__{obj.__class__.layers.rel.field_name}"
    #             query = f"?{query_param}={getattr(obj, obj.__class__.layers.rel.field_name)}"
    #             reverse_name = f"api:{obj.__class__.layers.field.opts.model_name}-list"
    #             path = f"{reverse(reverse_name)}"
    #             absolute_uri = self.context['request'].build_absolute_uri(path) + query
    #             links.append({
    #                 "rel": "child",
    #                 "kind": "collection",
    #                 "name": "keywords",
    #                 "count": "TODO",
    #                 "href": absolute_uri

    #             })
    #     return links

    # def get_layers(self, obj):
    #     return self.context['request'].build_absolute_uri(f"{reverse('api:layer-list')}?service__id={obj.pk}")

    # def get_feature_types(self, obj) -> FeatureTypeSerializer:
    #     queryset = FeatureType.objects.none()

    #     if obj.is_service_type(OGCServiceEnum.WFS):
    #         queryset = obj.featuretypes.all().prefetch_related('keywords')
    #     return FeatureTypeSerializer(queryset, many=True, context=self.context).data

    # @staticmethod
    # def get_keywords(obj) -> KeywordSerializer:
    #     try:
    #         keywords = obj.keywords
    #     except ObjectDoesNotExist:
    #         keywords = None
    #     if keywords:
    #         return KeywordSerializer(keywords, many=True).data
    #     return None
