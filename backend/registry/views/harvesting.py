
from camel_converter import to_camel
from django.db.models import F, Prefetch, Q, Sum
from django_celery_results.models import TaskResult
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
             queryset=BackgroundProcess.objects.process_info().prefetch_related(
                 Prefetch(
                     "threads",
                     queryset=TaskResult.objects.only(
                         "id"
                     )
                 ),
                 Prefetch(
                     "logs",
                     queryset=BackgroundProcessLog.objects.all()
                 ),
             )
             ),
]


class HarvestingJobViewSetMixin():
    queryset = HarvestingJob.objects.with_process_info()
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
        "backgroundProcess.logs": [
            Prefetch("background_process",
                     queryset=BackgroundProcess.objects.process_info().prefetch_related(
                         Prefetch(
                             "threads",
                             queryset=TaskResult.objects.only(
                                 "id"
                             )
                         ),
                         Prefetch(
                             "logs",
                             queryset=BackgroundProcessLog.objects.all()
                         ),
                     )
                     ),
        ],
        "temporaryMdMetadataFiles": [
            Prefetch('temporary_md_metadata_files',
                     queryset=TemporaryMdMetadataFile.objects.select_related('job'))
        ],
        "harvestedDatasetMetadata": [
            Prefetch("harvested_dataset_metadata",
                     queryset=HarvestedDatasetMetadataRelation.objects.select_related(
                         'harvesting_job', 'dataset_metadata_record', )
                     )
        ] + DEFAULT_HARVESTED_DATASET_METADATA_PREFETCHES,
        "harvestedServiceMetadata": [
            Prefetch("harvested_service_metadata",
                     queryset=HarvestedServiceMetadataRelation.objects.select_related(
                         'harvesting_job', 'service_metadata_record', )
                     )
        ] + DEFAULT_HARVESTED_SERVICE_METADATA_PREFETCHES,
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
        #     Prefetch(
        #         "harvested_dataset_metadata",
        #         queryset=HarvestedDatasetMetadataRelation.objects.only(
        #             "id"),
        #     ), *DEFAULT_HARVESTED_DATASET_METADATA_PREFETCHES
        # ],
        # "harvestedServiceMetadata,newServiceMetadataCount,updatedServiceMetadataCount,existingServiceMetadataCount,duplicatedServiceMetadataCount": [
        #     Prefetch(
        #         "harvested_service_metadata",
        #         queryset=HarvestedServiceMetadataRelation.objects.only(
        #             "id")
        #     ), *DEFAULT_HARVESTED_SERVICE_METADATA_PREFETCHES
        # ],
    }

    # def get_queryset(self, *args, **kwargs):
    #     qs = super().get_queryset(*args, **kwargs)
    #     fields_snake = self.request.GET.get(
    #         "fields[HarvestingJob]", "").split(',')
    #     fields = [to_camel(field) for field in fields_snake if field.strip()]

    #     if not fields or "fetchRecordDuration" in fields:
    #         qs = qs.annotate(
    #             fetch_record_duration=Sum(
    #                 F('background_process__threads__date_done') -
    #                 F('background_process__threads__date_created'),
    #                 filter=Q(background_process__threads__task_name='registry.tasks.harvest.call_fetch_records')),
    #         )
    #     if not fields or "mdMetadataFileToDbDuration" in fields:
    #         qs = qs.annotate(
    #             md_metadata_file_to_db_duration=Sum(
    #                 F('background_process__threads__date_done') -
    #                 F('background_process__threads__date_created'),
    #                 filter=Q(background_process__threads__task_name='registry.tasks.harvest.call_md_metadata_file_to_db')),
    #         )
    #     return qs


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
