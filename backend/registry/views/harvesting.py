
from extras.permissions import DjangoObjectPermissionsOrAnonReadOnly
from extras.viewsets import ObjectPermissionCheckerViewSetMixin
from registry.models.harvest import HarvestingJob
from registry.serializers.harvesting import HarvestingJobSerializer
from rest_framework_extensions.mixins import NestedViewSetMixin
from rest_framework_json_api.schemas.openapi import AutoSchema
from rest_framework_json_api.views import ModelViewSet


class HarvestingJobViewSet(
    ObjectPermissionCheckerViewSetMixin,
    NestedViewSetMixin,
    ModelViewSet,
):
    schema = AutoSchema(
        tags=["Harvesting"],
    )
    queryset = HarvestingJob.objects.all()
    serializer_class = HarvestingJobSerializer
    permission_classes = [DjangoObjectPermissionsOrAnonReadOnly]
