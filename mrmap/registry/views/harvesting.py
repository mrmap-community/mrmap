
from extras.permissions import DjangoObjectPermissionsOrAnonReadOnly
from extras.viewsets import NestedModelViewSet
from registry.models.harvest import HarvestingJob
from registry.serializers.harvesting import HarvestingJobSerializer
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
