from django.utils.translation import gettext_lazy as _
from registry.models.service import Layer, WebMapService
from registry.models.update import LayerMapping, WebMapServiceUpdateJob
from rest_framework_json_api.relations import ResourceRelatedField
from rest_framework_json_api.serializers import (BooleanField, DateTimeField,
                                                 HyperlinkedIdentityField,
                                                 IntegerField, ModelSerializer)


class WebMapServiceUpdateJobSerializer(ModelSerializer):
    url = HyperlinkedIdentityField(
        view_name="registry:webmapserviceupdatejob-detail",
        read_only=True
    )
    service = ResourceRelatedField(
        label=_("Web Map Service"),
        help_text=_("The web map service this update job belongs to."),
        queryset=WebMapService.objects
    )
    date_created = DateTimeField(
        label=_("Created"),
        help_text=_("The date and time when this update job was created."),
        read_only=True
    )
    done_at = DateTimeField(
        label=_("Done"),
        help_text=_("The date and time when this update job was completed."),
        read_only=True
    )
    status = IntegerField(
        label=_("Status"),
        help_text=_("The current status of the update job."),
        read_only=True
    )

    class Meta:
        model = WebMapServiceUpdateJob
        fields = ("url", "service",
                  "date_created", "done_at", "status")


class LayerMappingSerializer(ModelSerializer):
    url = HyperlinkedIdentityField(
        view_name="registry:layermapping-detail",
        read_only=True
    )

    job = ResourceRelatedField(
        label=_("Update Job"),
        help_text=_("The update job this layer mapping belongs to."),
        queryset=WebMapServiceUpdateJob.objects
    )
    new_layer = ResourceRelatedField(
        label=_("New Layer"),
        help_text=_("The new layer this mapping points to."),
        queryset=Layer.objects
    )
    old_layer = ResourceRelatedField(
        label=_("Old Layer"),
        help_text=_("The old layer this mapping points to."),
        queryset=Layer.objects
    )
    created = DateTimeField(
        label=_("Created"),
        help_text=_("The date and time when this layer mapping was created."),
        read_only=True
    )
    is_confirmed = BooleanField(
        label=_("Is Confirmed"),
        help_text=_("Whether this layer mapping is confirmed or not."),
        default=False
    )

    class Meta:
        model = LayerMapping
        fields = ("url", "old_layer", "new_layer", "is_confirmed")
