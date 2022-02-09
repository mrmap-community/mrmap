from django.db.models.query import Prefetch
from extras.openapi import CustomAutoSchema
from extras.permissions import DjangoObjectPermissionsOrAnonReadOnly
from registry.models.metadata import (DatasetMetadata, Keyword,
                                      MetadataContact, ReferenceSystem, Style)
from registry.models.service import CatalougeService, FeatureType, Layer
from registry.serializers.metadata import (DatasetMetadataSerializer,
                                           KeywordSerializer,
                                           MetadataContactSerializer,
                                           StyleSerializer)
from rest_framework_extensions.mixins import NestedViewSetMixin
from rest_framework_json_api.views import ModelViewSet


class KeywordViewSet(NestedViewSetMixin, ModelViewSet):
    schema = CustomAutoSchema(
        tags=["Metadata"],
    )
    queryset = Keyword.objects.all()
    serializer_class = KeywordSerializer
    filterset_fields = {
        "keyword": ["exact", "icontains", "contains"],
    }
    search_fields = ("keyword",)


class StyleViewSet(NestedViewSetMixin, ModelViewSet):
    schema = CustomAutoSchema(
        tags=["Metadata"],
    )
    queryset = Style.objects.all()
    serializer_class = StyleSerializer
    filterset_fields = {
        "name": ["exact", "icontains", "contains"],
        "title": ["exact", "icontains", "contains"],
    }
    search_fields = (
        "name",
        "title",
    )
    # removes create and delete endpoints, cause this two actions are made by the mrmap system it self in registrion or update processing of the service.
    # delete is only provided on the service endpoint it self, which implicit removes all related objects
    http_method_names = ["get", "patch", "head", "options"]


class DatasetMetadataViewSet(ModelViewSet):
    schema = CustomAutoSchema(
        tags=["Metadata"],
    )
    queryset = DatasetMetadata.objects.all()
    serializer_class = DatasetMetadataSerializer
    filterset_fields = {
        "title": ["exact", "icontains", "contains"],
        "abstract": ["exact", "icontains", "contains"],
        "keywords__keyword": ["exact", "icontains", "contains"],
    }
    search_fields = ("title", "abstract", "keywords__keyword")
    select_for_includes = {
        "metadata_contact": ["metadata_contact"],
        "dataset_contact": ["dataset_contact"],
    }
    prefetch_for_includes = {
        "self_pointing_layers": [
            Prefetch(
                "self_pointing_layers",
                queryset=Layer.objects.select_related("parent").prefetch_related(
                    "keywords", "styles", "reference_systems"
                ),
            ),
        ],
        "self_pointing_feature_types": [
            Prefetch(
                "self_pointing_feature_types",
                queryset=FeatureType.objects.prefetch_related(
                    "keywords", "reference_systems"
                ),
            )
        ],
        "self_pointing_catalouge_service": [
            Prefetch(
                "self_pointing_catalouge_service",
                queryset=CatalougeService.objects.prefetch_related("keywords"),
            )
        ],
        "keywords": ["keywords"],
        "reference_systems": ["reference_systems"],
        # "operation_urls": [Prefetch("operation_urls", queryset=WebMapServiceOperationUrl.objects.select_related("service").prefetch_related("mime_types"))]
    }
    permission_classes = [DjangoObjectPermissionsOrAnonReadOnly]

    def get_queryset(self):
        qs = super().get_queryset()
        include = self.request.GET.get("include", None)
        if not include or "metadataContact" not in include:
            defer = [
                f"metadata_contact__{field.name}"
                for field in MetadataContact._meta.get_fields()
                if field.name not in ["id", "pk"]
            ]
            qs = qs.select_related("metadata_contact").defer(*defer)
        if not include or "datasetContact" not in include:
            defer = [
                f"dataset_contact__{field.name}"
                for field in MetadataContact._meta.get_fields()
                if field.name not in ["id", "pk"]
            ]
            qs = qs.select_related("dataset_contact").defer(*defer)
        if not include or "selfPointingLayers" not in include:
            qs = qs.prefetch_related(
                Prefetch(
                    "self_pointing_layers",
                    queryset=Layer.objects.only(
                        "id",
                        "service_id",
                        "tree_id",
                        "lft",
                    ),
                )
            )
        if not include or "selfPointingFeatureTypes" not in include:
            qs = qs.prefetch_related(
                Prefetch(
                    "self_pointing_feature_types",
                    queryset=FeatureType.objects.only("id", "service_id"),
                )
            )
        if not include or "selfPointingCatalougeService" not in include:
            qs = qs.prefetch_related(
                Prefetch(
                    "self_pointing_catalouge_service",
                    queryset=CatalougeService.objects.only("id"),
                )
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


class MetadataContactViewSet(ModelViewSet):
    schema = CustomAutoSchema(
        tags=["Metadata"],
    )
    queryset = MetadataContact.objects.all()
    serializer_class = MetadataContactSerializer
