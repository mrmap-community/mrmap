
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
from extras.viewsets import NestedModelViewSet, PreloadNotIncludesMixin
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
from rest_framework_json_api.views import ModelViewSet

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


class HarvestingJobViewSetMixin():
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

    def initial(self, *args, **kwargs):
        fields_snake = self.request.GET.get(
            "fields[HarvestingJob]", "").split(',')
        self.sparse_fields = {
            self.queryset.model.__name__: [
                to_camel(field) for field in fields_snake if field.strip()]
        }
        super().initial(*args, **kwargs)

    def get_sparse_fields(self, resource):
        return self.sparse_fields.get(resource, [])

    def with_harvesting_stats(self, qs):
        fields = self.get_sparse_fields(self.queryset.model.__name__)
        fetch_record_duration_needed = not fields or "fetchRecordDuration" in fields
        md_metadata_file_to_db_duration_needed = not fields or "mdMetadataFileToDbDuration" in fields

        cte_annotation = {}
        if fetch_record_duration_needed:
            cte_annotation.update({
                "fetch_record_duration": Coalesce(Sum('download_duration'), timedelta(seconds=0), output_field=DurationField())
            })
        if md_metadata_file_to_db_duration_needed:
            cte_annotation.update({
                "md_metadata_file_to_db_duration": Coalesce(Sum('processing_duration'), timedelta(seconds=0), output_field=DurationField())
            })

        """
        example to use without django-cte package:
        
        
        dataset_sums = HarvestedDatasetMetadataRelation.objects.filter(
            harvesting_job_id=OuterRef('id')
        ).values('harvesting_job_id').annotate(
            fetch_record_duration=Coalesce(Sum('download_duration'), timedelta(
                seconds=0), output_field=DurationField()),
            md_metadata_file_to_db_duration=Coalesce(
                Sum('processing_duration'), timedelta(seconds=0), output_field=DurationField())
        )

        # Subquery für die Aggregation der service_sums
        service_sums = HarvestedServiceMetadataRelation.objects.filter(
            harvesting_job_id=OuterRef('id')
        ).values('harvesting_job_id').annotate(
            fetch_record_duration=Coalesce(Sum('download_duration'), timedelta(
                seconds=0), output_field=DurationField()),
            md_metadata_file_to_db_duration=Coalesce(
                Sum('processing_duration'), timedelta(seconds=0), output_field=DurationField())
        )

        qs = qs.annotate(
            dataset_fetch_record_duration=Subquery(dataset_sums.values(
                'fetch_record_duration')[:1], output_field=DurationField()),
            dataset_md_metadata_file_to_db_duration=Subquery(dataset_sums.values(
                'md_metadata_file_to_db_duration')[:1], output_field=DurationField()),
            service_fetch_record_duration=Subquery(service_sums.values(
                'fetch_record_duration')[:1], output_field=DurationField()),
            service_md_metadata_file_to_db_duration=Subquery(service_sums.values(
                'md_metadata_file_to_db_duration')[:1], output_field=DurationField())
        ).annotate(
            fetch_record_duration=F('dataset_fetch_record_duration') +
            F('service_fetch_record_duration'),
            md_metadata_file_to_db_duration=F(
                'dataset_md_metadata_file_to_db_duration') + F('service_md_metadata_file_to_db_duration')
        )"""

        if cte_annotation:
            dataset_sums = With(
                queryset=HarvestedDatasetMetadataRelation.objects.values(
                    'harvesting_job_id').annotate(**cte_annotation),
                name="dataset_sums"
            )

            service_sums = With(
                queryset=HarvestedServiceMetadataRelation.objects.values(
                    'harvesting_job_id').annotate(**cte_annotation),
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

            if fetch_record_duration_needed:
                qs = qs.annotate(
                    fetch_record_duration=dataset_sums.col.fetch_record_duration + service_sums.col.fetch_record_duration)
            if md_metadata_file_to_db_duration_needed:
                qs = qs.annotate(md_metadata_file_to_db_duration=dataset_sums.col.md_metadata_file_to_db_duration +
                                 service_sums.col.md_metadata_file_to_db_duration)
        return qs

    def with_process_info(self, qs):
        fields = self.get_sparse_fields(self.queryset.model.__name__)
        progress_needed = not fields or "progress" in fields
        total_steps_needed = (
            not fields or "totalSteps" in fields) or progress_needed
        done_steps_needed = (
            not fields or "doneSteps" in fields) or progress_needed
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
                            background_process__phase__icontains="Harvesting is running..."),
                        then=1 + Ceil(F("unhandled_records_count") /
                                      F("max_step_size"))
                    ),
                    When(
                        condition=Q(
                            background_process__phase__icontains="parse and store ISO Metadatarecords to db..."),
                        then=1 + F("download_tasks_count") +
                        F("total_records") -
                        F("unhandled_records_count")
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
                            then=Round(F("done_steps") * 1.0 / F("total_steps") * 100.0, precission=4),  # noqa
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
