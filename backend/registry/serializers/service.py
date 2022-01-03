from accounts.models.groups import Organization
from accounts.serializers.users import UserSerializer
from django.contrib.auth import get_user_model
from extras.serializers import ObjectPermissionCheckerSerializerMixin
from registry.models.metadata import Keyword, MetadataContact, Style
from registry.models.security import (WebFeatureServiceAuthentication,
                                      WebMapServiceAuthentication)
from registry.models.service import (FeatureType, Layer, OperationUrl,
                                     WebFeatureService, WebMapService)
from registry.serializers.metadata import (KeywordSerializer,
                                           MetadataContactSerializer,
                                           StyleSerializer)
from rest_framework.fields import BooleanField
from rest_framework_gis.fields import GeometryField
from rest_framework_json_api.relations import (
    HyperlinkedRelatedField, ResourceRelatedField,
    SerializerMethodResourceRelatedField)
from rest_framework_json_api.serializers import (HyperlinkedIdentityField,
                                                 HyperlinkedModelSerializer,
                                                 ModelSerializer,
                                                 SerializerMethodField)


class OperationsUrlSerializer(ModelSerializer):

    class Meta:
        model = OperationUrl
        fields = '__all__'


class LayerSerializer(ModelSerializer):
    url = HyperlinkedIdentityField(
        view_name='registry:layer-detail',
    )

    bbox_lat_lon = GeometryField()

    service = ResourceRelatedField(
        # model=WebMapService,
        queryset=WebMapService.objects,
        related_link_view_name='registry:layer-wms-detail',
        related_link_lookup_field='pk',
        related_link_url_kwarg='layer_pk'
        # elf_link_view_name='registry:wms-relationships',
    )
    styles = HyperlinkedRelatedField(
        queryset=Style.objects,
        many=True,  # necessary for M2M fields & reverse FK fields
        related_link_view_name='registry:layer-styles-list',
        related_link_url_kwarg='parent_lookup_layer',
        self_link_view_name='registry:layer-relationships',
    )
    keywords = HyperlinkedRelatedField(
        queryset=Keyword.objects,
        many=True,  # necessary for M2M fields & reverse FK fields
        related_link_view_name='registry:layer-keywords-list',
        related_link_url_kwarg='parent_lookup_layer',
        self_link_view_name='registry:layer-relationships',
    )

    included_serializers = {
        'styles': StyleSerializer,
        'keywords': KeywordSerializer,
    }

    class Meta:
        model = Layer
        fields = '__all__'


class WebMapServiceSerializer(ObjectPermissionCheckerSerializerMixin, HyperlinkedModelSerializer):

    url = HyperlinkedIdentityField(
        view_name='registry:wms-detail',
    )

    layers = ResourceRelatedField(
        # queryset=Layer.objects,
        model=Layer,
        many=True,  # necessary for M2M fields & reverse FK fields
        related_link_view_name='registry:wms-layers-list',
        related_link_url_kwarg='parent_lookup_service',
        self_link_view_name='registry:wms-relationships',
        read_only=True,
        # meta_attrs={'layer_count': 'count'}
    )

    service_contact = ResourceRelatedField(
        queryset=MetadataContact.objects,
        related_link_view_name='registry:wms-service-contact-list',
        related_link_url_kwarg='parent_lookup_service_contact_webmapservice_metadata'
    )
    metadata_contact = ResourceRelatedField(
        queryset=MetadataContact.objects,
        related_link_view_name='registry:wms-metadata-contact-list',
        related_link_url_kwarg='parent_lookup_metadata_contact_webmapservice_metadata'
    )
    keywords = ResourceRelatedField(
        queryset=Keyword.objects,
        many=True,
        related_link_view_name='registry:wms-keywords-list',
        related_link_url_kwarg='parent_lookup_ogcservice_metadata',
        # meta_attrs={'keyword_count': 'count'}
    )
    created_at = SerializerMethodField()
    last_modified_at = SerializerMethodField()

    is_accessible = SerializerMethodField()

    created_by = SerializerMethodResourceRelatedField(
        model=get_user_model(),
        required=False,
        # related_link_view_name='accounts:user-detail',
        # related_link_url_kwarg='pk',
    )
    last_modified_by = SerializerMethodResourceRelatedField(
        model=get_user_model(),
        required=False,
    )

    included_serializers = {
        'layers': LayerSerializer,
        'service_contact': MetadataContactSerializer,
        'metadata_contact': MetadataContactSerializer,
        'keywords': KeywordSerializer,
        'created_by': UserSerializer,
        'last_modified_by': UserSerializer,
    }

    class Meta:
        model = WebMapService
        fields = "__all__"
        meta_fields = ('is_accessible', )

    def get_created_at(self, instance):
        return instance.first_history[0].history_date if instance.first_history and len(instance.first_history) == 1 else None

    def get_last_modified_at(self, instance):
        return instance.last_history[0].history_date if instance.last_history and len(instance.last_history) == 1 else None

    def get_created_by(self, instance):
        return instance.first_history[0].history_user if instance.first_history and len(instance.first_history) == 1 else None

    def get_last_modified_by(self, instance):
        return instance.last_history[0].history_user if instance.last_history and len(instance.last_history) == 1 else None

    def get_is_accessible(self, obj):
        perm_checker = self.get_perm_checker()
        return perm_checker.has_perm(f'view_{obj._meta.model_name}', obj)


class WebMapServiceCreateSerializer(ModelSerializer):

    service_auth = ResourceRelatedField(
        queryset=WebMapServiceAuthentication.objects,
        required=False)
    owner = ResourceRelatedField(
        queryset=Organization.objects)

    collect_metadata_records = BooleanField(default=True)

    class Meta:
        model = WebMapService
        fields = (
            "get_capabilities_url",
            "owner",
            "service_auth",
            "collect_metadata_records")


class FeatureTypeSerializer(ModelSerializer):

    keywords = HyperlinkedRelatedField(
        queryset=Keyword.objects,
        many=True,  # necessary for M2M fields & reverse FK fields
        related_link_view_name='registry:featuretype-keywords-list',
        related_link_url_kwarg='parent_lookup_featuretype',
        self_link_view_name='registry:featuretype-relationships',
    )

    included_serializers = {
        'keywords': KeywordSerializer,
    }

    class Meta:
        model = FeatureType
        fields = '__all__'


class WebFeatureServiceSerializer(ModelSerializer):

    url = HyperlinkedIdentityField(
        view_name='registry:wfs-detail',
    )

    included_serializers = {
        'featuretypes': FeatureTypeSerializer,
    }

    featuretypes = HyperlinkedRelatedField(
        queryset=FeatureType.objects,
        many=True,  # necessary for M2M fields & reverse FK fields
        related_link_view_name='registry:wfs-featuretypes-list',
        related_link_url_kwarg='parent_lookup_service',
        self_link_view_name='registry:wfs-relationships',
    )

    class Meta:
        model = WebFeatureService
        fields = "__all__"


class WebFeatureServiceCreateSerializer(ModelSerializer):

    service_auth = ResourceRelatedField(
        queryset=WebFeatureServiceAuthentication.objects,
        required=False)
    owner = ResourceRelatedField(
        queryset=Organization.objects)

    collect_metadata_records = BooleanField(default=True)

    class Meta:
        model = WebFeatureService
        fields = (
            "get_capabilities_url",
            "owner",
            "service_auth",
            "collect_metadata_records")
