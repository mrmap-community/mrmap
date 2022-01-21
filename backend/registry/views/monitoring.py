
from backend.registry.models.monitoring import WMSGetCapabilitiesResult
from extras.permissions import DjangoObjectPermissionsOrAnonReadOnly
from extras.viewsets import (AsyncCreateMixin,
                             ObjectPermissionCheckerViewSetMixin,
                             SerializerClassesMixin)
from registry.tasks.monitoring import check_wms_get_capabilities_operation
from rest_framework_extensions.mixins import NestedViewSetMixin
from rest_framework_json_api.schemas.openapi import AutoSchema
from rest_framework_json_api.views import ModelViewSet


class WebMapServiceMonitoringResultViewSet(
    AsyncCreateMixin,
    SerializerClassesMixin,
    ObjectPermissionCheckerViewSetMixin,
    NestedViewSetMixin,
    ModelViewSet,
):
    schema = AutoSchema(
        tags=["Monitoring"],
    )
    queryset = WMSGetCapabilitiesResult.objects.all()
    serializer_classes = {
        "default": None,  # TODO
        "create": None,  # TODO
    }
    permission_classes = [DjangoObjectPermissionsOrAnonReadOnly]
    task_function = check_wms_get_capabilities_operation

    def get_task_kwargs(self, request, serializer):
        return {
            "service_pk": serializer.data["service"].pk
        }
