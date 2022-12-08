from extras.serializers import StringRepresentationSerializer
from registry.models.metadata import (DatasetMetadata, Keyword, Licence,
                                      MetadataContact, ReferenceSystem, Style)
from registry.models.service import CatalogueService, FeatureType, Layer
from rest_framework.relations import HyperlinkedIdentityField
from rest_framework_json_api.relations import ResourceRelatedField
from rest_framework_json_api.serializers import ModelSerializer


class KeywordSerializer(
        StringRepresentationSerializer,
        ModelSerializer):

    url = HyperlinkedIdentityField(
        view_name="registry:keyword-detail",
    )

    class Meta:
        model = Keyword
        fields = "__all__"


class LicenceSerializer(
        StringRepresentationSerializer,
        ModelSerializer):

    url = HyperlinkedIdentityField(
        view_name="registry:licence-detail",
    )

    class Meta:
        model = Licence
        fields = "__all__"


class ReferenceSystemSerializer(
        StringRepresentationSerializer,
        ModelSerializer):

    url = HyperlinkedIdentityField(
        view_name="registry:referencesystem-detail",
    )

    class Meta:
        model = ReferenceSystem
        fields = "__all__"


class StyleSerializer(
        StringRepresentationSerializer,
        ModelSerializer):

    url = HyperlinkedIdentityField(
        view_name="registry:style-detail",
    )

    class Meta:
        model = Style
        fields = "__all__"


class MetadataContactSerializer(
        StringRepresentationSerializer,
        ModelSerializer):

    url = HyperlinkedIdentityField(view_name="registry:metadatacontact-detail")

    class Meta:
        model = MetadataContact
        fields = "__all__"


class DatasetMetadataSerializer(
        StringRepresentationSerializer,
        ModelSerializer):

    url = HyperlinkedIdentityField(view_name="registry:datasetmetadata-detail")

    self_pointing_layers = ResourceRelatedField(
        queryset=Layer.objects,
        many=True,
        related_link_view_name="registry:datasetmetadata-layers-list",
        related_link_url_kwarg="parent_lookup_dataset_metadata_relation__dataset_metadata",
    )
    self_pointing_feature_types = ResourceRelatedField(
        queryset=FeatureType.objects,
        many=True,
        related_link_view_name="registry:datasetmetadata-featuretypes-list",
        related_link_url_kwarg="parent_lookup_dataset_metadata_relation__dataset_metadata",
    )
    self_pointing_catalouge_service = ResourceRelatedField(
        queryset=CatalogueService.objects,
        many=True,
        related_link_view_name="registry:datasetmetadata-csws-list",
        related_link_url_kwarg="parent_lookup_dataset_metadata_relation__dataset_metadata",
    )
    dataset_contact = ResourceRelatedField(
        queryset=MetadataContact.objects,
        related_link_view_name='registry:datasetmetadata-datasetcontact-list',
        related_link_url_kwarg='parent_lookup_dataset_contact_metadata'
    )
    metadata_contact = ResourceRelatedField(
        queryset=MetadataContact.objects,
        related_link_view_name='registry:datasetmetadata-metadatacontact-list',
        related_link_url_kwarg='parent_lookup_metadata_contact_metadata'
    )
    licence = ResourceRelatedField(
        queryset=Licence.objects,
        related_link_view_name='registry:datasetmetadata-licence-list',
        related_link_url_kwarg='parent_lookup_datasetmetadata'
    )
    keywords = ResourceRelatedField(
        queryset=Keyword.objects,
        many=True,
        related_link_view_name='registry:datasetmetadata-keywords-list',
        related_link_url_kwarg='parent_lookup_datasetmetadata_metadata'
    )
    reference_systems = ResourceRelatedField(
        queryset=ReferenceSystem.objects,
        many=True,
        related_link_view_name='registry:datasetmetadata-referencesystems-list',
        related_link_url_kwarg='parent_lookup_dataset_metadata'
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
