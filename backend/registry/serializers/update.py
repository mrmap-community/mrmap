from django.db import IntegrityError, transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from extras.fields import CrontabStringField
from extras.serializers import (StringRepresentationSerializer,
                                SystemInfoSerializerMixin)
from registry.models import (CatalogueService, CatalogueServiceUpdateJob,
                             FeatureType, FeatureTypeMapping, Layer,
                             LayerMapping, WebFeatureService,
                             WebFeatureServiceUpdateJob, WebMapService,
                             WebMapServiceUpdateJob)
from registry.models.update import (CatalogueServiceUpdateSetting,
                                    WebFeatureServiceUpdateSetting,
                                    WebMapServiceUpdateSetting)
from registry.serializers.service import (CatalogueServiceSerializer,
                                          WebFeatureServiceSerializer,
                                          WebMapServiceSerializer)
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.fields import SerializerMethodField
from rest_framework_json_api.relations import ResourceRelatedField
from rest_framework_json_api.serializers import (BooleanField, CharField,
                                                 DateTimeField,
                                                 HyperlinkedIdentityField,
                                                 IntegerField, ModelSerializer,
                                                 Serializer)


class UpdateSettingSerializer(
    Serializer
):
    url = HyperlinkedIdentityField(
        view_name='registry:webmapservicemonitoringsetting-detail',
    )
    schedule_interval = CrontabStringField(
        source='crontab',
        label=_("schedule interval"),
        help_text=_(
            "the schedule interval for this setting (e.g. '*/5 * * * *')."),
    )

    last_run_at = DateTimeField(read_only=True, allow_null=True)
    next_run_expected_at = DateTimeField(read_only=True, allow_null=True)
    run_overdue = SerializerMethodField()

    def get_run_overdue(self, obj) -> bool:
        current_time = timezone.now()
        if obj.expires is not None and obj.expires <= current_time:
            return False
        expected_at = obj.next_run_expected_at
        return expected_at is not None and expected_at < current_time

    class Meta:
        fields = ('url', 'schedule_interval', 'enabled',
                  'last_run_at', 'next_run_expected_at', 'run_overdue')


class WebMapServiceUpdateSettingSerializer(
    UpdateSettingSerializer,
    StringRepresentationSerializer,
    SystemInfoSerializerMixin,
    ModelSerializer
):
    service = ResourceRelatedField(
        label=_("web map service"),
        help_text=_("the web map service for that this settings are."),
        queryset=WebMapService.objects,
    )

    class Meta:
        model = WebMapServiceUpdateSetting
        fields = ('url', 'service', 'schedule_interval', 'enabled',
                  'last_run_at', 'next_run_expected_at', 'run_overdue')


class WebFeatureServiceUpdateSettingSerializer(
    UpdateSettingSerializer,
    StringRepresentationSerializer,
    SystemInfoSerializerMixin,
    ModelSerializer
):
    service = ResourceRelatedField(
        label=_("web feature service"),
        help_text=_("the web feature service for that this settings are."),
        queryset=WebFeatureService.objects,
    )

    class Meta:
        model = WebFeatureServiceUpdateSetting
        fields = ('url', 'service', 'schedule_interval', 'enabled',
                  'last_run_at', 'next_run_expected_at', 'run_overdue')


class CatalogueServiceUpdateSettingSerializer(
    UpdateSettingSerializer,
    StringRepresentationSerializer,
    SystemInfoSerializerMixin,
    ModelSerializer
):

    service = ResourceRelatedField(
        label=_("catalogue service"),
        help_text=_("the catalogue service for that this settings are."),
        queryset=CatalogueService.objects,
    )

    class Meta:
        model = CatalogueServiceUpdateSetting
        fields = ('url', 'service', 'schedule_interval', 'enabled',
                  'last_run_at', 'next_run_expected_at', 'run_overdue')


class UpdateJobBaseSerializer(Serializer):
    def validate_service(self, service):
        if self.instance is None:
            user = self.context["request"].user
            permission = f"registry.change_{service._meta.model_name}"
            if not (user.has_perm(permission) or user.has_perm(permission, service)):
                raise PermissionDenied(_("You may not update this service."))
            if self.Meta.model.objects.filter(
                service=service, done_at__isnull=True
            ).exists():
                raise ValidationError(_("There is an existing noncompleted job for this service."))
        return service

    def create(self, validated_data):
        try:
            with transaction.atomic():
                return super().create(validated_data)
        except IntegrityError as error:
            # A scheduled or manual request may have created a job after validation.
            constraint = (
                f"registry_{self.Meta.model._meta.model_name}"
                "_only_one_unfinished_update_per_service"
            )
            violated_constraint = getattr(
                getattr(error.__cause__, "diag", None), "constraint_name", None
            )
            # PostgreSQL truncates identifiers to 63 bytes.
            if violated_constraint not in (constraint, constraint[:63]):
                raise
            raise ValidationError({
                "service": _("There is an existing noncompleted job for this service.")
            }) from error

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
    status_code = IntegerField(
        source="status",
        label=_("Status Code"),
        help_text=_(
            "The current status of the update job. (Internal Representation)"),
        read_only=True,
    )
    status = CharField(
        source="get_status_display",
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
    delta = SerializerMethodField()

    def get_delta(self, obj):
        if obj.old_layer_id is None:
            return None

        changes = []
        for field in (
            "title", "abstract", "is_queryable", "is_opaque",
            "scale_min", "scale_max",
        ):
            old = getattr(obj.old_layer, field)
            new = getattr(obj.new_layer, field)
            if old != new:
                changes.append({"field": field, "old": old, "new": new})
        return changes

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
        fields = ("url", "job", "old_layer",
                  "new_layer", "created", "is_confirmed", "delta")


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
        fields = ("url", "job", "old_featuretype",
                  "new_featuretype", "created", "is_confirmed")


class WebMapServiceUpdateJobSerializer(UpdateJobBaseSerializer, ModelSerializer):
    class JSONAPIMeta:
        included_resources = ["mappings"]

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
        help_text=_(
            "The web map service this update job is a candidate for updating."),
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
        fields = ("url", "service", "date_created", "done_at",
                  "status", "status_code", "update_candidate", "mappings")


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
        help_text=_(
            "The web feature service this update job is a candidate for updating."),
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
        fields = ("url", "service", "date_created", "done_at",
                  "status", "status_code", "update_candidate", "mappings")


class CatalogueServiceUpdateJobSerializer(UpdateJobBaseSerializer, ModelSerializer):
    url = HyperlinkedIdentityField(
        view_name="registry:catalogueserviceupdatejob-detail",
        read_only=True,
    )
    service = ResourceRelatedField(
        label=_("Catalogue Service"),
        help_text=_("The catalogue service this update job belongs to."),
        queryset=CatalogueService.objects,
    )
    update_candidate = ResourceRelatedField(
        source="service.catalogueservice_update_candidate",
        label=_("Update Candidate"),
        help_text=_(
            "The catalogue service this update job is a candidate for updating."),
        model=CatalogueService,
        read_only=True,
    )

    included_serializers = {
        "service": CatalogueServiceSerializer,
        "update_candidate": CatalogueServiceSerializer,
    }

    class Meta:
        model = CatalogueServiceUpdateJob
        fields = ("url", "service", "date_created", "done_at",
                  "status", "update_candidate")
