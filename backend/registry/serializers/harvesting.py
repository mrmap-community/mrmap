from django.utils.translation import gettext_lazy as _
from extras.serializers import StringRepresentationSerializer
from notify.models import BackgroundProcess
from registry.models.harvest import HarvestingJob, TemporaryMdMetadataFile
from registry.serializers.service import CatalogueServiceSerializer
from rest_framework_json_api.serializers import (HyperlinkedIdentityField,
                                                 ModelSerializer,
                                                 ResourceRelatedField,
                                                 UniqueTogetherValidator)


class HarvestingJobSerializer(
        StringRepresentationSerializer,
        ModelSerializer):
    url = HyperlinkedIdentityField(
        view_name='registry:harvestingjob-detail',
    )

    background_process = ResourceRelatedField(
        model=BackgroundProcess,
        label=_("Background Process"),
        help_text=_("the parent of this node"),
        read_only=True,
    )

    included_serializers = {
        'service': CatalogueServiceSerializer,
    }

    class Meta:
        model = HarvestingJob
        fields = "__all__"
        validators = [
            UniqueTogetherValidator(
                queryset=HarvestingJob.objects.filter(done_at__isnull=True),
                fields=["service"],
                message=_(
                    "There is an existing harvesting job for this service.")
            )
        ]


class TemporaryMdMetadataFileSerializer(
    StringRepresentationSerializer,
    ModelSerializer
):
    url = HyperlinkedIdentityField(
        view_name='registry:TemporaryMdMetadataFile-detail',
    )

    class Meta:
        model = TemporaryMdMetadataFile
        fields = "__all__"
