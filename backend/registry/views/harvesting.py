
from datetime import timedelta

from camel_converter import to_camel
from django.db.models import (Case, Count, F, OuterRef, Prefetch, Q, Subquery,
                              Sum, Value, When)
from django.db.models.expressions import RawSQL
from django.db.models.fields import DurationField, FloatField
from django.db.models.functions import Ceil, Coalesce, Round
from django.db.models.sql.constants import LOUTER
from django_celery_results.models import TaskResult
from django_cte import With
from extras.permissions import DjangoObjectPermissionsOrAnonReadOnly
from extras.viewsets import (NestedModelViewSet, PreloadNotIncludesMixin,
                             SparseFieldMixin)
from notify.models import BackgroundProcess, BackgroundProcessLog
from registry.enums.harvesting import CollectingStatenEnum
from registry.filters.harvesting import HarvestingJobFilterSet
from registry.models.harvest import (HarvestedDatasetMetadataRelation,
                                     HarvestedServiceMetadataRelation,
                                     HarvestingJob, TemporaryMdMetadataFile)
from registry.models.metadata import Keyword
from registry.models.service import CatalogueServiceOperationUrl
from registry.serializers.harvesting import (
    HarvestedDatasetMetadataRelationSerializer,
    HarvestedServiceMetadataRelationSerializer, HarvestingJobSerializer,
    TemporaryMdMetadataFileSerializer)
from rest_framework_json_api.views import ModelViewSet, ReadOnlyModelViewSet

DEFAULT_HARVESTED_DATASET_METADATA_PREFETCHES = [
    Prefetch(
        "harvested_dataset_metadata",
        queryset=HarvestedDatasetMetadataRelation.objects.filter(
            collecting_state=CollectingStatenEnum.NEW.value).only("id"),
        to_attr="new_dataset_metadata"
    ),
    Prefetch(
        "harvested_dataset_metadata",
        queryset=HarvestedDatasetMetadataRelation.objects.filter(
            collecting_state=CollectingStatenEnum.UPDATED.value).only("id"),
        to_attr="updated_dataset_metadata"
    ),
    Prefetch(
        "harvested_dataset_metadata",
        queryset=HarvestedDatasetMetadataRelation.objects.filter(
            collecting_state=CollectingStatenEnum.EXISTING.value).only("id"),
        to_attr="existing_dataset_metadata"
    ),
    Prefetch(
        "harvested_dataset_metadata",
        queryset=HarvestedDatasetMetadataRelation.objects.filter(
            collecting_state=CollectingStatenEnum.DUPLICATED.value).only("id"),
        to_attr="duplicated_dataset_metadata"
    )
]

DEFAULT_HARVESTED_SERVICE_METADATA_PREFETCHES = [
    Prefetch(
        "harvested_service_metadata",
        queryset=HarvestedServiceMetadataRelation.objects.filter(
            collecting_state=CollectingStatenEnum.NEW.value).only("id"),
        to_attr="new_service_metadata"
    ),
    Prefetch(
        "harvested_service_metadata",
        queryset=HarvestedServiceMetadataRelation.objects.filter(
            collecting_state=CollectingStatenEnum.UPDATED.value).only("id"),
        to_attr="updated_service_metadata"
    ),
    Prefetch(
        "harvested_service_metadata",
        queryset=HarvestedServiceMetadataRelation.objects.filter(
            collecting_state=CollectingStatenEnum.EXISTING.value).only("id"),
        to_attr="existing_service_metadata"
    ),
    Prefetch(
        "harvested_service_metadata",
        queryset=HarvestedServiceMetadataRelation.objects.filter(
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


class HarvestingJobViewSetMixin(SparseFieldMixin):
    queryset = HarvestingJob.objects.all()
    serializer_class = HarvestingJobSerializer
    permission_classes = [DjangoObjectPermissionsOrAnonReadOnly]
    ordering_fields = ["id", 'background_process__date_created']
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
        "backgroundProcess": BACKGROUND_PROCESS_PREFETCHES,
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
        string = 'Dataset' if for_dataset else 'Service'
        if self.check_sparse_fields_contains(f"new{string}MetadataCount"):
            cte_annotation.update({
                f"new_{string.lower()}_metadata_count": Count("id", filter=Q(collecting_state=CollectingStatenEnum.NEW.value))
            })
        if self.check_sparse_fields_contains(f"updated{string}MetadataCount"):
            cte_annotation.update({
                f"updated_{string.lower()}_metadata_count": Count("id", filter=Q(collecting_state=CollectingStatenEnum.UPDATED.value))
            })
        if self.check_sparse_fields_contains(f"existing{string}MetadataCount"):
            cte_annotation.update({
                f"existing_{string.lower()}_metadata_count": Count("id", filter=Q(collecting_state=CollectingStatenEnum.EXISTING.value))
            })
        if self.check_sparse_fields_contains(f"duplicated{string}MetadataCount"):
            cte_annotation.update({
                f"duplicated_{string.lower()}_metadata_count": Count("id", filter=Q(collecting_state=CollectingStatenEnum.DUPLICATED.value))
            })

        if self.check_sparse_fields_contains("fetchRecordDuration"):
            cte_annotation.update({
                "fetch_record_duration": Coalesce(Sum('download_duration'), timedelta(seconds=0), output_field=DurationField()),
            })
        if self.check_sparse_fields_contains("mdMetadataFileToDbDuration"):
            cte_annotation.update({
                "md_metadata_file_to_db_duration": Coalesce(Sum('processing_duration'), timedelta(seconds=0), output_field=DurationField())
            })

        return cte_annotation

    def _prepare_qs_for_harvesting_stats(self, qs, dataset_sums, service_sums):
        if self.check_sparse_fields_contains("fetchRecordDuration"):
            qs = qs.annotate(fetch_record_duration=dataset_sums.col.fetch_record_duration +
                             service_sums.col.fetch_record_duration)
        if self.check_sparse_fields_contains("mdMetadataFileToDbDuration"):
            qs = qs.annotate(md_metadata_file_to_db_duration=dataset_sums.col.md_metadata_file_to_db_duration +
                             service_sums.col.md_metadata_file_to_db_duration)
        if self.check_sparse_fields_contains("newDatasetMetadataCount"):
            qs = qs.annotate(
                new_dataset_metadata_count=dataset_sums.col.new_dataset_metadata_count)
        if self.check_sparse_fields_contains("updatedDatasetMetadataCount"):
            qs = qs.annotate(
                updated_dataset_metadata_count=dataset_sums.col.updated_dataset_metadata_count)
        if self.check_sparse_fields_contains("existingDatasetMetadataCount"):
            qs = qs.annotate(
                existing_dataset_metadata_count=dataset_sums.col.existing_dataset_metadata_count)
        if self.check_sparse_fields_contains("duplicatedDatasetMetadataCount"):
            qs = qs.annotate(
                duplicated_dataset_metadata_count=dataset_sums.col.duplicated_dataset_metadata_count)
        if self.check_sparse_fields_contains("newServiceMetadataCount"):
            qs = qs.annotate(
                new_service_metadata_count=service_sums.col.new_service_metadata_count)
        if self.check_sparse_fields_contains("updatedServiceMetadataCount"):
            qs = qs.annotate(
                updated_service_metadata_count=service_sums.col.updated_service_metadata_count)
        if self.check_sparse_fields_contains("existingServiceMetadataCount"):
            qs = qs.annotate(
                existing_service_metadata_count=service_sums.col.existing_service_metadata_count)
        if self.check_sparse_fields_contains("duplicatedServiceMetadataCount"):
            qs = qs.annotate(
                duplicated_service_metadata_count=service_sums.col.duplicated_service_metadata_count)

        return qs

    def with_harvesting_stats(self, qs):
        dataset_cte_annotation = self._get_cte_annotation_kwargs(True)
        service_cte_annotation = self._get_cte_annotation_kwargs(False)
        dataset_sums = None
        service_sums = None
        if dataset_cte_annotation and service_cte_annotation:
            dataset_sums = With(
                queryset=HarvestedDatasetMetadataRelation.objects.values('harvesting_job_id').annotate(
                    **dataset_cte_annotation),
                name="dataset_sums"
            )
            service_sums = With(
                queryset=HarvestedServiceMetadataRelation.objects.values('harvesting_job_id').annotate(
                    **service_cte_annotation),
                name="service_sums"
            )

            qs = (
                dataset_sums.join(model_or_queryset=qs,
                                  id=dataset_sums.col.harvesting_job_id,
                                  _join_type=LOUTER)
                .with_cte(dataset_sums)
            )
            qs = (
                service_sums.join(model_or_queryset=qs,
                                  id=service_sums.col.harvesting_job_id,
                                  _join_type=LOUTER)
                .with_cte(service_sums)
            )
        elif dataset_cte_annotation:
            dataset_sums = With(
                queryset=HarvestedDatasetMetadataRelation.objects.values('harvesting_job_id').annotate(
                    **dataset_cte_annotation),
                name="dataset_sums"
            )
            qs = (
                dataset_sums.join(model_or_queryset=qs,
                                  id=dataset_sums.col.harvesting_job_id,
                                  _join_type=LOUTER)
                .with_cte(dataset_sums)
            )
        elif service_cte_annotation:
            service_sums = With(
                queryset=HarvestedServiceMetadataRelation.objects.values('harvesting_job_id').annotate(
                    **service_cte_annotation),
                name="service_sums"
            )
            qs = (
                service_sums.join(model_or_queryset=qs,
                                  id=service_sums.col.harvesting_job_id,
                                  _join_type=LOUTER)
                .with_cte(service_sums)
            )
        qs = self._prepare_qs_for_harvesting_stats(
            qs, dataset_sums, service_sums)

        return qs

    def with_process_info(self, qs):
        progress_needed = self.check_sparse_fields_contains("progress")
        total_steps_needed = self.check_sparse_fields_contains(
            "totalSteps") or progress_needed
        done_steps_needed = self.check_sparse_fields_contains(
            "doneSteps") or progress_needed
        download_tasks_count_needed = total_steps_needed or done_steps_needed

        annotate_kwargs = {}
        if download_tasks_count_needed:
            annotate_kwargs.update({
                "download_tasks_count": Ceil(F("total_records") / F("max_step_size")),
            })
        if total_steps_needed:
            annotate_kwargs.update({
                # + 1 for call_fetch_total_records
                "total_steps": F("download_tasks_count") + F("total_records") + 1
            })

        if done_steps_needed:
            annotate_kwargs.update({
                "unhandled_records_count": Count("temporary_md_metadata_file"),
                "done_steps": Case(
                    When(
                        condition=Q(
                            background_process__phase__icontains="completed"),
                        then=F("total_steps")
                    ),
                    When(
                        condition=Q(
                            background_process__phase__icontains="Harvesting is running..."),
                        then=1 + Ceil(F("unhandled_records_count") /
                                      F("max_step_size"))
                    ),
                    When(
                        condition=Q(
                            background_process__phase__icontains="parse and store ISO Metadatarecords to db..."),
                        then=1 + F("download_tasks_count") +
                        F("total_records") - F("unhandled_records_count")
                    ),
                    default=0
                ),
            })
        if progress_needed:
            annotate_kwargs.update({
                "progress": Case(
                    When(
                        ~Q(background_process__phase="abort") & Q(
                            background_process__done_at__isnull=False),
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

        qs = qs.annotate(**annotate_kwargs)

        return qs

    def get_queryset(self, *args, **kwargs):
        qs = super().get_queryset(*args, **kwargs)
        qs = self.with_harvesting_stats(qs)
        qs = self.with_process_info(qs)
        unhandled_records_cte = With(
            queryset=TemporaryMdMetadataFile.objects.values('job_id').annotate(
                import_error_count=Count(
                    "id", distinct=True, filter=~Q(import_error="")),
                unhandled_records_count=Count(
                    "id", distinct=True, filter=Q(import_error=""))
            ),
            name="unhandled_records_cte"
        )
        qs = (
            unhandled_records_cte.join(model_or_queryset=qs,
                                       id=unhandled_records_cte.col.job_id,
                                       _join_type=LOUTER)
            .with_cte(unhandled_records_cte)
        )
        qs = qs.annotate(
            import_error_count=Coalesce(
                unhandled_records_cte.col.import_error_count, 0),
            unhandled_records_count=Coalesce(
                unhandled_records_cte.col.unhandled_records_count, 0),
        )

        """
                qs = qs.annotate(
                    import_error_count=Count(
                        'temporary_md_metadata_file', filter=~Q(temporary_md_metadata_file__import_error='')),
                    unhandled_records_count=Count(
                        'temporary_md_metadata_file', filter=Q(temporary_md_metadata_file__import_error=''))
                )
        """
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


class TemporaryMdMetadataFileViewSetMixin():
    queryset = TemporaryMdMetadataFile.objects.all()
    serializer_class = TemporaryMdMetadataFileSerializer
    permission_classes = [DjangoObjectPermissionsOrAnonReadOnly]
    ordering_fields = ["id"]
    filterset_fields = {
        'id': ['exact', 'icontains', 'contains', 'in'],
        'job__id': ['exact', 'icontains', 'contains', 'in'],
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


class HarvestedDatasetMetadataRelationViewSetMixin():
    queryset = HarvestedDatasetMetadataRelation.objects.all()
    serializer_class = HarvestedDatasetMetadataRelationSerializer
    permission_classes = [DjangoObjectPermissionsOrAnonReadOnly]
    ordering_fields = ["id"]
    filterset_fields = {
        'id': ['exact', 'icontains', 'contains', 'in'],
        'collecting_state': ['exact', 'icontains', 'contains', 'in'],
        'harvesting_job__id': ['exact', 'icontains', 'contains', 'in'],
        "dataset_metadata_record__id": ['exact', 'icontains', 'contains', 'in'],
    }


class HarvestedDatasetMetadataRelationViewSet(
    HarvestedDatasetMetadataRelationViewSetMixin,
    ModelViewSet
):
    pass


class NestedHarvestedDatasetMetadataRelationViewSet(
    HarvestedDatasetMetadataRelationViewSetMixin,
    NestedModelViewSet
):
    pass


class HarvestedServiceMetadataRelationViewSetMixin():
    queryset = HarvestedServiceMetadataRelation.objects.all()
    serializer_class = HarvestedServiceMetadataRelationSerializer
    permission_classes = [DjangoObjectPermissionsOrAnonReadOnly]
    ordering_fields = ["id"]
    filterset_fields = {
        'id': ['exact', 'icontains', 'contains', 'in'],
        'collecting_state': ['exact', 'icontains', 'contains', 'in'],
        'harvesting_job__id': ['exact', 'icontains', 'contains', 'in'],
        "service_metadata_record__id": ['exact', 'icontains', 'contains', 'in'],
    }


class HarvestedServiceMetadataRelationViewSet(
    HarvestedServiceMetadataRelationViewSetMixin,
    ModelViewSet
):
    pass


class NestedHarvestedServiceMetadataRelationViewSet(
    HarvestedServiceMetadataRelationViewSetMixin,
    NestedModelViewSet
):
    pass
