from django.db.models.query import Prefetch
# HistoricalViewSetMixin moved to extras/viewsets.py with #741: it is the same
# read plan for every model which keeps history, and ``accounts`` needs it for
# its role tables without importing the registry's api
from extras.viewsets import (HistoricalViewSetMixin, PreloadNotIncludesMixin,
                             SerializerClassesMixin)
from mptt2.models import Tree
from registry.filters.historical import (
    CatalogueServiceHistoricalFilterSet, FeatureTypeHistoricalFilterSet,
    LayerHistoricalFilterSet, WebFeatureServiceHistoricalFilterSet,
    WebMapServiceHistoricalFilterSet)
from registry.models import Layer, WebMapService
from registry.models.metadata import (DatasetMetadataRecord, Keyword,
                                      MetadataContact, ServiceMetadataRecord)
from registry.models.security import (AllowedWebFeatureServiceOperation,
                                      AllowedWebMapServiceOperation)
from registry.models.service import (CatalogueService,
                                     CatalogueServiceOperationUrl, FeatureType,
                                     WebFeatureService,
                                     WebFeatureServiceOperationUrl,
                                     WebMapServiceOperationUrl)
from registry.serializers.historical import (
    CatalogueServiceHistorySerializer, FeatureTypeHistorySerializer,
    LayerHistorySerializer, WebFeatureServiceHistorySerializer,
    WebMapServiceHistorySerializer, DatasetMetadataRecordHistorySerializer,
    ServiceMetadataRecordHistorySerializer)
from rest_framework_json_api.views import ModelViewSet


class OGCServiceHistoricalViewSetMixin(
    SerializerClassesMixin,
    PreloadNotIncludesMixin,
    HistoricalViewSetMixin
):
    prefetch_for_not_includes = {
        "history_relation.metadata_contact": [
            Prefetch(
                "history_relation__metadata_contact",
                queryset=MetadataContact.objects.only(
                    "id",
                ),
            ),
        ],
        "history_relation.keywords": [
            Prefetch("history_relation__keywords",
                     queryset=Keyword.objects.only("id"))
        ]
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

        return super().get_queryset(*args, **kwargs).select_related("metadata_contact",
                                                                    "service_contact").defer(*defer_metadata_contact, *defer_service_contact)


HISTORY_OPERATION_URLS = "history_relation.operation_urls"


class WebMapServiceHistoricalViewSet(
    OGCServiceHistoricalViewSetMixin,
    ModelViewSet
):

    queryset = WebMapService.change_log.all()
    filterset_class = WebMapServiceHistoricalFilterSet
    serializer_classes = {
        "default": WebMapServiceHistorySerializer,
    }
    prefetch_for_not_includes = {
        "history_relation.layers": [
            Prefetch(
                "history_relation__layers",
                queryset=Layer.objects.only(
                    "id",
                    "service_id",
                    "mptt_tree_id",
                    "mptt_lft",
                ),
            )
        ],
        "history_relation.allowed_operations": [
            Prefetch(
                "history_relation__allowed_operations",
                queryset=AllowedWebMapServiceOperation.objects.only(
                    "id", "secured_service__id")
            )
        ],
        HISTORY_OPERATION_URLS: [
            Prefetch(
                "history_relation__operation_urls",
                queryset=WebMapServiceOperationUrl.objects.only(
                    "id", "service_id"),
            )
        ]
    }


class LayerHistoricalViewSet(
    SerializerClassesMixin,
    PreloadNotIncludesMixin,
    HistoricalViewSetMixin,
    ModelViewSet
):

    queryset = Layer.change_log.all()
    filterset_class = LayerHistoricalFilterSet
    serializer_classes = {
        "default": LayerHistorySerializer,
    }
    prefetch_for_includes = {
        "history_relation": [
            Prefetch(
                "history_relation",
                queryset=Layer.objects.with_inherited_attributes_cte()
                .select_related(
                    "mptt_parent",
                    "mptt_parent",
                    "mptt_tree",
                    "service",
                ).prefetch_related(
                    "keywords",
                    "styles",
                    "reference_systems",
                    Prefetch(
                        "registry_datasetmetadatarecord_metadata_records",
                        queryset=DatasetMetadataRecord.objects.only("id")
                    ),

                )
            )
        ],
    }
    prefetch_for_not_includes = {
        "service": [
            Prefetch("service",
                     queryset=WebMapService.objects.only("id"))
        ],
        "mptt_parent": [
            Prefetch("mptt_parent",
                     queryset=Layer.objects.only("id"))
        ],
        "mptt_tree": [
            Prefetch("mptt_tree",
                     queryset=Tree.objects.only("id"))
        ],
        "history_relation": [
            Prefetch("history_relation",
                     queryset=Layer.objects.only("id"))
        ],
        # "historyRelation.Keywords": [
        #     Prefetch("history_relation__keywords",
        #              queryset=Keyword.objects.only("id"))
        # ]
    }


class WebFeatureServiceHistoricalViewSet(
    OGCServiceHistoricalViewSetMixin,
    ModelViewSet
):

    queryset = WebFeatureService.change_log.all()
    filterset_class = WebFeatureServiceHistoricalFilterSet
    serializer_classes = {
        "default": WebFeatureServiceHistorySerializer,
    }
    prefetch_for_not_includes = {
        "history_relation.featuretypes": [
            Prefetch(
                "history_relation__featuretypes",
                queryset=FeatureType.objects.only(
                    "id",
                    "service_id"
                ),
            )
        ],
        "history_relation.allowed_operations": [
            Prefetch(
                "history_relation__allowed_operations",
                queryset=AllowedWebFeatureServiceOperation.objects.only(
                    "id", "secured_service__id")
            )
        ],
        HISTORY_OPERATION_URLS: [
            Prefetch(
                "history_relation__operation_urls",
                queryset=WebFeatureServiceOperationUrl.objects.only(
                    "id", "service_id"),
            )
        ]
    }


class FeatureTypeHistoricalViewSet(
    SerializerClassesMixin,
    PreloadNotIncludesMixin,
    HistoricalViewSetMixin,
    ModelViewSet
):
    queryset = FeatureType.change_log.all()
    filterset_class = FeatureTypeHistoricalFilterSet
    serializer_classes = {
        "default": FeatureTypeHistorySerializer,
    }
    prefetch_for_not_includes = {
        "service": [
            Prefetch("service",
                     queryset=WebFeatureService.objects.only("id"))
        ],
        "history_relation": [
            Prefetch("history_relation",
                     queryset=FeatureType.objects.only("id"))
        ],
        "history_relation.keywords": [
            Prefetch("history_relation__keywords",
                     queryset=Keyword.objects.only("id"))
        ]
    }


class CatalogueServiceHistoricalViewSet(
    OGCServiceHistoricalViewSetMixin,
    ModelViewSet
):

    queryset = CatalogueService.change_log.all()
    filterset_class = CatalogueServiceHistoricalFilterSet
    serializer_classes = {
        "default": CatalogueServiceHistorySerializer,
    }
    prefetch_for_not_includes = {

        HISTORY_OPERATION_URLS: [
            Prefetch(
                "history_relation__operation_urls",
                queryset=CatalogueServiceOperationUrl.objects.only(
                    "id", "service_id"),
            )
        ]
    }


class DatasetMetadataRecordHistoricalViewSet(HistoricalViewSetMixin, ModelViewSet):
    queryset = DatasetMetadataRecord.change_log.all()
    serializer_class = DatasetMetadataRecordHistorySerializer
    filterset_fields = {
        "history_relation": ["exact"],
        "history_type": ["exact", "in"],
        "history_date": ["gte", "lte"],
    }


class ServiceMetadataRecordHistoricalViewSet(HistoricalViewSetMixin, ModelViewSet):
    queryset = ServiceMetadataRecord.change_log.all()
    serializer_class = ServiceMetadataRecordHistorySerializer
    filterset_fields = {
        "history_relation": ["exact"],
        "history_type": ["exact", "in"],
        "history_date": ["gte", "lte"],
    }
