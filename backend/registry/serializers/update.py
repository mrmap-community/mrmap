from django.utils.translation import gettext_lazy as _
from registry.models.service import FeatureType, Layer, WebFeatureService, WebMapService
from registry.models.update import (
    FeatureTypeMapping,
    LayerMapping,
    WebFeatureServiceUpdateJob,
    WebMapServiceUpdateJob,
)
from registry.serializers.service import WebFeatureServiceSerializer, WebMapServiceSerializer
from rest_framework_json_api.relations import ResourceRelatedField
from rest_framework_json_api.serializers import (
    BooleanField,
    DateTimeField,
    HyperlinkedIdentityField,
    IntegerField,
    ModelSerializer,
    Serializer,
)


class UpdateJobBaseSerializer(Serializer):
    date_created = DateTimeField(
        label=_("Created"),
        help_text=_("The date and time when this update job was created."),
        read_only=True,
    )
    done_at = DateTimeField(
        label=_("Done"),
        help_text=_("The date and time when this update job was completed."),
        read_only=True,
    )
    status = IntegerField(
        label=_("Status"),
        help_text=_("The current status of the update job."),
        read_only=True,
    )


class MappingBaseSerializer(Serializer):
    created = DateTimeField(
        label=_("Created"),
        help_text=_("The date and time when this layer mapping was created."),
        read_only=True,
    )
    is_confirmed = BooleanField(
        label=_("Is Confirmed"),
        help_text=_("Whether this layer mapping is confirmed or not."),
        default=False,
    )


class LayerMappingSerializer(MappingBaseSerializer, ModelSerializer):
    url = HyperlinkedIdentityField(
        view_name="registry:layermapping-detail",
        read_only=True,
    )
    job = ResourceRelatedField(
        label=_("Update Job"),
        help_text=_("The update job this layer mapping belongs to."),
        queryset=WebMapServiceUpdateJob.objects,
    )
    new_layer = ResourceRelatedField(
        label=_("New Layer"),
        help_text=_("The new layer this mapping points to."),
        queryset=Layer.objects,
    )
    old_layer = ResourceRelatedField(
        label=_("Old Layer"),
        help_text=_("The old layer this mapping points to."),
        queryset=Layer.objects,
        required=False,
    )

    included_serializers = {
        "job": "registry.serializers.update.WebMapServiceUpdateJobSerializer",
    }

    class Meta:
        model = LayerMapping
        fields = ("url", "job", "old_layer", "new_layer", "created", "is_confirmed")


class FeatureTypeMappingSerializer(MappingBaseSerializer, ModelSerializer):
    url = HyperlinkedIdentityField(
        view_name="registry:featuretypemapping-detail",
        read_only=True,
    )
    job = ResourceRelatedField(
        label=_("Update Job"),
        help_text=_("The update job this featuretype mapping belongs to."),
        queryset=WebFeatureServiceUpdateJob.objects,
    )
    new_featuretype = ResourceRelatedField(
        label=_("New FeatureType"),
        help_text=_("The new featuretype this mapping points to."),
        queryset=FeatureType.objects,
    )
    old_featuretype = ResourceRelatedField(
        label=_("Old FeatureType"),
        help_text=_("The old featuretype this mapping points to."),
        queryset=FeatureType.objects,
        required=False,
    )

    included_serializers = {
        "job": "registry.serializers.update.WebFeatureServiceUpdateJobSerializer",
    }

    class Meta:
        model = FeatureTypeMapping
        fields = ("url", "job", "old_featuretype", "new_featuretype", "created", "is_confirmed")


class WebMapServiceUpdateJobSerializer(UpdateJobBaseSerializer, ModelSerializer):
    url = HyperlinkedIdentityField(
        view_name="registry:webmapserviceupdatejob-detail",
        read_only=True,
    )
    service = ResourceRelatedField(
        label=_("Web Map Service"),
        help_text=_("The web map service this update job belongs to."),
        queryset=WebMapService.objects,
    )
    update_candidate = ResourceRelatedField(
        source="service.webmapservice_update_candidate",
        label=_("Update Candidate"),
        help_text=_("The web map service this update job is a candidate for updating."),
        model=WebMapService,
        read_only=True,
    )
    mappings = ResourceRelatedField(
        model=LayerMapping,
        many=True,  # necessary for M2M fields & reverse FK fields
        # related_link_view_name="registry:wms-layers-list",
        # related_link_url_kwarg="parent_lookup_service",
        read_only=True,
    )

    included_serializers = {
        "service": WebMapServiceSerializer,
        "update_candidate": WebMapServiceSerializer,
        "mappings": LayerMappingSerializer,
    }

    class Meta:
        model = WebMapServiceUpdateJob
        fields = ("url", "service", "date_created", "done_at", "status", "update_candidate", "mappings")


class WebFeatureServiceUpdateJobSerializer(UpdateJobBaseSerializer, ModelSerializer):
    url = HyperlinkedIdentityField(
        view_name="registry:webfeatureserviceupdatejob-detail",
        read_only=True,
    )
    service = ResourceRelatedField(
        label=_("Web Feature Service"),
        help_text=_("The web feature service this update job belongs to."),
        queryset=WebFeatureService.objects,
    )
    update_candidate = ResourceRelatedField(
        source="service.webfeatureservice_update_candidate",
        label=_("Update Candidate"),
        help_text=_("The web feature service this update job is a candidate for updating."),
        model=WebFeatureService,
        read_only=True,
    )
    mappings = ResourceRelatedField(
        model=FeatureTypeMapping,
        many=True,  # necessary for M2M fields & reverse FK fields
        # related_link_view_name="registry:wfs-featuretypes-list",
        # related_link_url_kwarg="parent_lookup_service",
        read_only=True,
    )

    included_serializers = {
        "service": WebFeatureServiceSerializer,
        "update_candidate": WebFeatureServiceSerializer,
        "mappings": FeatureTypeMappingSerializer,
    }

    class Meta:
        model = WebFeatureServiceUpdateJob
        fields = ("url", "service", "date_created", "done_at", "status", "update_candidate", "mappings")
