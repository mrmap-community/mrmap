from registry.models.metadata import (DatasetMetadata, Keyword,
                                      MetadataContact, ReferenceSystem, Style)
from registry.models.service import FeatureType, Layer
from rest_framework.relations import HyperlinkedIdentityField
from rest_framework_json_api.relations import ResourceRelatedField
from rest_framework_json_api.serializers import ModelSerializer


class KeywordSerializer(ModelSerializer):

    url = HyperlinkedIdentityField(
        view_name="registry:keyword-detail",
    )

    class Meta:
        model = Keyword
        fields = "__all__"


class StyleSerializer(ModelSerializer):

    url = HyperlinkedIdentityField(
        view_name="registry:style-detail",
    )

    class Meta:
        model = Style
        fields = "__all__"


class MetadataContactSerializer(ModelSerializer):

    url = HyperlinkedIdentityField(view_name="registry:metadatacontact-detail")

    class Meta:
        model = MetadataContact
        fields = "__all__"


class DatasetMetadataSerializer(ModelSerializer):

    url = HyperlinkedIdentityField(view_name="registry:datasetmetadata-detail")

    self_pointing_layers = ResourceRelatedField(
        queryset=Layer.objects,
        many=True,  # necessary for M2M fields & reverse FK fields
        # TODO:
        # related_link_view_name="registry:wms-layers-list",
        # related_link_url_kwarg="parent_lookup_service",
        # self_link_view_name="registry:wms-relationships",
    )
    self_pointing_feature_types = ResourceRelatedField(
        queryset=FeatureType.objects,
        many=True,  # necessary for M2M fields & reverse FK fields
        # TODO:
        # related_link_view_name="registry:wms-layers-list",
        # related_link_url_kwarg="parent_lookup_service",
        # self_link_view_name="registry:wms-relationships",
    )
    dataset_contact = ResourceRelatedField(
        queryset=MetadataContact.objects,
        # TODO:
        # related_link_view_name='registry:wms-metadata-contact-list',
        # related_link_url_kwarg='parent_lookup_metadata_contact_webmapservice_metadata'
    )
    metadata_contact = ResourceRelatedField(
        queryset=MetadataContact.objects,
        # TODO:
        # related_link_view_name='registry:wms-metadata-contact-list',
        # related_link_url_kwarg='parent_lookup_metadata_contact_webmapservice_metadata'
    )
    keywords = ResourceRelatedField(
        queryset=Keyword.objects,
        many=True,
        # TODO:
        # related_link_view_name='registry:wms-keywords-list',
        # related_link_url_kwarg='parent_lookup_ogcservice_metadata',
    )
    reference_systems = ResourceRelatedField(
        queryset=ReferenceSystem.objects,
        many=True,
        # TODO:
        # related_link_view_name='registry:wms-keywords-list',
        # related_link_url_kwarg='parent_lookup_ogcservice_metadata',
    )

    included_serializers = {
        "self_pointing_layers": "registry.serializers.service.LayerSerializer",
        "self_pointing_feature_types": "registry.serializers.service.FeatureTypeSerializer",
        "dataset_contact": MetadataContactSerializer,
        "metadata_contact": MetadataContactSerializer,
        "keywords": KeywordSerializer,
        # "created_by": UserSerializer,
        # "last_modified_by": UserSerializer,
    }

    class Meta:
        model = DatasetMetadata
        fields = "__all__"
