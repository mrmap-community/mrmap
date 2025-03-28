from camel_converter import to_camel
from django.contrib.auth import get_user_model
from django.db.models import (Case, Count, Exists, F, OuterRef, Prefetch, Q,
                              Subquery, Sum)
from django.db.models import Value
from django.db.models import Value as V
from django.db.models import When
from django.db.models.expressions import F, OuterRef
from django.db.models.functions import Coalesce
from django.db.models.query import Prefetch
from django.db.models.sql.constants import LOUTER
from django_cte import With
from extras.permissions import DjangoObjectPermissionsOrAnonReadOnly
from extras.viewsets import (AsyncCreateMixin, HistoryInformationViewSetMixin,
                             NestedModelViewSet,
                             ObjectPermissionCheckerViewSetMixin,
                             PreloadNotIncludesMixin, SerializerClassesMixin,
                             SparseFieldMixin)
from notify.models import BackgroundProcess, ProcessNameEnum
from registry.enums.harvesting import CollectingStatenEnum
from registry.filters.service import (FeatureTypeFilterSet, LayerFilterSet,
                                      WebFeatureServiceFilterSet,
                                      WebMapServiceFilterSet)
from registry.models import (FeatureType, Layer, WebFeatureService,
                             WebMapService)
from registry.models.harvest import (HarvestedDatasetMetadataRelation,
                                     HarvestedServiceMetadataRelation,
                                     HarvestingJob)
from registry.models.metadata import (DatasetMetadataRecord, Keyword,
                                      MetadataContact, MimeType,
                                      ReferenceSystem, Style)
from registry.models.security import (AllowedWebFeatureServiceOperation,
                                      AllowedWebMapServiceOperation,
                                      WebFeatureServiceProxySetting,
                                      WebMapServiceProxySetting)
from registry.models.service import (CatalogueService,
                                     CatalogueServiceOperationUrl,
                                     WebFeatureServiceOperationUrl,
                                     WebMapServiceOperationUrl)
from registry.serializers.service import (CatalogueServiceCreateSerializer,
                                          CatalogueServiceSerializer,
                                          FeatureTypeSerializer,
                                          LayerSerializer,
                                          WebFeatureServiceCreateSerializer,
                                          WebFeatureServiceSerializer,
                                          WebMapServiceCreateSerializer,
                                          WebMapServiceHistorySerializer,
                                          WebMapServiceListSerializer,
                                          WebMapServiceSerializer)
from registry.tasks.service import build_ogc_service
from rest_framework_json_api.views import ModelViewSet


class WebMapServiceHistoricalViewSet(
    SerializerClassesMixin,
    ModelViewSet
):
    # removes create and delete endpoints, cause this two actions are made by the mrmap system it self in registrion or update processing of the service.
    # delete is only provided on the service endpoint it self, which implicit removes all related objects
    http_method_names = ["get", "patch", "head", "options"]

    queryset = WebMapService.change_log.all()
    serializer_classes = {
        "default": WebMapServiceHistorySerializer,
    }

    select_for_includes = {
        "history_user": ["history_user"],
        "history_relation": ["history_relation"]
    }

    filterset_fields = {
        'history_relation': ['exact'],
    }

    def get_queryset(self, *args, **kwargs):
        defer_metadata_contact = [
            f"metadata_contact__{field.name}"
            for field in MetadataContact._meta.get_fields()
            if field.name not in ["id", "pk"]
        ]
        defer_service_contact = [
            f"metadata_contact__{field.name}"
            for field in MetadataContact._meta.get_fields()
            if field.name not in ["id", "pk"]
        ]

        qs = super().get_queryset(*args, **kwargs).select_related("metadata_contact",
                                                                  "service_contact").defer(*defer_metadata_contact, *defer_service_contact)

        include = self.request.GET.get("include", None)

        if not include or "historyUser" not in include:
            defer = [
                f"history_user__{field.name}"
                for field in get_user_model()._meta.get_fields()
                if field.name not in ["id", "pk"]
            ]
            qs = qs.select_related("history_user").defer(*defer)
        elif include and "historyUser" in include:
            # TODO: select_for_includes setup does not work for history records...
            qs = qs.select_related("history_user")

        if not include or "history_relation__layers" not in include:
            qs = qs.prefetch_related(
                Prefetch(
                    "history_relation__layers",
                    queryset=Layer.objects.only(
                        "id",
                        "service_id",
                        "mptt_tree_id",
                        "mptt_lft",
                    ),
                )
            )
        if not include or "history_relation__metadata_contact" not in include:
            qs = qs.prefetch_related(
                Prefetch(
                    "history_relation__metadata_contact",
                    queryset=MetadataContact.objects.only(
                        "id",
                    ),
                )
            )
        if not include or "history_relation__keywords" not in include:
            qs = qs.prefetch_related(
                Prefetch("history_relation__keywords",
                         queryset=Keyword.objects.only("id"))
            )
        if not include or "history_relation__allowedOperations" not in include:
            qs = qs.prefetch_related(
                Prefetch(
                    "history_relation__allowed_operations",
                    queryset=AllowedWebMapServiceOperation.objects.only(
                        "id", "secured_service__id")
                )
            )
        if not include or "history_relation__operationUrls" not in include:
            qs = qs.prefetch_related(
                Prefetch(
                    "history_relation__operation_urls",
                    queryset=WebMapServiceOperationUrl.objects.only(
                        "id", "service_id"),
                )
            )
        return qs


class WebMapServiceViewSet(
    SerializerClassesMixin,
    AsyncCreateMixin,
    ObjectPermissionCheckerViewSetMixin,
    PreloadNotIncludesMixin,
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
    queryset = WebMapService.capabilities.all()
    serializer_classes = {
        "default": WebMapServiceSerializer,
        "list": WebMapServiceListSerializer,
        "create": WebMapServiceCreateSerializer,
    }
    select_for_includes = {
        "proxy_setting": ["proxy_setting"],
        "service_contact": ["service_contact"],
        "metadata_contact": ["metadata_contact"],
    }
    prefetch_for_includes = {
        "layers": [
            Prefetch(
                "layers",
                queryset=Layer.objects.with_inherited_attributes().select_related("mptt_parent", "mptt_tree").prefetch_related(
                    Prefetch(
                        "keywords",
                        queryset=Keyword.objects.only("id")
                    ),
                    Prefetch(
                        "registry_datasetmetadatarecord_metadata_records",
                        queryset=DatasetMetadataRecord.objects.only("id")
                    ),

                )
            )
        ],
        "keywords": ["keywords"],
        "operationUrls": [
            Prefetch(
                "operation_urls",
                queryset=WebMapServiceOperationUrl.objects.select_related(
                    "service",
                ).prefetch_related("mime_types"),
            )
        ],
    }
    prefetch_for_not_includes = {
        "layers": [
            Prefetch(
                "layers",
                queryset=Layer.objects.only(
                    "id",
                    "service_id",
                    "mptt_tree_id",
                    "mptt_lft",
                ),
            )
        ],
        "keywords": [
            Prefetch("keywords", queryset=Keyword.objects.only("id"))
        ],
        "allowedOperations": [
            Prefetch(
                "allowed_operations",
                queryset=AllowedWebMapServiceOperation.objects.only(
                    "id", "secured_service")
            )
        ],
        "operationUrls": [
            Prefetch(
                "operation_urls",
                queryset=WebMapServiceOperationUrl.objects.only(
                    "id", "service"),
            )
        ],
        "proxySetting": [
            Prefetch(
                "proxy_setting",
                queryset=WebMapServiceProxySetting.objects.only(
                    "id", )
            )
        ]
    }
    filterset_class = WebMapServiceFilterSet
    search_fields = ("id", "title", "abstract", "keywords__keyword")
    ordering_fields = ["id", "title", "abstract", "hits", "date_stamp"]
    permission_classes = [DjangoObjectPermissionsOrAnonReadOnly]
    task_function = build_ogc_service

    def get_task_kwargs(self, request, serializer):
        background_process = BackgroundProcess.objects.create(
            phase="Background process created",
            process_type=ProcessNameEnum.REGISTERING.value,
            description=f'Register new service with url {serializer.validated_data["get_capabilities_url"]}'  # noqa
        )

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
            },
            "background_process_pk": background_process.pk
        }

    def get_queryset(self, *args, **kwargs):
        qs = super().get_queryset(*args, **kwargs)
        fields_snake = self.request.GET.get(
            "fields[WebMapService]", "").split(',')
        fields = [to_camel(field) for field in fields_snake if field.strip()]

        if not fields or "camouflage" in fields:
            qs = qs.annotate(
                camouflage=Coalesce(
                    F("proxy_setting__camouflage"), V(False)),
            )
        if not fields or "logResponse" in fields:
            qs = qs.annotate(
                log_response=Coalesce(
                    F("proxy_setting__log_response"), V(False)),
            )
        if not fields or "isSecured" in fields:
            qs = qs.annotate(
                is_secured=Exists(
                    AllowedWebMapServiceOperation.objects.filter(
                        secured_service__id__exact=OuterRef("pk"),
                    )
                ),
            )
        if not fields or "isSpatialSecured" in fields:
            qs = qs.annotate(
                is_spatial_secured=Exists(
                    AllowedWebMapServiceOperation.objects.filter(
                        secured_service__id__exact=OuterRef("pk"),
                        allowed_area__isnull=False
                    )
                )
            )

        return qs


class LayerViewSetMixin(
    PreloadNotIncludesMixin,
    HistoryInformationViewSetMixin,
):
    queryset = Layer.objects.with_inherited_attributes().select_related("mptt_tree")
    serializer_class = LayerSerializer
    filterset_class = LayerFilterSet
    search_fields = ("id", "title", "abstract", "keywords__keyword")
    select_for_includes = {
        "service": ["service"],
        "service.operation_urls": ["service"]
    }
    prefetch_for_includes = {
        "service": ["service__keywords", "service__layers"],
        "service.operationUrls": [
            Prefetch(
                "service__operation_urls",
                queryset=WebMapServiceOperationUrl.objects.prefetch_related(
                    "mime_types"
                ),
            ),
            "service__keywords",
            "service__layers"
        ],
        "styles": ["styles"],
        "keywords": ["keywords"],
        "referenceSystems": ["reference_systems"],
        "datasetMetadata": ["registry_datasetmetadatarecord_metadata_records"]
    }
    prefetch_for_not_includes = {
        "mpttParent": [
            # TODO optimize queryset with defer
            Prefetch(
                "mptt_parent",
                queryset=Layer.objects.select_related(
                    "mptt_tree").only("id", "mptt_tree")
            )
        ],
        "styles": [
            Prefetch("styles", queryset=Style.objects.only("id", "layer_id"))
        ],
        "keywords": [
            Prefetch("keywords", queryset=Keyword.objects.only("id"))
        ],
        "referenceSystem": [
            Prefetch(
                "reference_systems", queryset=ReferenceSystem.objects.only("id")
            )
        ],
        "datasetMetadata": [
            Prefetch(
                "registry_datasetmetadatarecord_metadata_records", queryset=DatasetMetadataRecord.objects.only("id")
            )
        ]
    }
    permission_classes = [DjangoObjectPermissionsOrAnonReadOnly]
    ordering_fields = ["id", "title", "abstract",
                       "hits", "scale_max", "scale_min", "date_stamp", "mptt_lft", "mptt_rgt", "mptt_depth"]


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
    PreloadNotIncludesMixin,
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
    queryset = WebFeatureService.capabilities.all()
    serializer_classes = {
        "default": WebFeatureServiceSerializer,
        "create": WebFeatureServiceCreateSerializer,
    }
    select_for_includes = {
        "proxy_setting": ["proxy_setting"],
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
        "allowedOperations": [
            Prefetch(
                "allowed_operations",
                queryset=AllowedWebFeatureServiceOperation.objects.select_related(
                    "secured_service")
            )
        ],
        "operationUrls": [
            Prefetch(
                "operation_urls",
                queryset=WebFeatureServiceOperationUrl.objects.select_related(
                    "service"
                ).prefetch_related("mime_types"),
            )
        ],
    }
    prefetch_for_not_includes = {
        "featureTypes": [
            Prefetch(
                "featuretypes",
                queryset=FeatureType.objects.only(
                    "id",
                    "service_id",
                )
            ),
        ],
        "keywords": [
            Prefetch("keywords", queryset=Keyword.objects.only("id"))
        ],
        "allowedOperations": [
            Prefetch(
                "allowed_operations",
                queryset=AllowedWebFeatureServiceOperation.objects.only(
                    "id", "secured_service")
            )
        ],
        "operationUrls": [
            Prefetch(
                "operation_urls",
                queryset=WebFeatureServiceOperationUrl.objects.only(
                    "id", "service"),
            )
        ],
        "proxySetting": [
            Prefetch(
                "proxy_setting",
                queryset=WebFeatureServiceProxySetting.objects.only(
                    "id", )
            )
        ]
    }
    filterset_class = WebFeatureServiceFilterSet
    search_fields = ("id", "title", "abstract", "keywords__keyword")
    ordering_fields = ["id", "title", "abstract", "hits", "date_stamp"]
    permission_classes = [DjangoObjectPermissionsOrAnonReadOnly]
    task_function = build_ogc_service

    def get_task_kwargs(self, request, serializer):
        background_process = BackgroundProcess.objects.create(
            phase="Background process created",
            process_type=ProcessNameEnum.REGISTERING.value,
            description=f'Register new service with url {serializer.validated_data["get_capabilities_url"]}'  # noqa
        )

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
            },
            "background_process_pk": background_process.pk
        }

    def get_queryset(self, *args, **kwargs):
        qs = super().get_queryset(*args, **kwargs)
        fields_snake = self.request.GET.get(
            "fields[WebFeatureService]", "").split(',')
        fields = [to_camel(field) for field in fields_snake if field.strip()]

        if not fields or "camouflage" in fields:
            qs = qs.annotate(
                camouflage=Coalesce(
                    F("proxy_setting__camouflage"), V(False)),
            )
        if not fields or "logResponse" in fields:
            qs = qs.annotate(
                log_response=Coalesce(
                    F("proxy_setting__log_response"), V(False)),
            )
        if not fields or "isSecured" in fields:
            qs = qs.annotate(
                is_secured=Exists(
                    AllowedWebFeatureServiceOperation.objects.filter(
                        secured_service__id__exact=OuterRef("pk"),
                    )
                ),
            )
        if not fields or "isSpatialSecured" in fields:
            qs = qs.annotate(
                is_spatial_secured=Exists(
                    AllowedWebFeatureServiceOperation.objects.filter(
                        secured_service__id__exact=OuterRef("pk"),
                        allowed_area__isnull=False
                    )
                )
            )

        return qs


class FeatureTypeViewSetMixin(
    PreloadNotIncludesMixin,
    HistoryInformationViewSetMixin,
):
    queryset = FeatureType.objects.all()
    serializer_class = FeatureTypeSerializer
    filterset_class = FeatureTypeFilterSet
    search_fields = ("id", "title", "abstract", "keywords__keyword")
    ordering_fields = ["id", "title", "abstract", "hits", "date_stamp"]

    select_for_includes = {
        "service": ["service"],
        "service.operation_urls": ["service"]
    }
    prefetch_for_includes = {
        "service": ["service__keywords", "service__featuretypes"],
        "service.operationUrls": [
            Prefetch(
                "service__operation_urls",
                queryset=WebFeatureServiceOperationUrl.objects.prefetch_related(
                    "mime_types"
                ),
            ),
            "service__keywords",
            "service__featuretypes"
        ],
        "outputFormats": ["output_formats"],
        "keywords": ["keywords"],
        "referenceSystems": ["reference_systems"],
    }
    prefetch_for_not_includes = {
        "keywords": [
            Prefetch("keywords", queryset=Keyword.objects.only("id"))
        ],
        "referenceSystems": [
            Prefetch(
                "reference_systems", queryset=ReferenceSystem.objects.only("id")
            )
        ],
        "outputFormats": [
            Prefetch(
                "output_formats", queryset=MimeType.objects.only("id")
            )
        ]
    }
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


class CatalogueServiceViewSetMixin(
    SerializerClassesMixin,
    AsyncCreateMixin,
    ObjectPermissionCheckerViewSetMixin,
    PreloadNotIncludesMixin,
    SparseFieldMixin,
    HistoryInformationViewSetMixin,
):
    """ Endpoints for resource `CatalogueService`

        create:
            Endpoint to register new `CatalogueService` object
        list:
            Retrieves all registered `CatalogueService` objects
        retrieve:
            Retrieve one specific `CatalogueService` by the given id
        partial_update:
            Endpoint to update some fields of a registered `CatalogueService`
        destroy:
            Endpoint to remove a registered `CatalogueService` from the system
    """
    queryset = CatalogueService.objects.all()
    serializer_classes = {
        "default": CatalogueServiceSerializer,
        "create": CatalogueServiceCreateSerializer,
    }
    search_fields = ("id", "title", "abstract", "keywords__keyword")
    filterset_fields = {
        'id': ['exact', 'icontains', 'contains', 'in'],
        'title': ['exact', 'icontains', 'contains'],
        'abstract': ['exact', 'icontains', 'contains']
    }
    ordering_fields = ["id", "title", "abstract", "hits", "date_stamp"]
    select_for_includes = {
        # "__all__": ["created_by"],
        "service_contact": ["service_contact"],
        "metadata_contact": ["metadata_contact"],

    }
    prefetch_for_includes = {
        # "__all__": [""],
        "keywords": ["keywords"],
        "operationUrls": [
            Prefetch(
                "operation_urls",
                queryset=CatalogueServiceOperationUrl.objects.select_related(
                    "service"
                ).prefetch_related("mime_types"),
            )
        ],
    }
    prefetch_for_not_includes = {
        "keywords": [
            Prefetch(
                "keywords",
                queryset=Keyword.objects.only("id")
            )
        ],
        "harvestedDatasets": [
            Prefetch(
                "registry_datasetmetadatarecord_metadata_records",
                queryset=DatasetMetadataRecord.objects.only("id"))
        ],
        "operationUrls": [
            Prefetch(
                "operation_urls",
                queryset=CatalogueServiceOperationUrl.objects.only(
                    "id", "service_id"),
            )
        ],
        "harvestingJob": [
            Prefetch(
                "harvesting_jobs",
                queryset=HarvestingJob.objects.only("id", "service")
            )
        ]
    }
    permission_classes = [DjangoObjectPermissionsOrAnonReadOnly]
    task_function = build_ogc_service

    def with_harvesting_stats(self, qs):
        harvested_total_count_needed = self.check_sparse_fields_contains(
            "harvestedTotalCount")
        harvested_dataset_count_needed = self.check_sparse_fields_contains(
            "harvestedDatasetCount") or harvested_total_count_needed
        harvested_service_count_needed = self.check_sparse_fields_contains(
            "harvestedServiceCount") or harvested_total_count_needed

        dataset_cte = With(
            queryset=HarvestedDatasetMetadataRelation.objects.annotate(service=F('harvesting_job__service_id')).values('service').annotate(
                dataset_count=Count(
                    "dataset_metadata_record_id",
                    filter=~Q(collecting_state=CollectingStatenEnum.DUPLICATED.value))
            ),
            name="dataset_cte"
        )
        service_cte = With(
            queryset=HarvestedServiceMetadataRelation.objects.annotate(service=F('harvesting_job__service_id')).values('service').annotate(
                service_count=Count(
                    "service_metadata_record_id",
                    filter=~Q(collecting_state=CollectingStatenEnum.DUPLICATED.value))),
            name="service_cte"
        )
        if harvested_dataset_count_needed:
            qs = (
                dataset_cte.join(model_or_queryset=qs,
                                 id=dataset_cte.col.service,
                                 _join_type=LOUTER
                                 )
                .with_cte(dataset_cte)
            )

        if harvested_service_count_needed:
            qs = (
                service_cte.join(model_or_queryset=qs,
                                 id=service_cte.col.service,
                                 _join_type=LOUTER
                                 )
                .with_cte(service_cte)
            )

        annotate_kwargs = {}
        if harvested_total_count_needed:
            annotate_kwargs.update({
                "harvested_dataset_count": Coalesce(dataset_cte.col.dataset_count, 0),
                "harvested_service_count": Coalesce(service_cte.col.service_count, 0),
                "harvested_total_count": Coalesce(F("harvested_dataset_count"), 0) + Coalesce(F("harvested_service_count"), 0)
            })
        if harvested_dataset_count_needed:
            annotate_kwargs.update({
                "harvested_dataset_count": Coalesce(dataset_cte.col.dataset_count, 0)
            })
        if harvested_service_count_needed:
            annotate_kwargs.update({
                "harvested_service_count": Coalesce(service_cte.col.service_count, 0),
            })
        if annotate_kwargs:
            qs = qs.annotate(**annotate_kwargs)
        return qs

    def get_queryset(self, *args, **kwargs):
        qs = super().get_queryset(*args, **kwargs)
        qs = self.with_harvesting_stats(qs)
        return qs

    def get_task_kwargs(self, request, serializer):
        background_process = BackgroundProcess.objects.create(
            phase="Background process created",
            process_type=ProcessNameEnum.REGISTERING.value,
            description=f'Register new service with url {serializer.validated_data["get_capabilities_url"]}'  # noqa
        )
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
            },
            "background_process_pk": background_process.pk
        }


class CatalogueServiceViewSet(
    CatalogueServiceViewSetMixin,
    ModelViewSet
):
    pass


class NestedCatalogueServiceViewSet(
    CatalogueServiceViewSetMixin,
    NestedModelViewSet
):
    pass
