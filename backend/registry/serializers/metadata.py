from extras.serializers import (StringRepresentationSerializer,
                                SystemInfoSerializerMixin)
from registry.models.metadata import (DatasetMetadataRecord, Keyword, Licence,
                                      MetadataContact, MimeType,
                                      ReferenceSystem, ServiceMetadataRecord,
                                      Style)
from registry.models.service import CatalogueService, FeatureType, Layer
from rest_framework.fields import SerializerMethodField
from rest_framework.relations import HyperlinkedIdentityField
from rest_framework_json_api.relations import ResourceRelatedField
from rest_framework_json_api.serializers import ModelSerializer


class MimeTypeSerializer(
    StringRepresentationSerializer,
    SystemInfoSerializerMixin,
    ModelSerializer
):

    class Meta:
        model = MimeType
        fields = "__all__"


class KeywordSerializer(
        StringRepresentationSerializer,
        SystemInfoSerializerMixin,
        ModelSerializer):

    url = HyperlinkedIdentityField(
        view_name="registry:keyword-detail",
    )

    class Meta:
        model = Keyword
        fields = "__all__"


class LicenceSerializer(
        StringRepresentationSerializer,
        SystemInfoSerializerMixin,
        ModelSerializer):

    url = HyperlinkedIdentityField(
        view_name="registry:licence-detail",
    )

    class Meta:
        model = Licence
        fields = "__all__"


class ReferenceSystemDefaultSerializer(
        StringRepresentationSerializer,
        SystemInfoSerializerMixin,
        ModelSerializer):

    url = HyperlinkedIdentityField(
        view_name="registry:referencesystem-detail",
    )

    class Meta:
        model = ReferenceSystem
        fields = "__all__"


class ReferenceSystemRetrieveSerializer(
        StringRepresentationSerializer,
        SystemInfoSerializerMixin,
        ModelSerializer):

    wkt = SerializerMethodField()
    bbox = SerializerMethodField()
    is_xy_order = SerializerMethodField()
    is_yx_order = SerializerMethodField()

    url = HyperlinkedIdentityField(
        view_name="registry:referencesystem-detail",
    )

    class Meta:
        model = ReferenceSystem
        fields = "__all__"

    def get_wkt(self, obj):
        return obj.wkt

    def get_bbox(self, obj):
        if obj.extent:
            return obj.extent.envelope.geojson

    def get_is_xy_order(self, obj):
        return obj.is_xy_order

    def get_is_yx_order(self, obj):
        return obj.is_yx_order


class StyleSerializer(
        StringRepresentationSerializer,
        SystemInfoSerializerMixin,
        ModelSerializer):

    url = HyperlinkedIdentityField(
        view_name="registry:style-detail",
    )

    class Meta:
        model = Style
        fields = "__all__"


class MetadataContactSerializer(
        StringRepresentationSerializer,
        SystemInfoSerializerMixin,
        ModelSerializer):

    url = HyperlinkedIdentityField(view_name="registry:metadatacontact-detail")

    class Meta:
        model = MetadataContact
        fields = "__all__"


class DatasetMetadataRecordSerializer(
        StringRepresentationSerializer,
        SystemInfoSerializerMixin,
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
    harvested_through = ResourceRelatedField(
        queryset=CatalogueService.objects,
        many=True,
        related_link_view_name="registry:datasetmetadata-csws-list",
        related_link_url_kwarg="parent_lookup_dataset_metadata_relation__dataset_metadata",
    )
    dataset_contact = ResourceRelatedField(
        queryset=MetadataContact.objects,
        related_link_view_name='registry:datasetmetadata-datasetcontact-list',
        related_link_url_kwarg='parent_lookup_datasetmetadatarecord_dataset_contact'
    )
    metadata_contact = ResourceRelatedField(
        queryset=MetadataContact.objects,
        related_link_view_name='registry:datasetmetadata-metadatacontact-list',
        related_link_url_kwarg='parent_lookup_datasetmetadatarecord_metadata_contact'
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
        "harvested_through": "registry.serializers.service.CatalogueServiceSerializer",
        "dataset_contact": MetadataContactSerializer,
        "metadata_contact": MetadataContactSerializer,
        "keywords": KeywordSerializer,
        # "created_by": UserSerializer,
        # "last_modified_by": UserSerializer,
    }

    class Meta:
        model = DatasetMetadataRecord
        fields = "__all__"


class ServiceMetadataRecordSerializer(
        StringRepresentationSerializer,
        SystemInfoSerializerMixin,
        ModelSerializer):

    url = HyperlinkedIdentityField(view_name="registry:servicemetadata-detail")

    harvested_through = ResourceRelatedField(
        queryset=CatalogueService.objects,
        many=True,
        related_link_view_name="registry:servicemetadata-csws-list",
        related_link_url_kwarg="parent_lookup_service_metadata_relation__service_metadata",
    )
    metadata_contact = ResourceRelatedField(
        queryset=MetadataContact.objects,
        # related_link_view_name='registry:servicemetadata-metadatacontact-list',
        # related_link_url_kwarg='parent_lookup_servicemetadatarecord_metadata_contact'
    )
    licence = ResourceRelatedField(
        queryset=Licence.objects,
        # related_link_view_name='registry:servicemetadata-licence-list',
        # related_link_url_kwarg='parent_lookup_servicemetadata'
    )
    keywords = ResourceRelatedField(
        queryset=Keyword.objects,
        many=True,
        # related_link_view_name='registry:servicemetadata-keywords-list',
        # related_link_url_kwarg='parent_lookup_servicemetadata_metadata'
    )
    reference_systems = ResourceRelatedField(
        queryset=ReferenceSystem.objects,
        many=True,
        # related_link_view_name='registry:servicemetadata-referencesystems-list',
        # related_link_url_kwarg='parent_lookup_service_metadata'
    )

    included_serializers = {
        "metadata_contact": MetadataContactSerializer,
        "keywords": KeywordSerializer,
        # "created_by": UserSerializer,
        # "last_modified_by": UserSerializer,
    }

    class Meta:
        model = ServiceMetadataRecord
        fields = "__all__"
        fields = "__all__"
