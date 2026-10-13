from accounts.serializers.users import UserSerializer
from extras.serializers import (HistoryInformationSerializer,
                                StringRepresentationSerializer,
                                SystemInfoSerializerMixin)
from guardian.core import ObjectPermissionChecker
from registry.models.metadata import (DatasetMetadataRecord, IsoCategory, Keyword, Language, Licence,
                                      MetadataContact, MetadataRelation, MimeType,
                                      ReferenceSystem, ServiceMetadataRecord,
                                      Style, TimeExtent)
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


class TimeExtentSerializer(StringRepresentationSerializer, ModelSerializer):
    class Meta:
        model = TimeExtent
        fields = "__all__"


class LanguageSerializer(StringRepresentationSerializer, ModelSerializer):
    class Meta:
        model = Language
        fields = "__all__"


class IsoCategorySerializer(StringRepresentationSerializer, ModelSerializer):
    class Meta:
        model = IsoCategory
        fields = "__all__"


class MetadataRelationSerializer(ModelSerializer):
    included_serializers = {
        "layer": "registry.serializers.service.LayerSerializer",
        "feature_type": "registry.serializers.service.FeatureTypeSerializer",
        "wms": "registry.serializers.service.WebMapServiceSerializer",
        "wfs": "registry.serializers.service.WebFeatureServiceSerializer",
        "csw": "registry.serializers.service.CatalogueServiceSerializer",
    }

    class Meta:
        model = MetadataRelation
        fields = "__all__"


class RecordPermissionsSerializerMixin(HistoryInformationSerializer):
    can_edit = SerializerMethodField()
    can_delete = SerializerMethodField()

    def get_fields(self):
        fields = super().get_fields()
        if getattr(self.context.get("view"), "action", None) == "list":
            fields.pop("can_edit", None)
            fields.pop("can_delete", None)
        return fields

    def _can_modify(self, obj, action):
        user = self.context["request"].user
        permission = f"{obj._meta.app_label}.{action}_{obj._meta.model_name}"
        if not user.has_perm(permission):
            return False
        request = self.context["request"]
        checker = getattr(request, "record_permission_checker", None)
        if checker is None:
            checker = ObjectPermissionChecker(user)
            request.record_permission_checker = checker
        return checker.has_perm(permission, obj)

    def get_can_edit(self, obj) -> bool:
        return self._can_modify(obj, "change")

    def get_can_delete(self, obj) -> bool:
        return self._can_modify(obj, "delete")


class DatasetMetadataRecordSerializer(
        RecordPermissionsSerializerMixin,
        StringRepresentationSerializer,
        SystemInfoSerializerMixin,
        ModelSerializer):

    url = HyperlinkedIdentityField(view_name="registry:datasetmetadata-detail")

    self_pointing_layers = ResourceRelatedField(
        queryset=Layer.objects,
        many=True,
        related_link_view_name="registry:datasetmetadata-layers-list",
        related_link_url_kwarg="parent_lookup_metadata_relation__dataset_metadata",
    )
    self_pointing_feature_types = ResourceRelatedField(
        queryset=FeatureType.objects,
        many=True,
        related_link_view_name="registry:datasetmetadata-featuretypes-list",
        related_link_url_kwarg="parent_lookup_metadata_relation__dataset_metadata",
    )
    harvested_through = ResourceRelatedField(
        queryset=CatalogueService.objects,
        many=True,
        related_link_view_name="registry:datasetmetadata-csws-list",
        related_link_url_kwarg="parent_lookup_registry_datasetmetadatarecord_metadata_record",
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
        related_link_url_kwarg='parent_lookup_datasetmetadatarecord'
    )
    keywords = ResourceRelatedField(
        queryset=Keyword.objects,
        many=True,
        related_link_view_name='registry:datasetmetadata-keywords-list',
        related_link_url_kwarg='parent_lookup_datasetmetadatarecord_metadata'
    )
    reference_systems = ResourceRelatedField(
        queryset=ReferenceSystem.objects,
        many=True,
        related_link_view_name='registry:datasetmetadata-referencesystems-list',
        related_link_url_kwarg='parent_lookup_datasetmetadatarecord'
    )

    included_serializers = {
        "self_pointing_layers": "registry.serializers.service.LayerSerializer",
        "self_pointing_feature_types": "registry.serializers.service.FeatureTypeSerializer",
        "harvested_through": "registry.serializers.service.CatalogueServiceSerializer",
        "dataset_contact": MetadataContactSerializer,
        "categories": IsoCategorySerializer,
        "metadata_contact": MetadataContactSerializer,
        "keywords": KeywordSerializer,
        "licence": LicenceSerializer,
        "reference_systems": ReferenceSystemDefaultSerializer,
        "time_extents": TimeExtentSerializer,
        "languages": LanguageSerializer,
        "created_by": UserSerializer,
        "last_modified_by": UserSerializer,
    }

    class Meta:
        model = DatasetMetadataRecord
        fields = "__all__"


class ServiceMetadataRecordSerializer(
        RecordPermissionsSerializerMixin,
        StringRepresentationSerializer,
        SystemInfoSerializerMixin,
        ModelSerializer):

    url = HyperlinkedIdentityField(view_name="registry:servicemetadata-detail")

    harvested_through = ResourceRelatedField(
        queryset=CatalogueService.objects,
        many=True,
        related_link_view_name="registry:servicemetadata-csws-list",
        related_link_url_kwarg="parent_lookup_registry_servicemetadatarecord_metadata_record",
    )
    metadata_contact = ResourceRelatedField(
        queryset=MetadataContact.objects,
        # related_link_view_name='registry:servicemetadata-metadatacontact-list',
        related_link_url_kwarg='parent_lookup_servicemetadatarecord_metadata_contact'
    )
    licence = ResourceRelatedField(
        queryset=Licence.objects,
        # related_link_view_name='registry:servicemetadata-licence-list',
        related_link_url_kwarg='parent_lookup_servicemetadatarecord'
    )
    keywords = ResourceRelatedField(
        queryset=Keyword.objects,
        many=True,
        # related_link_view_name='registry:servicemetadata-keywords-list',
        related_link_url_kwarg='parent_lookup_servicemetadatarecord_metadata'
    )
    reference_systems = ResourceRelatedField(
        queryset=ReferenceSystem.objects,
        many=True,
        related_link_view_name='registry:servicemetadata-referencesystems-list',
        related_link_url_kwarg='parent_lookup_servicemetadatarecord'
    )

    included_serializers = {
        "harvested_through": "registry.serializers.service.CatalogueServiceSerializer",
        "self_pointing_wms": "registry.serializers.service.WebMapServiceSerializer",
        "self_pointing_wfs": "registry.serializers.service.WebFeatureServiceSerializer",
        "self_pointing_csw": "registry.serializers.service.CatalogueServiceSerializer",
        "metadata_contact": MetadataContactSerializer,
        "keywords": KeywordSerializer,
        "licence": LicenceSerializer,
        "reference_systems": ReferenceSystemDefaultSerializer,
        "time_extents": TimeExtentSerializer,
        "languages": LanguageSerializer,
        "created_by": UserSerializer,
        "last_modified_by": UserSerializer,
    }

    class Meta:
        model = ServiceMetadataRecord
        fields = "__all__"
