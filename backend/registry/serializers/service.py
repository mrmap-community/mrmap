from accounts.models.groups import Organization
from accounts.serializers.users import UserSerializer
from django.contrib.auth import get_user_model
from extras.serializers import (HistoryInformationSerializer,
                                ObjectPermissionCheckerSerializer)
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


class FullLayerSerializer(ModelSerializer):
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
    styles = ResourceRelatedField(
        queryset=Style.objects,
        many=True,  # necessary for M2M fields & reverse FK fields
        related_link_view_name='registry:layer-styles-list',
        related_link_url_kwarg='parent_lookup_layer',
        self_link_view_name='registry:layer-relationships',
    )
    keywords = ResourceRelatedField(
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


class IncludeLayerSerializer(ModelSerializer):
    url = HyperlinkedIdentityField(
        view_name='registry:layer-detail',
    )

    bbox_lat_lon = GeometryField()

    class Meta:
        model = Layer
        exclude = ('service', 'keywords', 'reference_systems', 'parent')


class WebMapServiceSerializer(ObjectPermissionCheckerSerializer, HistoryInformationSerializer, ModelSerializer):

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

    included_serializers = {
        'layers': IncludeLayerSerializer,
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
