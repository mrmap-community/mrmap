
from django.db.models import Prefetch
from extras.permissions import DjangoObjectPermissionsOrAnonReadOnly
from extras.viewsets import NestedModelViewSet
from notify.models import BackgroundProcess, BackgroundProcessLog
from registry.models.harvest import (HarvestedDatasetMetadataRelation,
                                     HarvestedServiceMetadataRelation,
                                     HarvestingJob, TemporaryMdMetadataFile)
from registry.serializers.harvesting import (
    HarvestedDatasetMetadataRelationSerializer,
    HarvestedServiceMetadataRelationSerializer, HarvestingJobSerializer,
    TemporaryMdMetadataFileSerializer)
from rest_framework_json_api.views import ModelViewSet


class HarvestingJobViewSetMixin():
    queryset = HarvestingJob.objects.all()
    serializer_class = HarvestingJobSerializer
    permission_classes = [DjangoObjectPermissionsOrAnonReadOnly]
    ordering_fields = ["id"]
    filterset_fields = {
        'id': ['exact', 'icontains', 'contains', 'in'],
        'service__id': ['exact', 'icontains', 'contains', 'in'],
    }
    select_for_includes = {
        "service": ["service"],

    }
    prefetch_for_includes = {
        "__all__": [],
        "backgroundProcess": [Prefetch("background_process", queryset=BackgroundProcess.objects.process_info())],
        "backgroundProcess.logs": [Prefetch('background_process__logs', queryset=BackgroundProcessLog.objects.select_related('background_process'))],
        "temporaryMdMetadataFiles": [Prefetch('temporary_md_metadata_files', queryset=TemporaryMdMetadataFile.objects.select_related('job'))],
        "harvestedDatasetMetadata": [Prefetch("harvested_dataset_metadata", queryset=HarvestedDatasetMetadataRelation.objects.all())],
        "harvestedServiceMetadata": [Prefetch("harvested_service_metadata", queryset=HarvestedServiceMetadataRelation.objects.all())],
    }


class HarvestingJobViewSet(
    HarvestingJobViewSetMixin,
    ModelViewSet
):
    pass


class NestedHarvestingJobViewSet(
    HarvestingJobViewSetMixin,
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
        'harvesting_job': ['exact', 'icontains', 'contains', 'in', 'isnull'],
        "dataset_metadata_record": ['exact', 'icontains', 'contains', 'in', 'isnull'],
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
        'harvesting_job': ['exact', 'icontains', 'contains', 'in', 'isnull'],
        "service_metadata_record": ['exact', 'icontains', 'contains', 'in', 'isnull'],
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
