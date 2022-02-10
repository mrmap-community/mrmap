from django.db.models.query import Prefetch
from extras.openapi import CustomAutoSchema
from extras.permissions import DjangoObjectPermissionsOrAnonReadOnly
from extras.viewsets import (AsyncCreateMixin, HistoryInformationViewSetMixin,
                             NestedModelViewSet,
                             ObjectPermissionCheckerViewSetMixin,
                             SerializerClassesMixin)
from registry.filters.service import (FeatureTypeFilterSet, LayerFilterSet,
                                      WebFeatureServiceFilterSet,
                                      WebMapServiceFilterSet)
from registry.models import (FeatureType, Layer, WebFeatureService,
                             WebMapService)
from registry.models.metadata import Keyword, ReferenceSystem, Style
from registry.models.service import (CatalougeService,
                                     WebFeatureServiceOperationUrl,
                                     WebMapServiceOperationUrl)
from registry.serializers.service import (CatalougeServiceCreateSerializer,
                                          CatalougeServiceSerializer,
                                          FeatureTypeSerializer,
                                          LayerSerializer,
                                          WebFeatureServiceCreateSerializer,
                                          WebFeatureServiceSerializer,
                                          WebMapServiceCreateSerializer,
                                          WebMapServiceSerializer)
from registry.tasks.service import build_ogc_service
from rest_framework_json_api.views import ModelViewSet


class WebMapServiceViewSet(
    SerializerClassesMixin,
    AsyncCreateMixin,
    ObjectPermissionCheckerViewSetMixin,
    HistoryInformationViewSetMixin,
    ModelViewSet,
):
    """ Endpoints for resource `WebMapService`

        create:
            Endpoint to register new `WebMapServices` object
        list:
            Retrieves all registered `WebMapServices` objects
        retrieve:
            Retrieve one specific `WebMapServices` by the given id
        partial_update:
            Endpoint to update some fields of a registered `WebMapServices`
        destroy:
            Endpoint to remove a registered `WebMapServices` from the system
    """
    schema = CustomAutoSchema(
        tags=["WebMapService"],
    )
    queryset = WebMapService.objects.all()
    serializer_classes = {
        "default": WebMapServiceSerializer,
        "create": WebMapServiceCreateSerializer,
    }
    select_for_includes = {
        "service_contact": ["service_contact"],
        "metadata_contact": ["metadata_contact"],
    }
    prefetch_for_includes = {
        "layers": [
            Prefetch(
                "layers",
                queryset=Layer.objects.select_related("parent").prefetch_related(
                    "keywords",
                    "styles",
                    "reference_systems",
                ),
            ),
        ],
        "keywords": ["keywords"],
        "operation_urls": [
            Prefetch(
                "operation_urls",
                queryset=WebMapServiceOperationUrl.objects.select_related(
                    "service"
                ).prefetch_related("mime_types"),
            )
        ],
    }
    filterset_class = WebMapServiceFilterSet
    search_fields = ("id", "title", "abstract", "keywords__keyword")
    permission_classes = [DjangoObjectPermissionsOrAnonReadOnly]
    task_function = build_ogc_service

    def get_task_kwargs(self, request, serializer):
        return {
            "get_capabilities_url": serializer.validated_data["get_capabilities_url"],
            "collect_metadata_records": serializer.validated_data["collect_metadata_records"],
            "service_auth_pk": serializer.service_auth.id if hasattr(serializer, "service_auth") else None,
            "request": {
                "path": request.path,
                "method": request.method,
                "content_type": request.content_type,
                "data": request.GET,
                "user_pk": request.user.pk,
            }
        }

    def dispatch(self, request, *args, **kwargs):
        if "layer_pk" in self.kwargs:
            self.lookup_field = "layer"
            self.lookup_url_kwarg = "layer_pk"
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        qs = super().get_queryset()
        include = self.request.GET.get("include", None)
        if not include or "layers" not in include:
            qs = qs.prefetch_related(
                Prefetch(
                    "layers",
                    queryset=Layer.objects.only(
                        "id",
                        "service_id",
                        "tree_id",
                        "lft",
                    ),
                )
            )
        if not include or "keywords" not in include:
            qs = qs.prefetch_related(
                Prefetch("keywords", queryset=Keyword.objects.only("id"))
            )
        if not include or "operationUrls" not in include:
            qs = qs.prefetch_related(
                Prefetch(
                    "operation_urls",
                    queryset=WebMapServiceOperationUrl.objects.only(
                        "id", "service_id"),
                )
            )
        return qs


class LayerViewSetMixin(
    HistoryInformationViewSetMixin,
):
    schema = CustomAutoSchema(
        tags=["Layer"],
    )
    queryset = Layer.objects.all()
    serializer_class = LayerSerializer
    filterset_class = LayerFilterSet
    search_fields = ("id", "title", "abstract", "keywords__keyword")
    select_for_includes = {
        "service": ["service"],
    }
    prefetch_for_includes = {
        "service": ["service__keywords", "service__layers"],
        "service.operation_urls": [
            Prefetch(
                "service__operation_urls",
                queryset=WebMapServiceOperationUrl.objects.prefetch_related(
                    "mime_types"
                ),
            )
        ],
        "styles": ["styles"],
        "keywords": ["keywords"],
        "reference_systems": ["reference_systems"],
    }
    permission_classes = [DjangoObjectPermissionsOrAnonReadOnly]

    def get_queryset(self):
        qs = super().get_queryset()
        include = self.request.GET.get("include", None)
        if not include or "service" not in include:
            defer = [
                f"service__{field.name}"
                for field in WebMapService._meta.get_fields()
                if field.name not in ["id", "pk"]
            ]
            qs = qs.select_related("service").defer(*defer)
        if not include or "parent" not in include:
            # TODO optimize queryset with defer
            qs = qs.select_related("parent")
        if not include or "styles" not in include:
            qs = qs.prefetch_related(
                Prefetch("styles", queryset=Style.objects.only("id", "layer_id"))
            )
        if not include or "keywords" not in include:
            qs = qs.prefetch_related(
                Prefetch("keywords", queryset=Keyword.objects.only("id"))
            )
        if not include or "referenceSystems" not in include:
            qs = qs.prefetch_related(
                Prefetch(
                    "reference_systems", queryset=ReferenceSystem.objects.only("id")
                )
            )

        return qs


class LayerViewSet(
        LayerViewSetMixin,
        ModelViewSet):
    """ Endpoints for resource `Layer`

        list:
            Retrieves all registered `Layer` objects
        retrieve:
            Retrieve one specific `Layer` by the given id
        partial_update:
            Endpoint to update some fields of a registered `Layer`

    """
    # removes create and delete endpoints, cause this two actions are made by the mrmap system it self in registrion or update processing of the service.
    # delete is only provided on the service endpoint it self, which implicit removes all related objects
    http_method_names = ["get", "patch", "head", "options"]


class NestedLayerViewSet(
        LayerViewSetMixin,
        NestedModelViewSet):
    """ Nested list endpoint for resource `Layer`

        list:
            Retrieves all registered `Layer` objects

    """


class WebFeatureServiceViewSet(
    SerializerClassesMixin,
    AsyncCreateMixin,
    ObjectPermissionCheckerViewSetMixin,
    HistoryInformationViewSetMixin,
    ModelViewSet,
):
    """ Endpoints for resource `WebFeatureService`

        create:
            Endpoint to register new `WebFeatureService` object
        list:
            Retrieves all registered `WebFeatureService` objects
        retrieve:
            Retrieve one specific `WebFeatureService` by the given id
        partial_update:
            Endpoint to update some fields of a registered `WebFeatureService`
        destroy:
            Endpoint to remove a registered `WebFeatureService` from the system
    """
    schema = CustomAutoSchema(
        tags=["WebFeatureService"],
    )
    queryset = WebFeatureService.objects.all()
    serializer_classes = {
        "default": WebFeatureServiceSerializer,
        "create": WebFeatureServiceCreateSerializer,
    }
    select_for_includes = {
        "service_contact": ["service_contact"],
        "metadata_contact": ["metadata_contact"],
    }
    prefetch_for_includes = {
        "featuretypes": [
            Prefetch(
                "featuretypes",
                queryset=FeatureType.objects.prefetch_related(
                    "keywords",
                    "reference_systems",
                    "output_formats",
                ),
            ),
        ],
        "keywords": ["keywords"],
        "operation_urls": [
            Prefetch(
                "operation_urls",
                queryset=WebFeatureServiceOperationUrl.objects.select_related(
                    "service"
                ).prefetch_related("mime_types"),
            )
        ],
    }
    filterset_class = WebFeatureServiceFilterSet
    search_fields = ("id", "title", "abstract", "keywords__keyword")
    permission_classes = [DjangoObjectPermissionsOrAnonReadOnly]
    task_function = build_ogc_service

    def dispatch(self, request, *args, **kwargs):
        if "featuretype_pk" in self.kwargs:
            self.lookup_field = "featuretype"
            self.lookup_url_kwarg = "featuretype_pk"
        return super().dispatch(request, *args, **kwargs)

    def get_task_kwargs(self, request, serializer):
        return {
            "get_capabilities_url": serializer.validated_data["get_capabilities_url"],
            "collect_metadata_records": serializer.validated_data["collect_metadata_records"],
            "service_auth_pk": serializer.service_auth.id if hasattr(serializer, "service_auth") else None,
            "http_request": {
                "path": request.path,
                "method": request.method,
                "content_type": request.content_type,
                "data": request.GET,
                "user_pk": request.user.pk,
            }
        }

    def get_queryset(self):
        qs = super().get_queryset()
        include = self.request.GET.get("include", None)
        if not include or "featuretypes" not in include:
            qs = qs.prefetch_related(
                Prefetch(
                    "featuretypes",
                    queryset=FeatureType.objects.only(
                        "id",
                        "service_id",
                    )
                ),
            )
        if not include or "keywords" not in include:
            qs = qs.prefetch_related(
                Prefetch("keywords", queryset=Keyword.objects.only("id"))
            )
        if not include or "operationUrls" not in include:
            qs = qs.prefetch_related(
                Prefetch(
                    "operation_urls",
                    queryset=WebFeatureServiceOperationUrl.objects.only(
                        "id", "service_id"),
                )
            )
        return qs


class FeatureTypeViewSetMixin(
    HistoryInformationViewSetMixin,
):
    schema = CustomAutoSchema(
        tags=["FeatureType"],
    )
    queryset = FeatureType.objects.all()
    serializer_class = FeatureTypeSerializer
    filterset_class = FeatureTypeFilterSet
    search_fields = ("id", "title", "abstract", "keywords__keyword")

    prefetch_for_includes = {"__all__": [], "keywords": ["keywords"]}
    permission_classes = [DjangoObjectPermissionsOrAnonReadOnly]


class FeatureTypeViewSet(
    FeatureTypeViewSetMixin,
    ModelViewSet
):
    """ Endpoints for resource `FeatureType`

        list:
            Retrieves all registered `FeatureType` objects
        retrieve:
            Retrieve one specific `FeatureType` by the given id
        partial_update:
            Endpoint to update some fields of a registered `FeatureType`

    """
    # removes create and delete endpoints, cause this two actions are made by the mrmap system it self in registrion or update processing of the service.
    # delete is only provided on the service endpoint it self, which implicit removes all related objects
    http_method_names = ["get", "patch", "head", "options"]


class NestedFeatureTypeViewSet(
    FeatureTypeViewSetMixin,
    NestedModelViewSet
):
    """ Nested list endpoint for resource `FeatureType`

        list:
            Retrieves all registered `FeatureType` objects

    """


class CatalougeServiceViewSet(
    SerializerClassesMixin,
    AsyncCreateMixin,
    ObjectPermissionCheckerViewSetMixin,
    HistoryInformationViewSetMixin,
    ModelViewSet,
):
    """ Endpoints for resource `CatalougeService`

        create:
            Endpoint to register new `CatalougeService` object
        list:
            Retrieves all registered `CatalougeService` objects
        retrieve:
            Retrieve one specific `CatalougeService` by the given id
        partial_update:
            Endpoint to update some fields of a registered `CatalougeService`
        destroy:
            Endpoint to remove a registered `CatalougeService` from the system
    """
    schema = CustomAutoSchema(
        tags=["CatalogueService"],
    )
    queryset = CatalougeService.objects.all()
    serializer_classes = {
        "default": CatalougeServiceSerializer,
        "create": CatalougeServiceCreateSerializer,
    }
    search_fields = ("id", "title", "abstract", "keywords__keyword")
    permission_classes = [DjangoObjectPermissionsOrAnonReadOnly]
    task_function = build_ogc_service

    def get_task_kwargs(self, request, serializer):
        return {
            "get_capabilities_url": serializer.validated_data["get_capabilities_url"],
            "collect_metadata_records": False,  # CSW has no remote metadata records
            "service_auth_pk": serializer.service_auth.id if hasattr(serializer, "service_auth") else None,
            "http_request": {
                "path": request.path,
                "method": request.method,
                "content_type": request.content_type,
                "data": request.GET,
                "user_pk": request.user.pk,
            }
        }
