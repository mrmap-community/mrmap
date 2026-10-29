from django.utils.translation import gettext_lazy as _
from extras.serializers import (StringRepresentationSerializer,
                                SystemInfoSerializerMixin,
                                TimeUntilNextRunMixin)
from registry.enums.harvesting import LogLevelEnum
from registry.models.harvest import (HarvestedMetadataRelation, HarvestingJob,
                                     HarvestingLog, PeriodicHarvestingJob,
                                     TemporaryMdMetadataFile)
from registry.models.service import CatalogueService
from registry.serializers.service import CatalogueServiceSerializer
from rest_framework_json_api.relations import ResourceRelatedField
from rest_framework_json_api.serializers import (CharField, ChoiceField, DurationField,
                                                 FloatField,
                                                 HyperlinkedIdentityField,
                                                 HyperlinkedModelSerializer,
                                                 IntegerField, ModelSerializer,
                                                 SerializerMethodField,
                                                 ValidationError)
from system.fields import CrontabStringField


class PeriodicHarvestingJobSerializer(
    StringRepresentationSerializer,
    SystemInfoSerializerMixin,
    TimeUntilNextRunMixin,
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
    time_until_next_run = SerializerMethodField(label=_("time until next run"))

    class Meta:
        model = PeriodicHarvestingJob
        fields = ('url', 'service', 'scheduling',
                  'time_until_next_run', 'enabled')


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
    #    many=True,
    #    related_link_view_name='registry:harvestingjob-harvesteddatasetmetadatarelations-list',
    #    related_link_url_kwarg='parent_lookup_harvesting_job',
    #    label=_("harvested dataset metadata"),
    #    help_text=_(
    #       "all harvested dataset metadata records with collecting state"),
    #   read_only=True,)
    # harvested_service_metadata = HyperlinkedRelatedField(
    #    many=True,
    #    related_link_view_name='registry:harvestingjob-harvestedservicemetadatarelations-list',
    #    related_link_url_kwarg='parent_lookup_harvesting_job',
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
    records_per_minute = FloatField(
        label=_("records per minute"),
        help_text=_(
            "how many records this run stored per minute of measured work, at the step size it "
            "asked the catalogue with. Only a run which finished answers one, because only it "
            "measured a harvest as a whole. Measured work is the summed download and database "
            "time of the records of the run, which spreads the time of a response over its "
            "records: the number compares step sizes with each other, it is no promise about a "
            "single run."),
        read_only=True)

    total_steps = IntegerField(read_only=True)
    done_steps = IntegerField(read_only=True)
    progress = FloatField(read_only=True)

    phase_label = CharField(source="get_phase_display", read_only=True)
    phase = IntegerField(required=False)
    # TODO: use IntegerChoices instead
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
        # the background_process is the overview's view ON this job, not a
        # field of the job itself: the process is explored on its own screen
        exclude = (
            "harvested_dataset_metadata",
            "harvested_service_metadata",
            "background_process",
        )

    def validate_service(self, value):
        # cause model.full_clean ist not called and therefore no ValidationError is raised by the UniqueConstraint from model side.
        # Instead without this extra validation, the endpoint will lead into IntegrityError --> 5xx internal server error
        if HarvestingJob.objects.filter(
            service=value,
            done_at__isnull=True
        ).exists():
            raise ValidationError(
                _("There is an existing running harvesting job for this service.")
            )
        return value


class CreateHarvestingJobSerializer(HarvestingJobSerializer):
    phase = None

    class Meta:
        model = HarvestingJob
        exclude = (
            "harvested_dataset_metadata",
            "harvested_service_metadata",
            "background_process",
            "phase",
        )

    def validate(self, attrs):
        """a harvest which names no step size starts from the size the catalogue answers (#691)

        The catalogue is the memory of the size a remote service is known to answer, the job stays
        the record of one run: an explicit size of the request still wins and is stored on the job as
        it is today.
        """
        attrs = super().validate(attrs)
        service = attrs.get("service")
        if service is not None and "max_step_size" not in attrs:
            attrs["max_step_size"] = service.max_step_size
        return attrs


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
