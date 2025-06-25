from django.contrib.auth import get_user_model
from django.db.models import OuterRef, Subquery
from django.db.models.query import Prefetch
from extras.viewsets import PreloadNotIncludesMixin, SerializerClassesMixin
from mptt2.models import Tree
from registry.models import Layer, WebMapService
from registry.models.metadata import (DatasetMetadataRecord, Keyword,
                                      MetadataContact)
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
    WebMapServiceHistorySerializer)
from rest_framework_json_api.views import ModelViewSet


class HistoricalViewSetMixin():
    # removes create and delete endpoints, cause this two actions are made by the mrmap system it self in registrion or update processing of the service.
    # delete is only provided on the service endpoint it self, which implicit removes all related objects
    http_method_names = ["get", "patch", "head", "options"]
    select_for_includes = {
        "historyUser": ["history_user"],
        # "historyRelation": ["history_relation"]
    }
    filterset_fields = {
        'id': ['exact', 'in'],
        'history_relation': ['exact'],
    }
    ordering_fields = ["id", 'history_date', 'history_user']

    def get_queryset(self, *args, **kwargs):
        qs = super().get_queryset(*args, **kwargs)

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
        return qs


class OGCServiceHistoricalViewSetMixin(
    SerializerClassesMixin,
    PreloadNotIncludesMixin,
    HistoricalViewSetMixin
):
    prefetch_for_not_includes = {
        "historyRelation.MetadataContact": [
            Prefetch(
                "history_relation__metadata_contact",
                queryset=MetadataContact.objects.only(
                    "id",
                ),
            ),
        ],
        "historyRelation.Keywords": [
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


class WebMapServiceHistoricalViewSet(
    OGCServiceHistoricalViewSetMixin,
    ModelViewSet
):

    queryset = WebMapService.change_log.all()
    serializer_classes = {
        "default": WebMapServiceHistorySerializer,
    }
    prefetch_for_not_includes = {
        "historyRelation.Layers": [
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
        "historyRelation.AllowedOperations": [
            Prefetch(
                "history_relation__allowed_operations",
                queryset=AllowedWebMapServiceOperation.objects.only(
                    "id", "secured_service__id")
            )
        ],
        "historyRelation.OperationUrls": [
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
    serializer_classes = {
        "default": LayerHistorySerializer,
    }
    prefetch_for_includes = {
        "historyRelation": [
            Prefetch(
                "history_relation",
                queryset=Layer.objects.with_inherited_attributes()
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
        "mpttParent": [
            Prefetch("mptt_parent",
                     queryset=Layer.objects.only("id"))
        ],
        "mpttTree": [
            Prefetch("mptt_tree",
                     queryset=Tree.objects.only("id"))
        ],
        "historyRelation": [
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
    serializer_classes = {
        "default": WebFeatureServiceHistorySerializer,
    }
    prefetch_for_not_includes = {
        "historyRelation.Featuretypes": [
            Prefetch(
                "history_relation__featuretypes",
                queryset=FeatureType.objects.only(
                    "id",
                    "service_id"
                ),
            )
        ],
        "historyRelation.AllowedOperations": [
            Prefetch(
                "history_relation__allowed_operations",
                queryset=AllowedWebFeatureServiceOperation.objects.only(
                    "id", "secured_service__id")
            )
        ],
        "historyRelation.OperationUrls": [
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
    serializer_classes = {
        "default": FeatureTypeHistorySerializer,
    }
    prefetch_for_not_includes = {
        "service": [
            Prefetch("service",
                     queryset=WebFeatureService.objects.only("id"))
        ],
        "historyRelation": [
            Prefetch("history_relation",
                     queryset=FeatureType.objects.only("id"))
        ],
        "historyRelation.Keywords": [
            Prefetch("history_relation__keywords",
                     queryset=Keyword.objects.only("id"))
        ]
    }


class CatalogueServiceHistoricalViewSet(
    OGCServiceHistoricalViewSetMixin,
    ModelViewSet
):

    queryset = CatalogueService.change_log.all()
    serializer_classes = {
        "default": CatalogueServiceHistorySerializer,
    }
    prefetch_for_not_includes = {

        "historyRelation.OperationUrls": [
            Prefetch(
                "history_relation__operation_urls",
                queryset=CatalogueServiceOperationUrl.objects.only(
                    "id", "service_id"),
            )
        ]
    }
