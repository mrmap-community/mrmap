from registry.filters.metadata import (ApplicationMetadataRecordSpatialFilterSet,
                                       DatasetMetadataRecordSpatialFilterSet,
                                       ServiceMetadataRecordSpatialFilterSet)
from django.db.models import F
from django.db.models.query import Prefetch
from extras.permissions import DjangoObjectPermissionsOrAnonReadOnly
from extras.viewsets import (HistoryInformationViewSetMixin, NestedModelViewSet, PreloadNotIncludesMixin,
                             SerializerClassesMixin)
from registry.models.metadata import (ApplicationMetadataRecord, DatasetMetadataRecord, IsoCategory,
                                      Keyword, Language, Licence,
                                      MetadataContact, MetadataRelation, MimeType,
                                      ReferenceSystem, ServiceMetadataRecord,
                                      Style, TimeExtent)
from registry.models.service import (CatalogueService, FeatureType, Layer,
                                     WebFeatureService, WebMapService)
from registry.serializers.metadata import (ApplicationMetadataRecordSerializer,
                                           DatasetMetadataRecordSerializer,
                                           IsoCategorySerializer, LanguageSerializer,
                                           MetadataRelationSerializer, TimeExtentSerializer,
                                           KeywordSerializer,
                                           LicenceSerializer,
                                           MetadataContactSerializer,
                                           MimeTypeSerializer,
                                           ReferenceSystemDefaultSerializer,
                                           ReferenceSystemRetrieveSerializer,
                                           ServiceMetadataRecordSerializer,
                                           StyleSerializer)
from rest_framework_json_api.views import ModelViewSet, ReadOnlyModelViewSet


class MimeTypeSetMixin:
    queryset = MimeType.objects.all()
    serializer_class = MimeTypeSerializer
    filterset_fields = {
        'id': ['exact', 'icontains', 'contains', 'in'],
        "mime_type": ["exact", "icontains", "contains"],
    }
    search_fields = ("mime_type",)


class MimeTypeViewSet(
    MimeTypeSetMixin,
    ModelViewSet
):
    pass


class NestedMimeTypeViewSet(
    MimeTypeSetMixin,
    NestedModelViewSet
):
    pass


class KeywordViewSetMixin:
    # the pickers of the frontend render and sort by the display string the
    # serializer answers, which for a keyword is its text (#1035)
    queryset = Keyword.objects.annotate(string_representation=F("keyword"))
    serializer_class = KeywordSerializer
    filterset_fields = {
        'id': ['exact', 'icontains', 'contains', 'in'],
        "keyword": ["exact", "icontains", "contains"],
    }
    search_fields = ("keyword",)
    ordering_fields = ["id", "keyword", "string_representation"]


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


class LicenceViewSetMixin:
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


class ReferenceSystemViewSetMixin(SerializerClassesMixin):
    queryset = ReferenceSystem.objects.all()
    serializer_classes = {
        "default": ReferenceSystemDefaultSerializer,
        "retrieve": ReferenceSystemRetrieveSerializer,
    }
    filterset_fields = {
        'id': ['exact', 'icontains', 'contains', 'in'],
        "code": ["exact", "icontains", "contains"],
        "prefix": ["exact", "icontains", "contains"]
    }
    search_fields = ("id", "code", "prefix")


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


class StyleViewSetMixin:
    queryset = Style.objects.all().select_related("layer")
    serializer_class = StyleSerializer
    filterset_fields = {
        'id': ['exact', 'icontains', 'contains', 'in'],
        "name": ["exact", "icontains", "contains"],
        "title": ["exact", "icontains", "contains"],
    }
    search_fields = (
        "id",
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


# Non-included record relations only need their identifiers for JSON:API linkage.
METADATA_RECORD_PREFETCH_FOR_NOT_INCLUDES = {
    "harvested_through": [
        Prefetch(
            "harvested_through",
            queryset=CatalogueService.objects.only("id"),
        )
    ],
    "keywords": [
        Prefetch("keywords", queryset=Keyword.objects.only("id"))
    ],
    "reference_systems": [
        Prefetch(
            "reference_systems", queryset=ReferenceSystem.objects.only("id")
        )
    ],
    "time_extents": [
        Prefetch("time_extents", queryset=TimeExtent.objects.only("id"))
    ],
    "languages": [
        Prefetch("languages", queryset=Language.objects.only("value"))
    ],
}


class DatasetMetadataViewSetMixin(
    HistoryInformationViewSetMixin,
    PreloadNotIncludesMixin,
):
    # the vector of a record is what it is found by, not something this endpoint
    # answers, and postgres keeps it compressed: see registry/expressions/search.py
    queryset = DatasetMetadataRecord.objects \
        .select_related("licence") \
        .defer("search_vector")
    serializer_class = DatasetMetadataRecordSerializer
    filterset_class = DatasetMetadataRecordSpatialFilterSet
    # a record is searched by the words its vector holds -- the title, the abstract
    # and every keyword of it are tokenized into that column -- because matching it
    # is one probe into its GIN index. Searching the three texts instead asks a
    # UPPER(...) LIKE per word and joins the keyword relation of the whole
    # catalogue, which is where a searched list spent its time (#1029); see
    # registry/filters/search.py
    search_fields = ("search_vector",)
    ordering_fields = ["id", "title", "abstract", "hits", "date_stamp"]
    select_for_includes = {
        "metadata_contact": ["metadata_contact"],
        "licence": ["licence"],
        "dataset_contact": ["dataset_contact"],
        "selfPointingLayers.service": ["metadata_contact", "dataset_contact"],
        "selfPointingFeatureType.service": ["metadata_contact", "dataset_contact"],
    }
    prefetch_for_includes = {
        "categories": ["categories"],
        # "__all__": [],
        "self_pointing_layers.service": [
            Prefetch(
                "self_pointing_layers",
                queryset=Layer.objects.with_inherited_attributes_cte()
                .select_related(
                    "mptt_parent",
                    "mptt_tree",
                    "service",
                    "service__proxy_setting",
                ).prefetch_related(
                    "keywords",
                    "styles",
                    "reference_systems",
                    "registry_datasetmetadatarecord_metadata_records",
                    "service__layers",
                    "service__operation_urls",
                    "service__keywords",
                    "service__allowed_operations",
                ),
            ),
        ],
        "self_pointing_layers": [
            Prefetch(
                "self_pointing_layers",
                queryset=Layer.objects.with_inherited_attributes_cte()
                .select_related(
                    "mptt_parent",
                    "mptt_tree",
                    "service",
                ).prefetch_related(
                    "keywords",
                    "styles",
                    "reference_systems",
                    "registry_datasetmetadatarecord_metadata_records",
                ),
            ),
        ],
        "self_pointing_feature_types.service": [
            Prefetch(
                "self_pointing_feature_types",
                queryset=FeatureType.objects.select_related(
                    "service",
                    "service__proxy_setting",
                ).prefetch_related(
                    "keywords",
                    "reference_systems",
                    "registry_datasetmetadatarecord_metadata_records",
                    "service__feature_types",
                    "service__operation_urls",
                    "service__keywords",
                    "service__allowed_operations",
                ),
            )
        ],
        "self_pointing_feature_types": [
            Prefetch(
                "self_pointing_feature_types",
                queryset=FeatureType.objects.select_related(
                    "service",
                ).prefetch_related(
                    "keywords",
                    "reference_systems",
                    "registry_datasetmetadatarecord_metadata_records",
                ),
            )
        ],
        "harvested_through": [
            Prefetch(
                "harvested_through",
                queryset=CatalogueService.objects.prefetch_related(
                    "keywords",
                    "registry_datasetmetadatarecord_metadata_records",
                ),
            )
        ],
        "keywords": ["keywords"],
        "time_extents": ["time_extents"],
        "languages": ["languages"],
        "reference_systems": ["reference_systems"],
        # "operation_urls": [Prefetch("operation_urls", queryset=WebMapServiceOperationUrl.objects.select_related("service").prefetch_related("mime_types"))]
    }
    prefetch_for_not_includes = {
        "categories": [
            Prefetch("categories", queryset=IsoCategory.objects.only("value"))
        ],
        "self_pointing_layers": [
            Prefetch(
                "self_pointing_layers",
                queryset=Layer.objects.only(
                    "id",
                    "service_id",
                    "mptt_tree_id",
                    "mptt_lft",
                ),
            )
        ],
        "self_pointing_feature_types": [
            Prefetch(
                "self_pointing_feature_types",
                queryset=FeatureType.objects.only("id", "service_id"),
            )
        ],
        **METADATA_RECORD_PREFETCH_FOR_NOT_INCLUDES,
    }
    permission_classes = [DjangoObjectPermissionsOrAnonReadOnly]

    def get_queryset(self, *args, **kwargs):
        qs = super().get_queryset(*args, **kwargs)
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


class MetadataContactViewSetMixin:
    queryset = MetadataContact.objects.all()
    serializer_class = MetadataContactSerializer
    filterset_fields = {
        'id': ['exact', 'icontains', 'contains', 'in'],
        'name': ['exact', 'icontains', 'contains'],
        'person_name': ['exact', 'icontains', 'contains'],
        'email': ['exact', 'icontains', 'contains'],
        'phone': ['exact', 'icontains', 'contains'],
        'facsimile': ['exact', 'icontains', 'contains'],
        'city': ['exact', 'icontains', 'contains'],
        'postal_code': ['exact', 'icontains', 'contains'],
        'address_type': ['exact', 'icontains', 'contains'],
        'address': ['exact', 'icontains', 'contains'],
        'state_or_province': ['exact', 'icontains', 'contains'],
        'country': ['exact', 'icontains', 'contains'],
    }
    search_fields = (
        "id",
        "name",
        "person_name",
        "email",
        "phone",
        "facsimile",
        "city",
        "postal_code",
        "address_type",
        "address",
        "state_or_province",
        "country"
    )


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


class NestedServiceContactViewSet(
    MetadataContactViewSetMixin,
    NestedModelViewSet
):
    resource_name = 'ServiceContact'


class NestedDatasetContactViewSet(
    MetadataContactViewSetMixin,
    NestedModelViewSet
):
    resource_name = 'DatasetContact'


class NestedApplicationContactViewSet(
    MetadataContactViewSetMixin,
    NestedModelViewSet
):
    resource_name = 'ApplicationContact'


class ServiceMetadataViewSetMixin(
    HistoryInformationViewSetMixin,
    PreloadNotIncludesMixin
):
    # see DatasetMetadataViewSetMixin.queryset
    queryset = ServiceMetadataRecord.objects \
        .select_related("licence") \
        .defer("search_vector")
    serializer_class = ServiceMetadataRecordSerializer
    filterset_class = ServiceMetadataRecordSpatialFilterSet
    # see DatasetMetadataViewSetMixin.search_fields
    search_fields = ("search_vector",)
    ordering_fields = ["id", "title", "abstract", "hits", "date_stamp"]
    select_for_includes = {

        "metadata_contact": ["metadata_contact"],
        "licence": ["licence"],
    }
    prefetch_for_includes = {
        "harvested_through": [
            Prefetch(
                "harvested_through",
                queryset=CatalogueService.objects.prefetch_related("keywords"),
            )
        ],
        "keywords": ["keywords"],
        "time_extents": ["time_extents"],
        "languages": ["languages"],
        "reference_systems": ["reference_systems"],
        # "operation_urls": [Prefetch("operation_urls", queryset=WebMapServiceOperationUrl.objects.select_related("service").prefetch_related("mime_types"))]
    }
    prefetch_for_not_includes = {
        **METADATA_RECORD_PREFETCH_FOR_NOT_INCLUDES,
        "self_pointing_wms": [
            Prefetch(
                "self_pointing_wms",
                queryset=WebMapService.objects.only("id")
            )
        ],
        "self_pointing_wfs": [
            Prefetch(
                "self_pointing_wfs",
                queryset=WebFeatureService.objects.only("id")
            )
        ],
        "self_pointing_csw": [
            Prefetch(
                "self_pointing_csw",
                queryset=CatalogueService.objects.only("id")
            )
        ]
    }
    permission_classes = [DjangoObjectPermissionsOrAnonReadOnly]

    def get_queryset(self, *args, **kwargs):
        qs = super().get_queryset(*args, **kwargs)
        include = self.request.GET.get("include", None)
        if not include or "metadataContact" not in include:
            defer = [
                f"metadata_contact__{field.name}"
                for field in MetadataContact._meta.get_fields()
                if field.name not in ["id", "pk"]
            ]
            qs = qs.select_related("metadata_contact").defer(*defer)

        return qs


class ServiceMetadataViewSet(
        ServiceMetadataViewSetMixin,
        ModelViewSet
):
    pass


class NestedServiceMetadataViewSet(
    ServiceMetadataViewSetMixin,
    NestedModelViewSet
):
    pass


class ApplicationMetadataViewSetMixin(
    HistoryInformationViewSetMixin,
    PreloadNotIncludesMixin,
):
    # the application record mirrors the dataset record (see the model docstring of
    # registry.models.metadata.ApplicationMetadataRecord): the same answer of that
    # shape, with the providing contact named after the application
    queryset = ApplicationMetadataRecord.objects \
        .select_related("licence") \
        .defer("search_vector")
    serializer_class = ApplicationMetadataRecordSerializer
    filterset_class = ApplicationMetadataRecordSpatialFilterSet
    search_fields = ("title", "abstract", "keywords__keyword")
    ordering_fields = ["id", "title", "abstract", "hits", "date_stamp"]
    select_for_includes = {
        "metadata_contact": ["metadata_contact"],
        "licence": ["licence"],
        "application_contact": ["application_contact"],
    }
    prefetch_for_includes = {
        "categories": ["categories"],
        "harvested_through": [
            Prefetch(
                "harvested_through",
                queryset=CatalogueService.objects.prefetch_related(
                    "keywords",
                    "registry_applicationmetadatarecord_metadata_records",
                ),
            )
        ],
        "keywords": ["keywords"],
        "time_extents": ["time_extents"],
        "languages": ["languages"],
        "reference_systems": ["reference_systems"],
    }
    prefetch_for_not_includes = {
        "categories": [
            Prefetch("categories", queryset=IsoCategory.objects.only("value"))
        ],
        **METADATA_RECORD_PREFETCH_FOR_NOT_INCLUDES,
    }
    permission_classes = [DjangoObjectPermissionsOrAnonReadOnly]

    def get_queryset(self, *args, **kwargs):
        qs = super().get_queryset(*args, **kwargs)
        include = self.request.GET.get("include", None)
        if not include or "metadataContact" not in include:
            defer = [
                f"metadata_contact__{field.name}"
                for field in MetadataContact._meta.get_fields()
                if field.name not in ["id", "pk"]
            ]
            qs = qs.select_related("metadata_contact").defer(*defer)
        if not include or "applicationContact" not in include:
            defer = [
                f"application_contact__{field.name}"
                for field in MetadataContact._meta.get_fields()
                if field.name not in ["id", "pk"]
            ]
            qs = qs.select_related("application_contact").defer(*defer)

        return qs


class ApplicationMetadataViewSet(
        ApplicationMetadataViewSetMixin,
        ModelViewSet
):
    pass


class NestedApplicationMetadataViewSet(
    ApplicationMetadataViewSetMixin,
    NestedModelViewSet
):
    pass


class TimeExtentViewSet(ReadOnlyModelViewSet):
    # the annotation makes the display string of the serializer sortable, which
    # is the sort the generic pickers send when they render this resource (#1035)
    queryset = TimeExtent.objects.with_string_representation()
    serializer_class = TimeExtentSerializer
    ordering_fields = ["id", "begin", "end", "resolution", "is_relative",
                       "string_representation"]


class LanguageViewSet(ReadOnlyModelViewSet):
    queryset = Language.objects.with_label().annotate(id=F("value"))
    serializer_class = LanguageSerializer
    ordering_fields = ["id", "value", "label"]


class IsoCategoryViewSet(ReadOnlyModelViewSet):
    queryset = IsoCategory.objects.with_label().annotate(id=F("value"))
    serializer_class = IsoCategorySerializer
    ordering_fields = ["id", "value", "label"]


class MetadataRelationViewSet(PreloadNotIncludesMixin, ReadOnlyModelViewSet):
    queryset = MetadataRelation.objects.order_by("id")
    select_for_includes = {source: [source] for source in ("wms", "wfs", "csw", "feature_type")}
    prefetch_for_includes = {
        "layer": [Prefetch("layer", queryset=Layer.objects.with_inherited_attributes_cte())],
    }
    serializer_class = MetadataRelationSerializer
    filterset_fields = {
        "dataset_metadata": ["exact"],
        "service_metadata": ["exact"],
        "layer": ["isnull"],
        "feature_type": ["isnull"],
        "wms": ["isnull"],
        "wfs": ["isnull"],
        "csw": ["isnull"],
    }
    search_fields = ("layer__title", "feature_type__title", "wms__title", "wfs__title", "csw__title")
    ordering_fields = ["id", "origin", "is_internal"]
    permission_classes = [DjangoObjectPermissionsOrAnonReadOnly]
