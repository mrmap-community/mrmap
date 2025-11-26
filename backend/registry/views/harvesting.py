from datetime import timedelta

from camel_converter import to_snake
from django.db.models import Case, Count, F, Prefetch, Q, Sum, Value, When
from django.db.models.fields import DurationField, FloatField
from django.db.models.functions import Ceil, Coalesce, Round
from django.db.models.sql.constants import LOUTER
from django_cte import CTE, With, with_cte
from extras.permissions import DjangoObjectPermissionsOrAnonReadOnly
from extras.viewsets import (NestedModelViewSet, PreloadNotIncludesMixin,
                             SerializerClassesMixin, SparseFieldMixin)
from notify.models import BackgroundProcess
from registry.enums.harvesting import CollectingStatenEnum, HarvestingPhaseEnum
from registry.filters.harvesting import HarvestingJobFilterSet
from registry.models.harvest import (HarvestedMetadataRelation, HarvestingJob,
                                     HarvestingLog, PeriodicHarvestingJob,
                                     TemporaryMdMetadataFile)
from registry.models.metadata import (DatasetMetadataRecord, Keyword,
                                      ServiceMetadataRecord)
from registry.models.service import CatalogueServiceOperationUrl
from registry.serializers.harvesting import (
    CreateHarvestingJobSerializer, HarvestedMetadataRelationSerializer,
    HarvestingJobSerializer, HarvestingLogSerializer,
    PeriodicHarvestingJobSerializer, TemporaryMdMetadataFileSerializer)
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
    queryset = HarvestingJob.objects.all()
    serializer_class = HarvestingJobSerializer
    serializer_classes = {
        "default": HarvestingJobSerializer,
        "create": CreateHarvestingJobSerializer,
    }
    permission_classes = [DjangoObjectPermissionsOrAnonReadOnly]
    ordering_fields = ["id", 'date_created']
    filterset_class = HarvestingJobFilterSet

    select_for_includes = {
        # "service": ["service"],
        # "backgroundProcess": ["background_process"]
    }
    prefetch_for_includes = {
        "service": [
            Prefetch("service__keywords",
                     queryset=Keyword.objects.only("id")),
            Prefetch("service__harvesting_jobs",
                     queryset=HarvestingJob.objects.all()),
            Prefetch("service__operation_urls",
                     queryset=CatalogueServiceOperationUrl.objects.all()),
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

        return qs

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
        sums = None
        if dataset_cte_annotation or service_cte_annotation or cte_annotation:
            sums = CTE(
                queryset=HarvestedMetadataRelation.objects.values('harvesting_job_id').annotate(
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

    def with_unhandled_records(self, qs):
        import_error_count_needed = self.check_sparse_fields_contains(
            "importErrorCount")
        unhandled_records_count_needed = self.check_sparse_fields_contains(
            "unhandledRecordsCount")
        progress_needed = self.check_sparse_fields_contains("progress")
        total_steps_needed = self.check_sparse_fields_contains(
            "totalSteps") or progress_needed
        done_steps_needed = self.check_sparse_fields_contains(
            "doneSteps") or progress_needed
        download_tasks_count_needed = total_steps_needed or done_steps_needed

        cte_kwargs = {}
        qs_annotation_kwargs = {}
        if import_error_count_needed:
            cte_kwargs.update({
                "import_error_count": Count("id", filter=Q(has_import_error=True))
            })
        if unhandled_records_count_needed:
            cte_kwargs.update({
                "unhandled_records_count": Count("id", filter=Q(has_import_error=False))
            })
        if download_tasks_count_needed:
            qs_annotation_kwargs.update({
                "download_tasks_count": Ceil(F("total_records") / F("max_step_size")),
            })
        if total_steps_needed:
            qs_annotation_kwargs.update({
                # + 1 for call_fetch_total_records
                "total_steps": F("download_tasks_count") + F("total_records") + 1
            })
        if done_steps_needed:
            cte_kwargs.update({
                "records_count": Count("id")
            })

            qs_annotation_kwargs.update({
                "done_steps": Case(
                    When(
                        condition=Q(
                            phase__gte=HarvestingPhaseEnum.COMPLETED.value),
                        then=F("total_steps")
                    ),
                    When(
                        condition=Q(
                            phase=HarvestingPhaseEnum.DOWNLOAD_RECORDS.value),
                        then=1 + Ceil(F("records_count") /
                                      F("max_step_size"))
                    ),
                    When(
                        condition=Q(
                            phase=HarvestingPhaseEnum.RECORDS_TO_DB.value),
                        then=1 + F("download_tasks_count") +
                        F("total_records") -
                        F("records_count")
                    ),
                    default=0
                ),
            })
        if progress_needed:
            qs_annotation_kwargs.update({
                "progress": Case(
                    When(
                        ~Q(phase=HarvestingPhaseEnum.ABORTED.value) & Q(
                            done_at__isnull=False),
                        then=Value(100.0)
                    ),
                    default=Case(
                        # TODO: does not provide floatingfield
                        When(
                            total_steps__gt=0,
                            then=Round(
                                F("done_steps") * 1.0 /
                                F("total_steps") * 100.0,
                                precission=2,
                                output_field=FloatField()
                            ),
                        ),
                        default=0.0
                    ),
                    output_field=FloatField()
                )
            })

        qs = self.construct_cte(
            qs, cte_kwargs, TemporaryMdMetadataFile, "job_id", qs_annotation_kwargs)

        return qs

    def construct_cte(self, qs, cte_kwargs, model, join_key, qs_annotation_kwargs={}, join_type=LOUTER):
        if cte_kwargs:
            cte = CTE(
                queryset=model.objects.values(
                    'job_id').annotate(**cte_kwargs),
                name=f"{to_snake(model.__name__)}_cte"
            )
            qs = with_cte(
                cte,
                select=cte.join(model_or_queryset=qs,
                                id=getattr(cte.col, join_key),
                                _join_type=join_type)
            )
            qs = self.annotate_qs_by_cte_fields(qs, cte_kwargs, cte)
        if qs_annotation_kwargs:
            qs = qs.annotate(**qs_annotation_kwargs)
        return qs

    def annotate_qs_by_cte_fields(self, qs, cte_kwargs, cte):
        qs_kwargs = {}
        for key, value in cte_kwargs.items():
            qs_kwargs.update({
                # Coalesce with int value will not always be right here;
                # TODO: Check if the value is Count (int) for example, if not (string) then use empty string for example
                key: Coalesce(getattr(cte.col, key), 0)
            })
        qs = qs.annotate(**qs_kwargs)
        return qs

    def get_queryset(self, *args, **kwargs):
        qs = super().get_queryset(*args, **kwargs)
        qs = self.with_harvesting_stats(qs)
        qs = self.with_unhandled_records(qs)
        return qs


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
    queryset = PeriodicHarvestingJob.objects.all()
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
    ordering_fields = ["id", "name", "service"]


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


class TemporaryMdMetadataFileViewSetMixin():
    queryset = TemporaryMdMetadataFile.objects.all()
    serializer_class = TemporaryMdMetadataFileSerializer
    permission_classes = [DjangoObjectPermissionsOrAnonReadOnly]
    ordering_fields = ["id"]
    filterset_fields = {
        'id': ['exact', 'icontains', 'contains', 'in'],
        'job__id': ['exact', 'icontains', 'contains', 'in'],
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
    ordering_fields = ["id"]
    filterset_fields = {
        'id': ['exact', 'icontains', 'contains', 'in'],
        'collecting_state': ['exact', 'icontains', 'contains', 'in'],
        'harvesting_job__id': ['exact', 'icontains', 'contains', 'in'],
        "dataset_metadata_record": ["isnull"],
        "service_metadata_record": ["isnull"],
        "dataset_metadata_record__id": ['exact', 'icontains', 'contains', 'in'],
        "service_metadata_record__id": ['exact', 'icontains', 'contains', 'in'],
    }
    prefetch_for_not_includes = {
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
    ordering_fields = ["id"]
    filterset_fields = {
        'id': ['exact', 'icontains', 'contains', 'in'],
    }


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
