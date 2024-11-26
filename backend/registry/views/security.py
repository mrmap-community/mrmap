from django.contrib.auth.models import Group
from django.db.models.query import Prefetch
from extras.viewsets import NestedModelViewSet
from registry.filters.security import AllowedWebMapServiceOperationFilterSet
from registry.models.security import (AllowedWebFeatureServiceOperation,
                                      AllowedWebMapServiceOperation,
                                      WebFeatureServiceAuthentication,
                                      WebFeatureServiceOperation,
                                      WebFeatureServiceProxySetting,
                                      WebMapServiceAuthentication,
                                      WebMapServiceOperation,
                                      WebMapServiceProxySetting)
from registry.models.service import Layer, WebFeatureService, WebMapService
from registry.serializers.security import (
    AllowedWebFeatureServiceOperationSerializer,
    AllowedWebMapServiceOperationSerializer,
    WebFeatureServiceAuthenticationSerializer,
    WebFeatureServiceOperationSerializer,
    WebFeatureServiceProxySettingSerializer,
    WebMapServiceAuthenticationSerializer, WebMapServiceOperationSerializer,
    WebMapServiceProxySettingSerializer)
from rest_framework.permissions import DjangoObjectPermissions
from rest_framework_json_api.views import ModelViewSet, ReadOnlyModelViewSet


class WebMapServiceAuthenticationViewSetMixin():
    queryset = WebMapServiceAuthentication.objects.all()
    serializer_class = WebMapServiceAuthenticationSerializer
    search_fields = ('username', 'service__title', 'service__id')


class WebMapServiceAuthenticationViewSet(
    WebMapServiceAuthenticationViewSetMixin,
    ModelViewSet
):
    pass


class NestedWebMapServiceAuthenticationViewSet(
    WebMapServiceAuthenticationViewSetMixin,
    NestedModelViewSet
):
    pass


class WebMapServiceOperationViewSetMixin():
    queryset = WebMapServiceOperation.objects.all()
    serializer_class = WebMapServiceOperationSerializer
    search_fields = ('operation', )
    ordering_fields = ["operation"]
    filterset_fields = {
        'operation': ['exact', 'icontains', 'contains', 'in'],
    }


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
    queryset = WebFeatureServiceOperation.objects.all()
    serializer_class = WebFeatureServiceOperationSerializer
    search_fields = ('operation', )
    ordering_fields = ["operation"]
    filterset_fields = {
        'operation': ['exact', 'icontains', 'contains', 'in'],
    }


class WebFeatureServiceAuthenticationViewSetMixin():
    queryset = WebFeatureServiceAuthentication.objects.all()
    serializer_class = WebFeatureServiceAuthenticationSerializer
    search_fields = ('username', 'service__title', 'service__id')


class WebFeatureServiceAuthenticationViewSet(
    WebFeatureServiceAuthenticationViewSetMixin,
    ModelViewSet
):
    pass


class NestedFeatureServiceAuthenticationViewSet(
        WebFeatureServiceAuthenticationViewSetMixin,
        NestedModelViewSet
):
    pass


class WebFeatureServiceOperationViewSet(
    WebFeatureServiceOperationViewSetMixin,
    ReadOnlyModelViewSet
):
    pass


class NestedWebFeatureServiceOperationViewSet(
    WebFeatureServiceOperationViewSetMixin,
    NestedModelViewSet
):
    pass


class AllowedWebMapServiceOperationViewSetMixin():
    queryset = AllowedWebMapServiceOperation.objects.all()
    serializer_class = AllowedWebMapServiceOperationSerializer
    permission_classes = [DjangoObjectPermissions]

    filterset_class = AllowedWebMapServiceOperationFilterSet

    search_fields = (
        "description",
        "secured_service__title",
        "secured_layers__title"
    )

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
                        "mptt_tree_id",
                        "mptt_lft",
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


class WebMapServiceProxySettingViewSetMixin():
    queryset = WebMapServiceProxySetting.objects.all()
    serializer_class = WebMapServiceProxySettingSerializer
    permission_classes = [DjangoObjectPermissions]

    filterset_fields = {
        'id': ['exact', 'icontains', 'contains', 'in'],
        "camouflage": ["exact", "icontains", "contains"],
        "log_response": ["exact", "icontains", "contains"],
        "secured_service__title": ['exact', 'icontains', 'contains'],
    }
    search_fields = (
        "id",
        "secured_service__title",
    )

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

        return qs


class WebMapServiceProxySettingViewSet(
        WebMapServiceProxySettingViewSetMixin,
        ModelViewSet
):
    """ Endpoints for resource `WebMapServiceProxySetting`
        create:
            Endpoint to create new `WebMapServiceProxySetting` object
        list:
            Retrieves all `WebMapServiceProxySetting` objects
        retrieve:
            Retrieve one specific `WebMapServiceProxySetting` by the given id
        partial_update:
            Endpoint to update some fields of a `WebMapServiceProxySetting`

    """


class NestedWebMapServiceProxySettingViewSet(
        WebMapServiceProxySettingViewSetMixin,
        NestedModelViewSet
):
    """ Nested list endpoint for resource `WebMapServiceProxySetting`

        list:
            Retrieves all `WebMapServiceProxySetting` objects

    """


class WebFeatureServiceProxySettingViewSetMixin():
    queryset = WebFeatureServiceProxySetting.objects.all()
    serializer_class = WebFeatureServiceProxySettingSerializer
    permission_classes = [DjangoObjectPermissions]

    filterset_fields = {
        'id': ['exact', 'icontains', 'contains', 'in'],
        "camouflage": ["exact", "icontains", "contains"],
        "log_response": ["exact", "icontains", "contains"],
        "secured_service__title": ['exact', 'icontains', 'contains'],
    }
    search_fields = (
        "id",
        "secured_service__title",
    )

    def get_queryset(self):
        qs = super().get_queryset()
        include = self.request.GET.get("include", None)

        if not include or "securedService" not in include:
            defer = [
                f"secured_service__{field.name}"
                for field in WebFeatureService._meta.get_fields()
                if field.name not in ["id", "pk"]
            ]
            qs = qs.select_related("secured_service").defer(*defer)

        return qs


class WebFeatureServiceProxySettingViewSet(
        WebFeatureServiceProxySettingViewSetMixin,
        ModelViewSet
):
    """ Endpoints for resource `WebFeatureServiceProxySetting`
        create:
            Endpoint to create new `WebFeatureServiceProxySetting` object
        list:
            Retrieves all `WebFeatureServiceProxySetting` objects
        retrieve:
            Retrieve one specific `WebFeatureServiceProxySetting` by the given id
        partial_update:
            Endpoint to update some fields of a `WebFeatureServiceProxySetting`

    """


class NestedWebFeatureServiceProxySettingViewSet(
        WebFeatureServiceProxySettingViewSetMixin,
        NestedModelViewSet
):
    """ Nested list endpoint for resource `WebFeatureServiceProxySetting`

        list:
            Retrieves all `WebFeatureServiceProxySetting` objects

    """
