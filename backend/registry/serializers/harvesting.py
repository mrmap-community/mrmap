from django.utils.translation import gettext_lazy as _
from extras.serializers import StringRepresentationSerializer
from notify.models import BackgroundProcess
from notify.serializers import BackgroundProcessSerializer
from registry.models.harvest import (HarvestedDatasetMetadataRelation,
                                     HarvestedServiceMetadataRelation,
                                     HarvestingJob, TemporaryMdMetadataFile)
from registry.serializers.service import CatalogueServiceSerializer
from rest_framework_json_api.serializers import (HyperlinkedIdentityField,
                                                 ModelSerializer,
                                                 ResourceRelatedField,
                                                 UniqueTogetherValidator)


class HarvestedDatasetMetadataRelationSerializer(
    StringRepresentationSerializer,
    ModelSerializer
):
    url = HyperlinkedIdentityField(
        view_name="registry:harvesteddatasetmetadatarelation-detail"
    )

    class Meta:
        model = HarvestedDatasetMetadataRelation
        fields = "__all__"


class HarvestedServiceMetadataRelationSerializer(
    StringRepresentationSerializer,
    ModelSerializer
):
    url = HyperlinkedIdentityField(
        view_name="registry:harvestedservicemetadatarelation-detail"
    )

    class Meta:
        model = HarvestedServiceMetadataRelation
        fields = "__all__"


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
    harvested_dataset_metadata = ResourceRelatedField(
        many=True,
        related_link_view_name='registry:harvestingjob-harvesteddatasetmetadatarelations-list',
        related_link_url_kwarg='parent_lookup_harvesting_job',
        label=_("harvested dataset metadata"),
        help_text=_(
            "all harvested dataset metadata records with collecting state"),
        read_only=True
    )
    harvested_service_metadata = ResourceRelatedField(
        many=True,
        related_link_view_name='registry:harvestingjob-harvestedservicemetadatarelations-list',
        related_link_url_kwarg='parent_lookup_harvesting_job',
        label=_("harvested service metadata"),
        help_text=_(
            "all harvested service metadata records with collecting state"),
        read_only=True
    )

    included_serializers = {
        'service': CatalogueServiceSerializer,
        'background_process': BackgroundProcessSerializer,
        'temporary_md_metadata_files': TemporaryMdMetadataFileSerializer,
        "harvested_dataset_metadata": HarvestedDatasetMetadataRelationSerializer,
        "harvested_service_metadata": HarvestedServiceMetadataRelationSerializer,
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
