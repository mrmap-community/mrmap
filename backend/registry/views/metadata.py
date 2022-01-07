from django.db.models.query import Prefetch
from registry.models.metadata import (
    DatasetMetadata,
    Keyword,
    MetadataContact,
    ReferenceSystem,
    Style,
)
from registry.models.service import CatalougeService, FeatureType, Layer
from registry.serializers.metadata import (
    DatasetMetadataSerializer,
    KeywordSerializer,
    MetadataContactSerializer,
    StyleSerializer,
)
from rest_framework_extensions.mixins import NestedViewSetMixin
from rest_framework_json_api.schemas.openapi import AutoSchema
from rest_framework_json_api.views import ModelViewSet


class KeywordViewSet(NestedViewSetMixin, ModelViewSet):
    schema = AutoSchema(
        tags=["Metadata"],
    )
    queryset = Keyword.objects.all()
    serializer_class = KeywordSerializer
    filterset_fields = {
        "keyword": ["exact", "icontains", "contains"],
    }
    search_fields = ("keyword",)


class StyleViewSet(NestedViewSetMixin, ModelViewSet):
    schema = AutoSchema(
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


class DatasetMetadataViewSet(ModelViewSet):
    schema = AutoSchema(
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

    def get_queryset(self):
        qs = super().get_queryset()
        include = self.request.GET.get("include", None)
        if not include or "metadata_contact" not in include:
            defer = [
                f"metadata_contact__{field.name}"
                for field in MetadataContact._meta.get_fields()
                if field.name not in ["id", "pk"]
            ]
            qs = qs.select_related("metadata_contact").defer(*defer)
        if not include or "dataset_contact" not in include:
            defer = [
                f"dataset_contact__{field.name}"
                for field in MetadataContact._meta.get_fields()
                if field.name not in ["id", "pk"]
            ]
            qs = qs.select_related("dataset_contact").defer(*defer)
        if not include or "self_pointing_layers" not in include:
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
        if not include or "self_pointing_feature_types" not in include:
            qs = qs.prefetch_related(
                Prefetch(
                    "self_pointing_feature_types",
                    queryset=FeatureType.objects.only("id", "service_id"),
                )
            )
        if not include or "self_pointing_catalouge_service" not in include:
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
        if not include or "reference_systems" not in include:
            qs = qs.prefetch_related(
                Prefetch(
                    "reference_systems", queryset=ReferenceSystem.objects.only("id")
                )
            )
        return qs


class MetadataContactViewSet(ModelViewSet):
    schema = AutoSchema(
        tags=["Metadata"],
    )
    queryset = MetadataContact.objects.all()
    serializer_class = MetadataContactSerializer
