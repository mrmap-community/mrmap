from django.utils.translation import gettext_lazy as _
from extras.serializers import StringRepresentationSerializer
from notify.models import BackgroundProcess
from notify.serializers import BackgroundProcessSerializer
from registry.models.harvest import HarvestingJob, TemporaryMdMetadataFile
from registry.serializers.service import CatalogueServiceSerializer
from rest_framework_json_api.serializers import (HyperlinkedIdentityField,
                                                 ModelSerializer,
                                                 ResourceRelatedField,
                                                 UniqueTogetherValidator)


class TemporaryMdMetadataFileSerializer(
    StringRepresentationSerializer,
    ModelSerializer
):
    url = HyperlinkedIdentityField(
        view_name='registry:temporarymdmetadatafile-detail',
    )

    class Meta:
        model = TemporaryMdMetadataFile
        fields = "__all__"


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
    temporary_md_metadata_files = ResourceRelatedField(
        many=True,
        related_link_view_name='registry:harvestingjob-temporarymdmetadatafiles-list',
        related_link_url_kwarg='parent_lookup_job',
        label=_("Temporary Md Metadata File"),
        help_text=_("collected records"),
        read_only=True
    )

    included_serializers = {
        'service': CatalogueServiceSerializer,
        'background_process': BackgroundProcessSerializer,
        'temporary_md_metadata_files': TemporaryMdMetadataFileSerializer,
    }

    class Meta:
        model = HarvestingJob
        fields = "__all__"
        validators = [
            UniqueTogetherValidator(
                queryset=HarvestingJob.objects.filter(
                    background_process__done_at__isnull=True),
                fields=["service"],
                message=_(
                    "There is an existing running harvesting job for this service.")
            )
        ]
