from django.contrib.auth.models import Group
from django.db.models.query import Prefetch
from extras.openapi import CustomAutoSchema
from extras.viewsets import NestedModelViewSet
from registry.models.security import (AllowedWebFeatureServiceOperation,
                                      AllowedWebMapServiceOperation,
                                      WebFeatureServiceOperation,
                                      WebMapServiceOperation)
from registry.models.service import Layer, WebMapService
from registry.serializers.security import (
    AllowedWebFeatureServiceOperationSerializer,
    AllowedWebMapServiceOperationSerializer,
    WebFeatureServiceOperationSerializer, WebMapServiceOperationSerializer)
from rest_framework.permissions import DjangoObjectPermissions
from rest_framework_json_api.views import ModelViewSet, ReadOnlyModelViewSet


class WebMapServiceOperationViewSetMixin():
    schema = CustomAutoSchema(
        tags=["SecurableOperation"],
    )
    queryset = WebMapServiceOperation.objects.all()
    serializer_class = WebMapServiceOperationSerializer
    search_fields = ('operation', )


class WebMapServiceOperationViewSet(
    WebMapServiceOperationViewSetMixin,
    ReadOnlyModelViewSet
):
    pass


class NestedWebMapServiceOperationViewSet(
        WebMapServiceOperationViewSetMixin,
        NestedModelViewSet
):
    pass


class WebFeatureServiceOperationViewSetMixin():
    schema = CustomAutoSchema(
        tags=["SecurableOperation"],
    )
    queryset = WebFeatureServiceOperation.objects.all()
    serializer_class = WebFeatureServiceOperationSerializer
    search_fields = ('operation', )


class WebFeatureServiceOperationViewSet(
    WebFeatureServiceOperationViewSetMixin,
    ReadOnlyModelViewSet
):
    pass


class WebFeatureServiceOperationViewSet(
    WebFeatureServiceOperationViewSetMixin,
    NestedModelViewSet
):
    pass


class AllowedWebMapServiceOperationViewSetMixin():
    schema = CustomAutoSchema(
        tags=["AllowedOperation"],
    )
    queryset = AllowedWebMapServiceOperation.objects.all()
    serializer_class = AllowedWebMapServiceOperationSerializer
    permission_classes = [DjangoObjectPermissions]

    def get_queryset(self):
        qs = super().get_queryset()
        include = self.request.GET.get("include", None)

        if not include or "securedService" not in include:
            defer = [
                f"secured_service__{field.name}"
                for field in WebMapService._meta.get_fields()
                if field.name not in ["id", "pk"]
            ]
            qs = qs.select_related("secured_service").defer(*defer)
        if not include or "securedLayers" not in include:
            qs = qs.prefetch_related(
                Prefetch(
                    "secured_layers",
                    queryset=Layer.objects.only(
                        "id",
                        "service_id",
                        "tree_id",
                        "lft",
                    ),
                )
            )
        if not include or "allowedGroups" not in include:
            qs = qs.prefetch_related(
                Prefetch(
                    "allowed_groups",
                    queryset=Group.objects.only(
                        "id"
                    ),
                )
            )
        if not include or "operations" not in include:
            qs = qs.prefetch_related(
                Prefetch(
                    "operations",
                    queryset=WebMapServiceOperation.objects.only(
                        "operation",
                    ),
                )
            )

        return qs


class AllowedWebMapServiceOperationViewSet(
        AllowedWebMapServiceOperationViewSetMixin,
        ModelViewSet
):
    """ Endpoints for resource `AllowedWebMapServiceOperation`
        create:
            Endpoint to create new `AllowedWebMapServiceOperation` object
        list:
            Retrieves all `AllowedWebMapServiceOperation` objects
        retrieve:
            Retrieve one specific `AllowedWebMapServiceOperation` by the given id
        partial_update:
            Endpoint to update some fields of a `AllowedWebMapServiceOperation`

    """


class NestedAllowedWebMapServiceOperationViewSet(
        AllowedWebMapServiceOperationViewSetMixin,
        NestedModelViewSet
):
    """ Nested list endpoint for resource `AllowedWebMapServiceOperation`

        list:
            Retrieves all `AllowedWebMapServiceOperation` objects

    """


class AllowedWebFeatureServiceOperationViewSetMixin():
    schema = CustomAutoSchema(
        tags=["AllowedOperation"],
    )
    queryset = AllowedWebFeatureServiceOperation.objects.all()
    serializer_class = AllowedWebFeatureServiceOperationSerializer
    permission_classes = [DjangoObjectPermissions]


class AllowedWebFeatureServiceOperationViewSet(
        AllowedWebFeatureServiceOperationViewSetMixin,
        ModelViewSet
):
    """ Endpoints for resource `AllowedWebFeatureServiceOperation`
        create:
            Endpoint to create new `AllowedWebFeatureServiceOperation` object
        list:
            Retrieves all `AllowedWebFeatureServiceOperation` objects
        retrieve:
            Retrieve one specific `AllowedWebFeatureServiceOperation` by the given id
        partial_update:
            Endpoint to update some fields of a `AllowedWebFeatureServiceOperation`

    """


class NestedAllowedWebFeatureServiceOperationViewSet(
        AllowedWebFeatureServiceOperationViewSetMixin,
        NestedModelViewSet
):
    """ Nested list endpoint for resource `AllowedWebFeatureServiceOperation`

        list:
            Retrieves all `AllowedWebFeatureServiceOperation` objects

    """
