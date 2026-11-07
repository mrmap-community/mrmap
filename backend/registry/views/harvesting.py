from datetime import timedelta

from camel_converter import to_snake
from django.db.models import Case, Count, F, Prefetch, Q, Sum, When
from django.db.models.expressions import ExpressionWrapper
from django.db.models.fields import DurationField, FloatField
from django.db.models.functions import Coalesce
from django.db.models.sql.constants import LOUTER
from django_cte import CTE, with_cte
from extras.permissions import DjangoObjectPermissionsOrAnonReadOnly
from extras.viewsets import (NestedModelViewSet, PreloadNotIncludesMixin,
                             SerializerClassesMixin, SparseFieldMixin)
from notify.models import BackgroundProcess
from registry.enums.harvesting import CollectingStatenEnum, HarvestingPhaseEnum
from registry.expressions.durations import DurationSeconds
from registry.filters.harvesting import (HarvestingJobFilterSet,
                                         HarvestingLogFilterSet)
from registry.managers.havesting import RUN_PROGRESS_FIELDS
from registry.models.harvest import (HarvestedMetadataRelation, HarvestingJob,
                                     HarvestingLog, PeriodicHarvestingJob,
                                     TemporaryMdMetadataFile)
from registry.models.metadata import (DatasetMetadataRecord, Keyword, Language,
                                      ServiceMetadataRecord)
from registry.models.monitoring import CatalogueServiceMonitoringSetting
from registry.models.service import CatalogueServiceOperationUrl
from registry.serializers.harvesting import (
    CreateHarvestingJobSerializer, HarvestedMetadataRelationSerializer,
    HarvestingJobSerializer, HarvestingLogSerializer,
    PeriodicHarvestingJobSerializer, TemporaryMdMetadataFileSerializer)
from rest_framework.filters import OrderingFilter
from rest_framework_json_api.views import ModelViewSet

DEFAULT_HARVESTED_DATASET_METADATA_PREFETCHES = [
    Prefetch(
        "harvested_dataset_metadata",
        queryset=HarvestedMetadataRelation.objects.filter(
            collecting_state=CollectingStatenEnum.NEW.value).only("id"),
        to_attr="new_dataset_metadata"
    ),
    Prefetch(
        "harvested_dataset_metadata",
        queryset=HarvestedMetadataRelation.objects.filter(
            collecting_state=CollectingStatenEnum.UPDATED.value).only("id"),
        to_attr="updated_dataset_metadata"
    ),
    Prefetch(
        "harvested_dataset_metadata",
        queryset=HarvestedMetadataRelation.objects.filter(
            collecting_state=CollectingStatenEnum.EXISTING.value).only("id"),
        to_attr="existing_dataset_metadata"
    ),
    Prefetch(
        "harvested_dataset_metadata",
        queryset=HarvestedMetadataRelation.objects.filter(
            collecting_state=CollectingStatenEnum.DUPLICATED.value).only("id"),
        to_attr="duplicated_dataset_metadata"
    )
]

DEFAULT_HARVESTED_SERVICE_METADATA_PREFETCHES = [
    Prefetch(
        "harvested_service_metadata",
        queryset=HarvestedMetadataRelation.objects.filter(
            collecting_state=CollectingStatenEnum.NEW.value).only("id"),
        to_attr="new_service_metadata"
    ),
    Prefetch(
        "harvested_service_metadata",
        queryset=HarvestedMetadataRelation.objects.filter(
            collecting_state=CollectingStatenEnum.UPDATED.value).only("id"),
        to_attr="updated_service_metadata"
    ),
    Prefetch(
        "harvested_service_metadata",
        queryset=HarvestedMetadataRelation.objects.filter(
            collecting_state=CollectingStatenEnum.EXISTING.value).only("id"),
        to_attr="existing_service_metadata"
    ),
    Prefetch(
        "harvested_service_metadata",
        queryset=HarvestedMetadataRelation.objects.filter(
            collecting_state=CollectingStatenEnum.DUPLICATED.value).only("id"),
        to_attr="duplicated_service_metadata"
    )
]

BACKGROUND_PROCESS_PREFETCHES = [
    Prefetch("background_process",
             queryset=BackgroundProcess.objects.prefetch_related(
                 # Prefetch(
                 #    "threads",
                 #    queryset=TaskResult.objects.only(
                 #        "id"
                 #    )
                 # ),
                 # Prefetch(
                 #    "logs",
                 #    queryset=BackgroundProcessLog.objects.only(
                 #        "id", "background_process_id")
                 # ),
             )
             ),
]


class HarvestingJobViewSetMixin(SparseFieldMixin, SerializerClassesMixin,):
    # the annotation carries the display string of the serializer, so the sort
    # the generic pickers send is answered like the list they render (#1035);
    # the display string names the catalogue of the run, so the service rides
    # the select and str(job) answers without a read per row (#1045)
    queryset = HarvestingJob.objects \
        .with_string_representation() \
        .select_related("service")
    serializer_class = HarvestingJobSerializer
    serializer_classes = {
        "default": HarvestingJobSerializer,
        "create": CreateHarvestingJobSerializer,
    }
    permission_classes = [DjangoObjectPermissionsOrAnonReadOnly]
    # `date_created` is orderable again: #1079 filled the column, which #1080 had withdrawn from
    # the sort offers while it was still empty. The end of a run stays orderable - the throughput
    # of a catalogue is measured by the runs which ended last, and a run which never ended has no
    # end to order by (#692, #1080). The progress of a run joins the offer now that #1071 answers
    # it: it is no column of the row but the annotation of the run's own work, which the request
    # has to carry before anything can be ordered by it (`with_unhandled_records`) (#1071, #1130)
    ordering_fields = ["id", "date_created", "done_at", "string_representation", "phase",
                       "total_records", "progress"]
    filterset_class = HarvestingJobFilterSet

    select_for_includes = {
        # "service": ["service"],
        # "backgroundProcess": ["background_process"]
    }
    prefetch_for_includes = {
        # the service of a harvesting job is serialized, all relations of that
        # service are only answered as related resources
        "service": [
            Prefetch("service__keywords",
                     queryset=Keyword.objects.only("id")),
            Prefetch("service__languages",
                     queryset=Language.objects.only("value")),
            Prefetch("service__harvesting_jobs",
                     queryset=HarvestingJob.objects.only("id", "service")),
            Prefetch("service__periodic_harvesting_jobs",
                     queryset=PeriodicHarvestingJob.objects.only("id", "service")),
            Prefetch("service__catalogue_service_monitorings",
                     queryset=CatalogueServiceMonitoringSetting.objects.only(
                         "id", "service")),
            Prefetch("service__operation_urls",
                     queryset=CatalogueServiceOperationUrl.objects.only(
                         "id", "service_id")),
        ],
        # "backgroundProcess": BACKGROUND_PROCESS_PREFETCHES,
        # "backgroundProcess.logs": [
        #    Prefetch("background_process",
        #             queryset=BackgroundProcess.objects.prefetch_related(
        #                 # Prefetch(
        #                 #    "threads",
        #                 #    queryset=TaskResult.objects.only(
        #                 #        "id"
        #                 #    )
        #                 # ),
        #                 Prefetch(
        #                     "logs",
        #                     queryset=BackgroundProcessLog.objects.all()
        #                 ),
        #             )
        #             ),
        # ],
        # "temporaryMdMetadataFiles": [
        #    Prefetch('temporary_md_metadata_files',
        #             queryset=TemporaryMdMetadataFile.objects.select_related('job'))
        # ],
        # "harvestedDatasetMetadata": [
        #    Prefetch("harvested_dataset_metadata",
        #             queryset=HarvestedDatasetMetadataRelation.objects.select_related(
        #                 'harvesting_job', 'dataset_metadata_record', )
        #             )
        # ] + DEFAULT_HARVESTED_DATASET_METADATA_PREFETCHES,
        # "harvestedServiceMetadata": [
        #    Prefetch("harvested_service_metadata",
        #             queryset=HarvestedServiceMetadataRelation.objects.select_related(
        #                 'harvesting_job', 'service_metadata_record', )
        #             )
        # ] + DEFAULT_HARVESTED_SERVICE_METADATA_PREFETCHES,
    }
    prefetch_for_not_includes = {
        # "temporaryMdMetadataFiles": [
        #     Prefetch(
        #         "temporary_md_metadata_files",
        #         queryset=TemporaryMdMetadataFile.objects.only(
        #             "id",
        #             "job_id",
        #         ),
        #     )
        # ],
        # "harvestedDatasetMetadata,newDatasetMetadataCount,updatedDatasetMetadataCount,existingDatasetMetadataCount,duplicatedDatasetMetadataCount": [
        #    Prefetch(
        #        "harvested_dataset_metadata",
        #        queryset=HarvestedDatasetMetadataRelation.objects.only(
        #            "id"),
        #    ), *DEFAULT_HARVESTED_DATASET_METADATA_PREFETCHES
        # ],
        # "harvestedServiceMetadata,newServiceMetadataCount,updatedServiceMetadataCount,existingServiceMetadataCount,duplicatedServiceMetadataCount": [
        #     Prefetch(
        #         "harvested_service_metadata",
        #         queryset=HarvestedServiceMetadataRelation.objects.only(
        #             "id")
        #     ), *DEFAULT_HARVESTED_SERVICE_METADATA_PREFETCHES
        # ],
    }

    def _get_cte_annotation_kwargs(self, for_dataset=True):
        cte_annotation = {}
        relation_filter_kwargs = {}
        if for_dataset:
            string = 'Dataset'
            relation_filter_kwargs.update({
                "dataset_metadata_record__isnull": False
            })
        else:
            string = 'Service'
            relation_filter_kwargs.update({
                "service_metadata_record__isnull": False
            })
        if self.check_sparse_fields_contains(f"new{string}MetadataCount"):
            cte_annotation.update({
                f"new_{string.lower()}_metadata_count": Count("id", filter=Q(collecting_state=CollectingStatenEnum.NEW.value, **relation_filter_kwargs))
            })
        if self.check_sparse_fields_contains(f"updated{string}MetadataCount"):
            cte_annotation.update({
                f"updated_{string.lower()}_metadata_count": Count("id", filter=Q(collecting_state=CollectingStatenEnum.UPDATED.value, **relation_filter_kwargs))
            })
        if self.check_sparse_fields_contains(f"existing{string}MetadataCount"):
            cte_annotation.update({
                f"existing_{string.lower()}_metadata_count": Count("id", filter=Q(collecting_state=CollectingStatenEnum.EXISTING.value, **relation_filter_kwargs))
            })
        if self.check_sparse_fields_contains(f"duplicated{string}MetadataCount"):
            cte_annotation.update({
                f"duplicated_{string.lower()}_metadata_count": Count("id", filter=Q(collecting_state=CollectingStatenEnum.DUPLICATED.value, **relation_filter_kwargs))
            })

        return cte_annotation

    def _prepare_qs_for_harvesting_stats(self, qs, sums):
        if self.check_sparse_fields_contains("fetchRecordDuration"):
            qs = qs.annotate(
                fetch_record_duration=sums.col.fetch_record_duration)
        if self.check_sparse_fields_contains("mdMetadataFileToDbDuration"):
            qs = qs.annotate(
                md_metadata_file_to_db_duration=sums.col.md_metadata_file_to_db_duration)
        if self.check_sparse_fields_contains("newDatasetMetadataCount"):
            qs = qs.annotate(
                new_dataset_metadata_count=Coalesce(sums.col.new_dataset_metadata_count, 0))
        if self.check_sparse_fields_contains("updatedDatasetMetadataCount"):
            qs = qs.annotate(
                updated_dataset_metadata_count=Coalesce(sums.col.updated_dataset_metadata_count, 0))
        if self.check_sparse_fields_contains("existingDatasetMetadataCount"):
            qs = qs.annotate(
                existing_dataset_metadata_count=Coalesce(sums.col.existing_dataset_metadata_count, 0))
        if self.check_sparse_fields_contains("duplicatedDatasetMetadataCount"):
            qs = qs.annotate(
                duplicated_dataset_metadata_count=Coalesce(sums.col.duplicated_dataset_metadata_count, 0))
        if self.check_sparse_fields_contains("newServiceMetadataCount"):
            qs = qs.annotate(
                new_service_metadata_count=Coalesce(sums.col.new_service_metadata_count, 0))
        if self.check_sparse_fields_contains("updatedServiceMetadataCount"):
            qs = qs.annotate(
                updated_service_metadata_count=Coalesce(sums.col.updated_service_metadata_count, 0))
        if self.check_sparse_fields_contains("existingServiceMetadataCount"):
            qs = qs.annotate(
                existing_service_metadata_count=Coalesce(sums.col.existing_service_metadata_count, 0))
        if self.check_sparse_fields_contains("duplicatedServiceMetadataCount"):
            qs = qs.annotate(
                duplicated_service_metadata_count=Coalesce(sums.col.duplicated_service_metadata_count, 0))
        if self.check_sparse_fields_contains("recordsPerMinute"):
            qs = qs.annotate(
                harvested_records=Coalesce(sums.col.harvested_records, 0),
                measured_seconds=Coalesce(sums.col.measured_seconds, 0.0),
            ).annotate(
                # Only a run which completed measured a harvest as a whole: the sums of a run which
                # stopped half way, or broke, name the work it happened to do, not what a harvest of
                # the catalogue takes. And a run whose records carry no durations measured nothing,
                # so it answers nothing - an invented number must not be mistaken for a measured one
                # (#692).
                records_per_minute=Case(
                    When(
                        phase=HarvestingPhaseEnum.COMPLETED,
                        done_at__isnull=False,
                        measured_seconds__gt=0,
                        then=ExpressionWrapper(
                            F("harvested_records") * 60.0 / F("measured_seconds"),
                            output_field=FloatField())),
                    default=None,
                    output_field=FloatField()))

        return qs

    def _statistics_range(self):
        """The runs whose records the statistics aggregate.

        The ``sums`` CTE aggregates the whole table of the harvested metadata
        relations and is joined ``LEFT OUTER``, which answers one row per job
        anyway (#885). A request whose url names one run can only answer that run,
        so the aggregation is bounded to the records of this very run: they are
        read out of the index over the rows of a job instead of as the whole table
        - which is the table the import of a big run is writing into while its
        diagnostics are polled every few seconds (#1071, cf. #1037).
        """
        pk = getattr(self, "kwargs", {}).get("pk")
        return Q(harvesting_job_id=pk) if str(pk or "").isdigit() else Q()

    def with_harvesting_stats(self, qs):
        dataset_cte_annotation = self._get_cte_annotation_kwargs(True)
        service_cte_annotation = self._get_cte_annotation_kwargs(False)
        cte_annotation = {}
        if self.check_sparse_fields_contains("fetchRecordDuration"):
            cte_annotation.update({
                "fetch_record_duration": Coalesce(Sum('download_duration'), timedelta(seconds=0), output_field=DurationField()),
            })
        if self.check_sparse_fields_contains("mdMetadataFileToDbDuration"):
            cte_annotation.update({
                "md_metadata_file_to_db_duration": Coalesce(Sum('processing_duration'), timedelta(seconds=0), output_field=DurationField())
            })
        if self.check_sparse_fields_contains("recordsPerMinute"):
            # the throughput of a run are the records it stored against the time their
            # download and their way into the database measured. Both are summed right here
            # already, so the number costs no second aggregation of the harvested records (#692).
            # The records which a completed snapshot only bookkeeps as removed are not among the
            # ones a run fetched and carry no duration either.
            cte_annotation.update({
                "harvested_records": Count(
                    'id',
                    filter=~Q(collecting_state=CollectingStatenEnum.REMOVED.value)),
                "measured_seconds": DurationSeconds(
                    Coalesce(Sum('download_duration'), timedelta(seconds=0), output_field=DurationField())
                    + Coalesce(Sum('processing_duration'), timedelta(seconds=0), output_field=DurationField())
                ),
            })
        sums = None
        if dataset_cte_annotation or service_cte_annotation or cte_annotation:
            sums = CTE(
                queryset=HarvestedMetadataRelation.objects.filter(
                    self._statistics_range()).values('harvesting_job_id').annotate(
                    **dataset_cte_annotation, **service_cte_annotation, **cte_annotation),
                name="sums"
            )

            qs = with_cte(
                sums,
                select=sums.join(model_or_queryset=qs,
                                 id=sums.col.harvesting_job_id,
                                 _join_type=LOUTER)
            )
            qs = self._prepare_qs_for_harvesting_stats(qs, sums)

        return qs

    def _progress_answers_asked(self):
        """The answers of ``RUN_PROGRESS_FIELDS`` which this request reads.

        The sparse fieldset names the answers a screen renders. A ``sort`` names
        the answer the list is ordered by, and that one is read as much as a
        column is: the offer of #1130 orders the runs of a catalogue by their
        progress whether or not the screen shows a number of it, and an answer
        which was not annotated is nothing to order by. The alerts list reads the
        annotations of a request the very same way (`querys/alerts.py`).
        """
        asked = {
            field for field in RUN_PROGRESS_FIELDS
            if self.check_sparse_fields_contains(field)}
        terms = {term.strip().lstrip("-")
                 for term in self.request.GET.get("sort", "").split(",")}
        # a client names an answer as the api names it, while the ordering is
        # answered as the database names it - a term may arrive either way
        asked |= {
            field for field in RUN_PROGRESS_FIELDS
            if field in terms or to_snake(field) in terms}
        return asked

    def with_unhandled_records(self, qs):
        """Answer what a run reports about its own work.

        The steps, the progress and the measurements of a run are annotations, so
        the request decides which of them are answered: a screen which shows no
        throughput pays for no aggregation of the records (#692) and a screen
        which shows no measurement pays for no measurement (#1071). What a client
        asks the list to be ordered by belongs to that decision as much as what it
        asks to see - an offered sort whose annotation was left out would answer
        one request in the order it asked for and the next with an error (#1130).
        The annotations themselves live with the aggregate
        (`HarvestingJobManager.with_run_progress`), because the websocket payload
        of a run is built from the very same numbers: a field which was only
        annotated here would answer once and empty with the first push.
        """
        return HarvestingJob.objects.with_run_progress(
            qs, answer=self._progress_answers_asked())

    def get_queryset(self, *args, **kwargs):
        qs = super().get_queryset(*args, **kwargs)
        qs = self.with_harvesting_stats(qs)
        qs = self.with_unhandled_records(qs)
        return qs

    def filter_queryset_without_ordering(self, queryset):
        """Apply the filters of the request and leave out the order it asked for.

        ``filter_queryset`` has to be given a queryset which carries the annotations
        the sort names - an answer which cannot resolve its own order raises a
        ``FieldError``. For the number of rows that requirement is a cost without a
        benefit: the order of the rows changes nothing about how many they are, and
        the answers of a run are read from the files it left behind, which the
        overview of a deployment must not read a second time only to be told how many
        runs it lists (#870, #1130).

        The backends are asked in the order they are configured, exactly as
        ``GenericAPIView.filter_queryset`` does; only the ordering is left out. The
        page itself is still filtered with it, so an order which is not offered is
        still answered with a bad request.
        """
        for backend in self.filter_backends:
            if issubclass(backend, OrderingFilter):
                continue
            queryset = backend().filter_queryset(self.request, queryset, self)
        return queryset

    def paginate_queryset(self, queryset, *args, **kwargs):
        """Count the jobs of the answer without the statistics of a job.

        ``with_harvesting_stats`` bounds the ``sums`` CTE, which aggregates the whole
        table of the harvested metadata relations into one aggregate row per job, and
        joins it ``LEFT OUTER``: the join answers exactly as many rows as the job
        table does, so the number of rows of the answer belongs to the job table. The
        paginator does not know that and asks the annotated queryset for its
        ``COUNT``, which materializes that aggregation a second time - the whole table
        of the harvested metadata relations twice for one overview of a deployment
        which has harvested (#885).

        The number is therefore read from the rows before the statistics: the filters
        of the request are applied to the queryset without them, which is the same
        answer without the annotations, and the page itself is still taken from the
        annotated queryset. The statistics cost one materialization per request.
        Without the order of the request: the progress of a run joins the sort offer
        of #1130 as an annotation, and the queryset before the statistics does not
        carry it, so ordering it by the terms of the request would answer such a
        request with an error instead of with a number of rows.
        """
        if getattr(queryset.query, '_with_ctes', None):
            queryset = queryset.with_cached_count(
                self.filter_queryset_without_ordering(
                    super().get_queryset()).count())
        return super().paginate_queryset(queryset, *args, **kwargs)


class HarvestingJobViewSet(
    HarvestingJobViewSetMixin,
    PreloadNotIncludesMixin,
    ModelViewSet
):
    pass


class NestedHarvestingJobViewSet(
    HarvestingJobViewSetMixin,
    PreloadNotIncludesMixin,
    NestedModelViewSet
):
    pass


class PeriodicHarvestingJobViewSetMixin:
    """ Endpoints for resource `PeriodicHarvestingJob`

        create:
            Endpoint to register new `PeriodicHarvestingJob` object
        list:
            Retrieves all registered `PeriodicHarvestingJob` objects
        retrieve:
            Retrieve one specific `PeriodicHarvestingJob` by the given id
        partial_update:
            Endpoint to update some fields of a `PeriodicHarvestingJob`
        destroy:
            Endpoint to remove a registered `PeriodicHarvestingJob` from the system
    """
    permission_classes = [DjangoObjectPermissionsOrAnonReadOnly]
    # the display string names the catalogue of the schedule, so the service
    # rides the select instead of one read per row (#1045)
    queryset = PeriodicHarvestingJob.objects.all().select_related("service")
    serializer_class = PeriodicHarvestingJobSerializer
    select_for_includes = {
        "service": ["service"],
    }
    filterset_fields = {
        'id': ['exact', 'icontains', 'contains', 'in'],
        'service__id': ['exact', 'icontains', 'contains', 'in'],
        'service__title': ['exact', 'icontains', 'contains'],
    }
    search_fields = ("id", "service", "service__title")
    # `name` is a uuid the system generates for the uniqueness of the celery
    # task, not a label an administrator orders schedules by; the readable
    # ordering of the schedules is by the catalogue they harvest (#1080)
    ordering_fields = ["id", "service"]


class PeriodicHarvestingJobViewSet(
    PeriodicHarvestingJobViewSetMixin,
    ModelViewSet
):
    pass


class NestedPeriodicHarvestingJobViewSet(
    PeriodicHarvestingJobViewSetMixin,
    NestedModelViewSet
):
    pass


class TemporaryMdMetadataFileViewSetMixin:
    queryset = TemporaryMdMetadataFile.objects.all()
    serializer_class = TemporaryMdMetadataFileSerializer
    permission_classes = [DjangoObjectPermissionsOrAnonReadOnly]
    ordering_fields = ["id", "request_id"]
    filterset_fields = {
        'id': ['exact', 'icontains', 'contains', 'in'],
        'job__id': ['exact', 'icontains', 'contains', 'in'],
        # the files of one catalogue: the run is only interesting through the
        # catalogue it belongs to, so the collection answers its service too (#1080)
        'job__service': ['exact', 'in'],
        'job__service__id': ['exact', 'in'],
        'has_import_error': ['exact'],
        'import_error': ['exact', 'icontains', 'contains', 'in', 'isnull'],
    }


class TemporaryMdMetadataFileViewSet(
    TemporaryMdMetadataFileViewSetMixin,
    ModelViewSet
):
    pass


class NestedTemporaryMdMetadataFileViewSet(
    TemporaryMdMetadataFileViewSetMixin,
    NestedModelViewSet
):
    pass


class HarvestedMetadataRelationViewSetMixin(PreloadNotIncludesMixin):
    queryset = HarvestedMetadataRelation.objects.all()
    serializer_class = HarvestedMetadataRelationSerializer
    permission_classes = [DjangoObjectPermissionsOrAnonReadOnly]
    ordering_fields = ["id", "history_date"]
    filterset_fields = {
        'id': ['exact', 'icontains', 'contains', 'in'],
        'harvesting_job__service': ['exact'],
        'collecting_state': ['exact', 'icontains', 'contains', 'in'],
        'harvesting_job__id': ['exact', 'icontains', 'contains', 'in'],
        "dataset_metadata_record": ["isnull"],
        "service_metadata_record": ["isnull"],
        "dataset_metadata_record__id": ['exact', 'icontains', 'contains', 'in'],
        "service_metadata_record__id": ['exact', 'icontains', 'contains', 'in'],
    }
    prefetch_for_not_includes = {
        "harvesting_job": ["harvesting_job"],
        "dataset_metadata_record": [
            Prefetch(
                "dataset_metadata_record",
                queryset=DatasetMetadataRecord.objects.only(
                    "id"
                ),
            )
        ],
        "service_metadata_record": [
            Prefetch(
                "service_metadata_record",
                queryset=ServiceMetadataRecord.objects.only(
                    "id"
                ),
            )
        ]
    }


class HarvestedMetadataRelationViewSet(
    HarvestedMetadataRelationViewSetMixin,
    ModelViewSet
):
    pass


class NestedHarvestedMetadataRelationViewSet(
    HarvestedMetadataRelationViewSetMixin,
    NestedModelViewSet
):
    pass


class HarvestingLogViewSetMixin(PreloadNotIncludesMixin):
    queryset = HarvestingLog.objects.all()
    serializer_class = HarvestingLogSerializer
    permission_classes = [DjangoObjectPermissionsOrAnonReadOnly]
    # every line really carries the time it was written, so the list answers
    # both directions of it and the run log reads in the order it happened (#1080)
    ordering_fields = ["id", "timestamp"]
    filterset_class = HarvestingLogFilterSet


class HarvestingLogViewSet(
    HarvestingLogViewSetMixin,
    ModelViewSet
):
    pass


class NestedHarvestingLogViewSet(
    HarvestingLogViewSetMixin,
    NestedModelViewSet
):
    pass
