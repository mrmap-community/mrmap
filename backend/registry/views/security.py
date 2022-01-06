from extras.viewsets import ObjectPermissionCheckerViewSetMixin
from registry.models.security import AllowedWebMapServiceOperation
from registry.serializers.security import \
    AllowedWebMapServiceOperationSerializer
from rest_framework.permissions import DjangoObjectPermissions
from rest_framework_extensions.mixins import NestedViewSetMixin
from rest_framework_json_api.schemas.openapi import AutoSchema
from rest_framework_json_api.views import ModelViewSet


class AllowedWebMapServiceOperationViewSet(ObjectPermissionCheckerViewSetMixin, NestedViewSetMixin, ModelViewSet):
    schema = AutoSchema(
        tags=["SecurityProxy"],
    )
    queryset = AllowedWebMapServiceOperation.objects.all()
    serializer_class = AllowedWebMapServiceOperationSerializer
    permission_classes = [DjangoObjectPermissions]
