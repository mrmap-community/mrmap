from django.db.models.query import Prefetch
from extras.openapi import CustomAutoSchema
from extras.permissions import DjangoObjectPermissionsOrAnonReadOnly
from extras.viewsets import NestedModelViewSet
from registry.models.metadata import (DatasetMetadata, Keyword, Licence,
                                      MetadataContact, ReferenceSystem, Style)
from registry.models.service import CatalogueService, FeatureType, Layer
from registry.serializers.metadata import (DatasetMetadataSerializer,
                                           KeywordSerializer,
                                           LicenceSerializer,
                                           MetadataContactSerializer,
                                           ReferenceSystemSerializer,
                                           StyleSerializer)
from rest_framework_json_api.views import ModelViewSet


class KeywordViewSetMixin():
    schema = CustomAutoSchema(
        tags=["Keyword"],
    )
    queryset = Keyword.objects.all()
    serializer_class = KeywordSerializer
    filterset_fields = {
        "keyword": ["exact", "icontains", "contains"],
    }
    search_fields = ("keyword",)


class KeywordViewSet(
    KeywordViewSetMixin,
    ModelViewSet
):
    pass


class NestedKeywordViewSet(
    KeywordViewSetMixin,
    NestedModelViewSet
):
    pass


class LicenceViewSetMixin():
    schema = CustomAutoSchema(
        tags=["Licence"],
    )
    queryset = Licence.objects.all()
    serializer_class = LicenceSerializer
    filterset_fields = {
        "name": ["exact", "icontains", "contains"],
        "identifier": ["exact", "icontains", "contains"],
    }
    search_fields = ("name", "identifier")


class LicenceViewSet(
    LicenceViewSetMixin,
    ModelViewSet
):
    pass


class NestedLicenceViewSet(
    LicenceViewSetMixin,
    NestedModelViewSet
):
    pass


class ReferenceSystemViewSetMixin():
    schema = CustomAutoSchema(
        tags=["ReferenceSystem"],
    )
    queryset = ReferenceSystem.objects.all()
    serializer_class = ReferenceSystemSerializer
    filterset_fields = {
        "code": ["exact", "icontains", "contains"],
        "prefix": ["exact", "icontains", "contains"]
    }
    search_fields = ("code", "prefix")


class ReferenceSystemViewSet(
    ReferenceSystemViewSetMixin,
    ModelViewSet
):
    pass


class NestedReferenceSystemViewSet(
    ReferenceSystemViewSetMixin,
    NestedModelViewSet
):
    pass


class StyleViewSetMixin():
    schema = CustomAutoSchema(
        tags=["Style"],
    )
    queryset = Style.objects.all().select_related("layer")
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


class StyleViewSet(
    StyleViewSetMixin,
    ModelViewSet
):
    pass


class NestedStyleViewSet(
    StyleViewSetMixin,
    NestedModelViewSet
):
    pass


class DatasetMetadataViewSetMixin:
    schema = CustomAutoSchema(
        tags=["DatasetMetadata"],
    )
    queryset = DatasetMetadata.objects.all()
    serializer_class = DatasetMetadataSerializer
    filterset_fields = {
        "title": ["exact", "icontains", "contains"],
        "abstract": ["exact", "icontains", "contains"],
        "keywords__keyword": ["exact", "icontains", "contains"],
    }
    search_fields = ("title", "abstract", "keywords__keyword")
    ordering_fields = ["id", "title", "abstract", "hits", "date_stamp"]
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
        "self_pointing_catalogue_service": [
            Prefetch(
                "self_pointing_catalogue_service",
                queryset=CatalogueService.objects.prefetch_related("keywords"),
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
        if not include or "selfPointingCatalogueService" not in include:
            qs = qs.prefetch_related(
                Prefetch(
                    "self_pointing_catalogue_service",
                    queryset=CatalogueService.objects.only("id"),
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


class DatasetMetadataViewSet(
        DatasetMetadataViewSetMixin,
        ModelViewSet
):
    pass


class NestedDatasetMetadataViewSet(
    DatasetMetadataViewSetMixin,
    NestedModelViewSet
):
    pass


class MetadataContactViewSetMixin():
    schema = CustomAutoSchema(
        tags=["MetadataContact"],
    )
    queryset = MetadataContact.objects.all()
    serializer_class = MetadataContactSerializer


class MetadataContactViewSet(
        MetadataContactViewSetMixin,
        ModelViewSet
):
    pass


class NestedMetadataContactViewSet(
    MetadataContactViewSetMixin,
    NestedModelViewSet
):
    pass


class ServiceContactViewSet(
    MetadataContactViewSetMixin,
    ModelViewSet
):
    resource_name = 'ServiceContact'


class NestedServiceContactViewSet(
    MetadataContactViewSetMixin,
    NestedModelViewSet
):
    resource_name = 'ServiceContact'


class DatasetContactViewSet(
    MetadataContactViewSetMixin,
    ModelViewSet
):
    resource_name = 'DatasetContact'


class NestedDatasetContactViewSet(
    MetadataContactViewSetMixin,
    NestedModelViewSet
):
    resource_name = 'DatasetContact'
