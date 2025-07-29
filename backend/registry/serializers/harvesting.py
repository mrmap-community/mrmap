
from django.utils.translation import gettext_lazy as _
from extras.serializers import (StringRepresentationSerializer,
                                SystemInfoSerializerMixin)
from registry.enums.harvesting import LogLevelEnum
from registry.models.harvest import (HarvestedMetadataRelation, HarvestingJob,
                                     HarvestingLog, PeriodicHarvestingJob,
                                     TemporaryMdMetadataFile)
from registry.models.service import CatalogueService
from registry.serializers.service import CatalogueServiceSerializer
from rest_framework_json_api.relations import ResourceRelatedField
from rest_framework_json_api.serializers import (ChoiceField, DurationField,
                                                 FloatField,
                                                 HyperlinkedIdentityField,
                                                 HyperlinkedModelSerializer,
                                                 IntegerField, ModelSerializer,
                                                 UniqueTogetherValidator)
from system.fields import CrontabStringField


class PeriodicHarvestingJobSerializer(
    StringRepresentationSerializer,
    SystemInfoSerializerMixin,
    ModelSerializer
):
    url = HyperlinkedIdentityField(
        view_name='registry:periodicharvestingjob-detail',
    )
    service = ResourceRelatedField(
        label=_("Catalogue Service"),
        help_text=_("the catalogue service for that this configuration is."),
        queryset=CatalogueService.objects,
    )
    scheduling = CrontabStringField(source='crontab')

    class Meta:
        model = PeriodicHarvestingJob
        fields = ('url', 'service', 'scheduling')


class HarvestedMetadataRelationSerializer(
    StringRepresentationSerializer,
    SystemInfoSerializerMixin,
    ModelSerializer
):
    url = HyperlinkedIdentityField(
        view_name="registry:harvestedmetadatarelation-detail",)

    class Meta:
        model = HarvestedMetadataRelation
        fields = "__all__"


class TemporaryMdMetadataFileSerializer(
    StringRepresentationSerializer,
    SystemInfoSerializerMixin,
    ModelSerializer
):
    url = HyperlinkedIdentityField(
        view_name='registry:temporarymdmetadatafile-detail',)

    class Meta:
        model = TemporaryMdMetadataFile
        fields = "__all__"


class HarvestingJobSerializer(
        StringRepresentationSerializer,
        SystemInfoSerializerMixin,
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

    phase = IntegerField(required=False)
    log_level = ChoiceField(default=LogLevelEnum.INFO,
                            choices=LogLevelEnum.choices)

    included_serializers = {
        'service': CatalogueServiceSerializer,
        # 'background_process': BackgroundProcessSerializer,
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
                    done_at__isnull=True),
                fields=["service"],
                message=_(
                    "There is an existing running harvesting job for this service.")
            )
        ]


class CreateHarvestingJobSerializer(HarvestingJobSerializer):
    phase = None

    class Meta:
        model = HarvestingJob
        exclude = (
            "harvested_dataset_metadata",
            "harvested_service_metadata",
            "phase",
        )


class HarvestingLogSerializer(
    StringRepresentationSerializer,
    SystemInfoSerializerMixin,
    ModelSerializer
):
    url = HyperlinkedIdentityField(
        view_name="registry:harvestinglog-detail",)

    class Meta:
        model = HarvestingLog
        fields = "__all__"
        fields = "__all__"
