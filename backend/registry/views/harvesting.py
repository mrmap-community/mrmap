
from extras.openapi import CustomAutoSchema
from extras.permissions import DjangoObjectPermissionsOrAnonReadOnly
from extras.viewsets import NestedModelViewSet
from registry.models.harvest import HarvestingJob
from registry.serializers.harvesting import HarvestingJobSerializer
from rest_framework_json_api.views import ModelViewSet


class HarvestingJobViewSetMixin():
    schema = CustomAutoSchema(
        tags=["Harvesting"],
    )
    queryset = HarvestingJob.objects.all()
    serializer_class = HarvestingJobSerializer
    permission_classes = [DjangoObjectPermissionsOrAnonReadOnly]


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
