from extras.viewsets import ObjectPermissionCheckerViewSetMixin
from registry.models.security import (AllowedWebFeatureServiceOperation,
                                      AllowedWebMapServiceOperation)
from registry.serializers.security import (
    AllowedWebFeatureServiceOperationSerializer,
    AllowedWebMapServiceOperationSerializer)
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


class AllowedWebFeatureServiceOperationViewSet(ObjectPermissionCheckerViewSetMixin, NestedViewSetMixin, ModelViewSet):
    schema = AutoSchema(
        tags=["SecurityProxy"],
    )
    queryset = AllowedWebFeatureServiceOperation.objects.all()
    serializer_class = AllowedWebFeatureServiceOperationSerializer
    permission_classes = [DjangoObjectPermissions]
