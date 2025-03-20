from django.utils.translation import gettext_lazy as _
from extras.serializers import StringRepresentationSerializer
from notify.serializers import BackgroundProcessSerializer
from registry.enums.harvesting import CollectingStatenEnum
from registry.models.harvest import (HarvestedDatasetMetadataRelation,
                                     HarvestedServiceMetadataRelation,
                                     HarvestingJob, TemporaryMdMetadataFile)
from registry.serializers.service import CatalogueServiceSerializer
from rest_framework_json_api.serializers import (DurationField, FloatField,
                                                 HyperlinkedIdentityField,
                                                 HyperlinkedModelSerializer,
                                                 IntegerField, ModelSerializer,
                                                 UniqueTogetherValidator)


class HarvestedDatasetMetadataRelationSerializer(
    StringRepresentationSerializer,
    ModelSerializer
):
    url = HyperlinkedIdentityField(
        view_name="registry:harvesteddatasetmetadatarelation-detail",)

    class Meta:
        model = HarvestedDatasetMetadataRelation
        fields = "__all__"


class HarvestedServiceMetadataRelationSerializer(
    StringRepresentationSerializer,
    ModelSerializer
):
    url = HyperlinkedIdentityField(
        view_name="registry:harvestedservicemetadatarelation-detail",)

    class Meta:
        model = HarvestedServiceMetadataRelation
        fields = "__all__"


class TemporaryMdMetadataFileSerializer(
    StringRepresentationSerializer,
    ModelSerializer
):
    url = HyperlinkedIdentityField(
        view_name='registry:temporarymdmetadatafile-detail',)

    class Meta:
        model = TemporaryMdMetadataFile
        fields = "__all__"


class HarvestingJobSerializer(
        StringRepresentationSerializer,
        HyperlinkedModelSerializer):
    url = HyperlinkedIdentityField(
        view_name='registry:harvestingjob-detail')
    # background_process = ResourceRelatedField(
    #     model=BackgroundProcess,
    #     label=_("Background Process"),
    #     help_text=_("the parent of this node"),
    #     read_only=True,)
    # temporary_md_metadata_files = HyperlinkedRelatedField(
    #    many=True,
    #    related_link_view_name='registry:harvestingjob-temporarymdmetadatafiles-list',
    #    related_link_url_kwarg='parent_lookup_job',
    #    label=_("Temporary Md Metadata File"),
    #    help_text=_("collected records"),
    #    read_only=True,)
    # harvested_dataset_metadata = HyperlinkedRelatedField(
    #    many=True,
   #     related_link_view_name='registry:harvestingjob-harvesteddatasetmetadatarelations-list',
   #     related_link_url_kwarg='parent_lookup_harvesting_job',
   #     label=_("harvested dataset metadata"),
   #     help_text=_(
    #       "all harvested dataset metadata records with collecting state"),
    #   read_only=True,)
    # harvested_service_metadata = HyperlinkedRelatedField(
   #     many=True,
   #     related_link_view_name='registry:harvestingjob-harvestedservicemetadatarelations-list',
   #     related_link_url_kwarg='parent_lookup_harvesting_job',
    #    label=_("harvested service metadata"),
    #    help_text=_(
    #        "all harvested service metadata records with collecting state"),
    #    read_only=True,)

    new_dataset_metadata_count = IntegerField(read_only=True)
    updated_dataset_metadata_count = IntegerField(read_only=True)
    existing_dataset_metadata_count = IntegerField(read_only=True)
    duplicated_dataset_metadata_count = IntegerField(read_only=True)
    new_service_metadata_count = IntegerField(read_only=True)
    updated_service_metadata_count = IntegerField(read_only=True)
    existing_service_metadata_count = IntegerField(read_only=True)
    duplicated_service_metadata_count = IntegerField(read_only=True)
    import_error_count = IntegerField(read_only=True)
    unhandled_records_count = IntegerField(read_only=True)

    fetch_record_duration = DurationField(read_only=True)
    md_metadata_file_to_db_duration = DurationField(read_only=True)

    total_steps = IntegerField(read_only=True)
    done_steps = IntegerField(read_only=True)
    progress = FloatField(read_only=True)

    included_serializers = {
        'service': CatalogueServiceSerializer,
        'background_process': BackgroundProcessSerializer,
        # 'temporary_md_metadata_files': TemporaryMdMetadataFileSerializer,
        # "harvested_dataset_metadata": HarvestedDatasetMetadataRelationSerializer,
        # "harvested_service_metadata": HarvestedServiceMetadataRelationSerializer,
    }

    class Meta:
        model = HarvestingJob
        exclude = (
            "harvested_dataset_metadata",
            "harvested_service_metadata"
        )
        validators = [
            UniqueTogetherValidator(
                queryset=HarvestingJob.objects.filter(
                    background_process__done_at__isnull=True),
                fields=["service"],
                message=_(
                    "There is an existing running harvesting job for this service.")
            )
        ]
