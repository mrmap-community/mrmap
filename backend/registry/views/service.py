from camel_converter import to_camel
from django.db.models import Count, Exists, F, OuterRef, Prefetch, Q, Sum
from django.db.models import Value as V
from django.db.models.functions import Coalesce
from django.db.models.sql.constants import LOUTER
from django_cte import With
from extras.permissions import DjangoObjectPermissionsOrAnonReadOnly
from extras.viewsets import (AsyncCreateMixin, HistoryInformationViewSetMixin,
                             NestedModelViewSet,
                             ObjectPermissionCheckerViewSetMixin,
                             PreloadNotIncludesMixin, SerializerClassesMixin,
                             SparseFieldMixin)
from notify.models import BackgroundProcess, ProcessNameEnum
from registry.enums.harvesting import CollectingStatenEnum, HarvestingPhaseEnum
from registry.filters.service import (FeatureTypeFilterSet, LayerFilterSet,
                                      WebFeatureServiceFilterSet,
                                      WebMapServiceFilterSet)
from registry.models import (FeatureType, Layer, WebFeatureService,
                             WebMapService)
from registry.models.harvest import HarvestedMetadataRelation, HarvestingJob
from registry.models.metadata import (DatasetMetadataRecord, Keyword, MimeType,
                                      ReferenceSystem, Style)
from registry.models.security import (AllowedWebFeatureServiceOperation,
                                      AllowedWebMapServiceOperation,
                                      WebFeatureServiceProxySetting,
                                      WebMapServiceProxySetting)
from registry.models.service import (CatalogueService,
                                     CatalogueServiceOperationUrl,
                                     WebFeatureServiceOperationUrl,
                                     WebMapServiceOperationUrl)
from registry.serializers.service import (
    CatalogueServiceCreateSerializer, CatalogueServiceOperationUrlSerializer,
    CatalogueServiceSerializer, FeatureTypeSerializer, LayerSerializer,
    WebFeatureServiceCreateSerializer, WebFeatureServiceSerializer,
    WebMapServiceCreateSerializer, WebMapServiceListSerializer,
    WebMapServiceOperationUrlSerializer, WebMapServiceSerializer)
from registry.tasks.service import build_ogc_service
from rest_framework_json_api.views import ModelViewSet


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


class WebMapServiceOperationUrlViewSetMixin(
):
    queryset = WebMapServiceOperationUrl.objects.all()
    serializer_class = WebMapServiceOperationUrlSerializer
    search_fields = ("id", "service")
    permission_classes = [DjangoObjectPermissionsOrAnonReadOnly]
    ordering_fields = ["id"]


class WebMapServiceOperationUrlViewSet(
    WebMapServiceOperationUrlViewSetMixin,
    ModelViewSet
):
    """ Endpoints for resource `WebMapServiceOperationUrl`

        list:
            Retrieves all registered `WebMapServiceOperationUrl` objects
        retrieve:
            Retrieve one specific `WebMapServiceOperationUrl` by the given id
        partial_update:
            Endpoint to update some fields of a registered `WebMapServiceOperationUrl`

    """
    # removes create and delete endpoints, cause this two actions are made by the mrmap system it self in registrion or update processing of the service.
    # delete is only provided on the service endpoint it self, which implicit removes all related objects
    http_method_names = ["get", "patch", "head", "options"]


class NestedWebMapServiceOperationUrlViewSet(
    WebMapServiceOperationUrlViewSetMixin,
    NestedModelViewSet
):
    """ Nested list endpoint for resource `WebMapServiceOperationUrl`

        list:
            Retrieves all registered `WebMapServiceOperationUrl` objects

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

    def with_running_harvesting_job(self, qs):
        running_harvesting_job_needed = self.check_sparse_fields_contains(
            "runningHarvestingJob")
        if running_harvesting_job_needed:
            qs = qs.prefetch_related(
                Prefetch(
                    "harvesting_jobs",
                    queryset=HarvestingJob.objects.filter(
                        done_at=None,
                        phase__lt=HarvestingPhaseEnum.COMPLETED.value
                    ).only("id", "service"),
                    to_attr="running_harvesting_job"
                ))

        return qs

    def with_harvesting_stats(self, qs):
        harvested_total_count_needed = self.check_sparse_fields_contains(
            "harvestedTotalCount")
        harvested_dataset_count_needed = self.check_sparse_fields_contains(
            "harvestedDatasetCount") or harvested_total_count_needed
        harvested_service_count_needed = self.check_sparse_fields_contains(
            "harvestedServiceCount") or harvested_total_count_needed

        # --- step 1: aggregate per harvesting_job_id ---
        job_level_kwargs = {}
        if harvested_dataset_count_needed:
            job_level_kwargs["dataset_count"] = Count(
                "id",
                filter=~Q(collecting_state=CollectingStatenEnum.DUPLICATED.value)
                & Q(dataset_metadata_record__isnull=False),
            )
        if harvested_service_count_needed:
            job_level_kwargs["service_count"] = Count(
                "id",
                filter=~Q(collecting_state=CollectingStatenEnum.DUPLICATED.value)
                & Q(service_metadata_record__isnull=False),
            )
        relation_agg = With(
            HarvestedMetadataRelation.objects.values("harvesting_job_id")
            .annotate(**job_level_kwargs),
            name="relation_agg",
        )

        # --- step 2: join by harvestingjob + aggregation per service id
        cte_kwargs = {}
        if harvested_dataset_count_needed:
            cte_kwargs.update({
                "dataset_count": Sum(relation_agg.col.dataset_count)
            })
        if harvested_service_count_needed:
            cte_kwargs.update({
                "service_count": Sum(relation_agg.col.service_count)
            })
        cte = With(
            relation_agg.join(
                HarvestingJob,
                id=relation_agg.col.harvesting_job_id,
            )
            .values("service_id")
            .annotate(**cte_kwargs),
            name="cte",
        )

        if harvested_total_count_needed or harvested_dataset_count_needed or harvested_service_count_needed:
            qs = (
                cte.join(model_or_queryset=qs,
                         id=cte.col.service_id,
                         _join_type=LOUTER
                         )
                .with_cte(relation_agg)
                .with_cte(cte)
            )

        # --- step 3: annotation of the final values
        annotate_kwargs = {}
        if harvested_total_count_needed:
            annotate_kwargs.update({
                "harvested_dataset_count": Coalesce(cte.col.dataset_count, 0),
                "harvested_service_count": Coalesce(cte.col.service_count, 0),
                "harvested_total_count": Coalesce(F("harvested_dataset_count"), 0) + Coalesce(F("harvested_service_count"), 0)
            })
        if harvested_dataset_count_needed:
            annotate_kwargs.update({
                "harvested_dataset_count": Coalesce(cte.col.dataset_count, 0)
            })
        if harvested_service_count_needed:
            annotate_kwargs.update({
                "harvested_service_count": Coalesce(cte.col.service_count, 0),
            })
        if annotate_kwargs:
            qs = qs.annotate(**annotate_kwargs)
        return qs

    def get_queryset(self, *args, **kwargs):
        qs = super().get_queryset(*args, **kwargs)
        qs = self.with_harvesting_stats(qs)
        qs = self.with_running_harvesting_job(qs)
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


class CatalogueServiceOperationUrlViewSetMixin(
):
    queryset = CatalogueServiceOperationUrl.objects.all()
    serializer_class = CatalogueServiceOperationUrlSerializer
    search_fields = ("id", "service")
    permission_classes = [DjangoObjectPermissionsOrAnonReadOnly]
    ordering_fields = ["id"]


class CatalogueServiceOperationUrlViewSet(
    CatalogueServiceOperationUrlViewSetMixin,
    ModelViewSet
):
    """ Endpoints for resource `CatalogueServiceOperationUrl`

        list:
            Retrieves all registered `CatalogueServiceOperationUrl` objects
        retrieve:
            Retrieve one specific `CatalogueServiceOperationUrl` by the given id
        partial_update:
            Endpoint to update some fields of a registered `CatalogueServiceOperationUrl`

    """
    # removes create and delete endpoints, cause this two actions are made by the mrmap system it self in registrion or update processing of the service.
    # delete is only provided on the service endpoint it self, which implicit removes all related objects
    http_method_names = ["get", "patch", "head", "options"]


class NestedCatalogueServiceOperationUrlViewSet(
    CatalogueServiceOperationUrlViewSetMixin,
    NestedModelViewSet
):
    """ Nested list endpoint for resource `CatalogueServiceOperationUrl`

        list:
            Retrieves all registered `CatalogueServiceOperationUrl` objects

    """
