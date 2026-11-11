from django.utils.translation import gettext_lazy as _
from extras.scheduling import next_run_expected_at
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
from rest_framework_json_api.serializers import (CharField, ChoiceField,
                                                 DateTimeField, DurationField,
                                                 FloatField,
                                                 HyperlinkedIdentityField,
                                                 HyperlinkedModelSerializer,
                                                 IntegerField, ModelSerializer,
                                                 SerializerMethodField,
                                                 ValidationError)
from system.fields import CrontabStringField


def validate_harvestable_service(service):
    if service is not None and not service.is_harvestable:
        raise ValidationError(_("The internal MrMap catalogue cannot be harvested."))
    return service


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
    next_run_at = SerializerMethodField(
        label=_("next run at"),
        help_text=_(
            "the moment this schedule is expected to fire next, as an aware "
            "instant: the same rule which decides that a schedule is overdue. "
            "A schedule which is disabled, expired or without a crontab "
            "answers nothing."),
        allow_null=True)
    last_run_at = DateTimeField(
        label=_("last run at"),
        help_text=_(
            "the moment this schedule last fired; nothing, while it never "
            "fired."),
        read_only=True,
        allow_null=True)
    total_run_count = IntegerField(
        label=_("total run count"),
        help_text=_("how often this schedule fired in all."),
        read_only=True)

    class Meta:
        model = PeriodicHarvestingJob
        fields = ('url', 'service', 'scheduling',
                  'time_until_next_run', 'next_run_at',
                  'enabled', 'last_run_at', 'total_run_count')

    def validate_service(self, value):
        return validate_harvestable_service(value)

    def _answers_next_run(self, name):
        """Whether the request of these schedules asks the named next-run answer.

        Both the human reading and the instant of the next run are decided in
        python, so the sparse fieldset of the request decides whether they are
        calculated at all: a screen which shows no next run pays for no
        estimate (#1082, cf. the annotations of the harvesting jobs).
        """
        view = self.context.get("view")
        check = getattr(view, "check_sparse_fields_contains", None)
        return True if check is None else check(name)

    def get_time_until_next_run(self, obj):
        if not self._answers_next_run("timeUntilNextRun"):
            return None
        return super().get_time_until_next_run(obj)

    def get_next_run_at(self, obj):
        if not self._answers_next_run("nextRunAt"):
            return None
        return next_run_expected_at(obj)


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
    new_application_metadata_count = IntegerField(read_only=True)
    updated_application_metadata_count = IntegerField(read_only=True)
    existing_application_metadata_count = IntegerField(read_only=True)
    duplicated_application_metadata_count = IntegerField(read_only=True)

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

    elapsed_seconds = FloatField(
        label=_("elapsed seconds"),
        help_text=_(
            "how long this run has been working, in seconds: from the moment the run was made "
            "to its end, or to the moment of the request while it still works. The moment the "
            "run was made is its `dateCreated`, or - where the harvesting never set one - the "
            "first row of its change log; a run which was made at no answerable moment answers "
            "nothing."),
        read_only=True)
    records_per_minute_running = FloatField(
        label=_("records per minute so far"),
        help_text=_(
            "how many records per minute this run has stored so far, against the time it has "
            "worked: the records it downloaded while it downloads, the records it wrote to the "
            "database while it imports. Named apart from `recordsPerMinute`, because it answers "
            "a run which is still working; what it measures is the run which is watched, not the "
            "size of the pages a harvest asks with."),
        read_only=True)
    estimated_seconds_remaining = FloatField(
        label=_("estimated seconds remaining"),
        help_text=_(
            "how long this run estimates itself to still take, in seconds: its elapsed time "
            "against the progress its steps already answer, scaled to the part which is left. An "
            "estimate and no measured duration: a run whose records are not known yet, which has "
            "done nothing yet, or which is closed answers nothing, because nothing is known or "
            "nothing is left then."),
        read_only=True)
    expected_done_at = DateTimeField(
        label=_("expected done at"),
        help_text=_(
            "the moment this run is expected to end: its `estimatedSecondsRemaining` added to "
            "the moment of the request. Where no estimate is answered, no end is answered "
            "either."),
        read_only=True)

    total_steps = IntegerField(read_only=True)
    done_steps = IntegerField(read_only=True)
    progress = FloatField(read_only=True)

    import_stalled_at = DateTimeField(
        label=_("import stalled at"),
        help_text=_(
            "since when the import watchdog sees the backlog of this run "
            "untouched: as many records are waiting for their import as on the "
            "watchdog's look before. A run which imports answers nothing, and what "
            "the watchdog did about the standstill is on the harvesting log of the "
            "run."),
        read_only=True)

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
        # field of the job itself: the process is explored on its own screen.
        # The harvested relations go the same way: the records a run collected
        # are explored as harvested-metadata-records, so the job answers their
        # counts but never the records themselves (#827 adds the third of them)
        # The watchdog's two counting fields are its memory, answered by
        # nothing: only its verdict, the re-declared `import_stalled_at` above,
        # reaches the api (#1038).
        exclude = (
            "harvested_dataset_metadata",
            "harvested_service_metadata",
            "harvested_application_metadata",
            "background_process",
            "import_backlog_seen",
            "import_backlog_seen_at",
        )

    def validate_service(self, value):
        validate_harvestable_service(value)
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
            "harvested_application_metadata",
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


class HarvestingLogListSerializer(
    StringRepresentationSerializer,
    SystemInfoSerializerMixin,
    ModelSerializer
):
    """The rows of a log list: the message of the line and whether an
    extended description is stored behind it.

    The detail of a failed page - the response content - sits in
    ``extented_description``, a FileField: a list which shows it answers a
    download per row, a list which hides it shows nothing. So the list
    answers the existence of the file and the content is read per log line,
    by a caller allowed to read the run; these files are the pile #888
    bounds and the list must not widen their read access (#1083).
    """
    url = HyperlinkedIdentityField(
        view_name="registry:harvestinglog-detail",)
    has_extended_description = SerializerMethodField(
        label=_("has extended description"),
        help_text=_(
            "whether this log line has a stored response behind it; the "
            "content of the file is answered on the line itself, never in "
            "a list"),
        read_only=True)

    class Meta:
        model = HarvestingLog
        exclude = ("extented_description",)

    def get_has_extended_description(self, obj) -> bool:
        return bool(obj.extented_description)


class HarvestingLogSerializer(HarvestingLogListSerializer):
    """One log line, read on its own: it answers its stored response too.

    Reading one line is the act of a caller who reads the run; the list
    above is not that act and keeps the file out of its rows (#1083).
    """

    # a fresh Meta rather than an inherited one: DRF refuses a serializer
    # which sets `fields` while a parent's `exclude` still applies
    class Meta:
        model = HarvestingLog
        fields = "__all__"
