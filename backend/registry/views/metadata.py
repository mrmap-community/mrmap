from dataclasses import asdict

from django.http import JsonResponse
from drf_spectacular.utils import (OpenApiParameter, OpenApiTypes,
                                   extend_schema, extend_schema_view)
from rest_framework.decorators import action
from rest_framework.renderers import JSONRenderer
from registry.filters.metadata import DatasetMetadataRecordSpatialFilterSet, ServiceMetadataRecordSpatialFilterSet
from django.db.models.query import Prefetch
from extras.permissions import DjangoObjectPermissionsOrAnonReadOnly
from extras.viewsets import (HistoryInformationViewSetMixin, NestedModelViewSet, PreloadNotIncludesMixin,
                             SerializerClassesMixin)
from registry.helper.metadata_resolution import (resolve_record,
                                                 validate_capabilities_candidate)
from registry.models.metadata import (DatasetMetadataRecord, IsoCategory,
                                      Keyword, Language, Licence,
                                      MetadataContact, MetadataRelation, MimeType,
                                      ReferenceSystem, ServiceMetadataRecord,
                                      Style, TimeExtent)
from registry.models.service import (CatalogueService, FeatureType, Layer,
                                     WebFeatureService, WebMapService)
from registry.serializers.metadata import (DatasetMetadataRecordSerializer,
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


#: The resolution answers what the caller is allowed to see, so a shared
#: cache must not answer it for another user.
_NO_STORE = {"Cache-Control": "no-store"}


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
    queryset = Keyword.objects.all()
    serializer_class = KeywordSerializer
    filterset_fields = {
        'id': ['exact', 'icontains', 'contains', 'in'],
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


class MetadataResolutionViewSetMixin:
    """ Which services can deliver one metadata record.

        Both actions answer plain JSON instead of a JSON:API resource, because
        the answer is computed from the stored document and the derived
        coupling index and is not held by the registry - like the service
        previews of :mod:`registry.views.service`, which they mirror including
        ``filter_backends`` and the ``no-store`` header.

        Discovery performs no request at all; the validation asks one
        advertised endpoint with a bounded time and response size. Both
        enforce the view permission of the record through ``get_object``, like
        ``retrieve`` does, and never write to the registry: discovering a
        service is not registering one.
    """

    @classmethod
    def get_extra_actions(cls):
        actions = super().get_extra_actions()
        # Nested relationship viewsets inherit the metadata UI customizations,
        # but the resolution addresses only the canonical metadata endpoint.
        if issubclass(cls, NestedModelViewSet):
            return [item for item in actions if item.__name__ not in {
                "service_candidates", "validate_service_candidate"}]
        return actions

    @extend_schema(
        responses={200: OpenApiTypes.OBJECT},
        description="The endpoints which the stored document advertises to "
                    "access the described resource, each with its state, "
                    "source and evidence, plus the registered resources a "
                    "stored metadata relation already verified. Performs no "
                    "upstream request; the answer stays unvalidated until "
                    "validate-service-candidate is asked.",
    )
    @action(detail=True, methods=["get"], url_path="service-candidates",
            renderer_classes=[JSONRenderer], filter_backends=[])
    def service_candidates(self, request, *args, **kwargs):
        resolution = resolve_record(self.get_object(), request.user)
        return JsonResponse(asdict(resolution), headers=_NO_STORE)

    @extend_schema(
        parameters=[OpenApiParameter(
            "url", OpenApiTypes.STR, required=True,
            description="The candidate url as service-candidates answered it."
        )],
        responses={200: OpenApiTypes.OBJECT, 400: OpenApiTypes.OBJECT,
                   422: OpenApiTypes.OBJECT},
        description="Ask one advertised capabilities endpoint, once, in an "
                    "anonymous session with a bounded time and response size, "
                    "and confirm the layer and feature type hints of the "
                    "record against its answer. Only a url which this record "
                    "advertised is ever asked; anything else is refused with "
                    "422 without a request. Credentials of the caller are "
                    "never forwarded.",
    )
    @action(detail=True, methods=["get"], url_path="validate-service-candidate",
            renderer_classes=[JSONRenderer], filter_backends=[])
    def validate_service_candidate(self, request, *args, **kwargs):
        record = self.get_object()
        url = request.query_params.get("url", "")
        if not url:
            return JsonResponse({"error": "url-required"}, status=400,
                                headers=_NO_STORE)
        resolution = resolve_record(record, request.user)
        candidate = next((
            candidate for candidate in resolution.candidates
            if url in (candidate.url, candidate.original_url)), None)
        if candidate is None:
            # Only what the record itself advertised may be asked; this is
            # what keeps the endpoint from becoming an open proxy.
            return JsonResponse({"error": "not-advertised"}, status=422,
                                headers=_NO_STORE)
        result = validate_capabilities_candidate(candidate, url)
        return JsonResponse({"url": url, **asdict(result)}, headers=_NO_STORE)


class DatasetMetadataViewSetMixin(
    HistoryInformationViewSetMixin,
    PreloadNotIncludesMixin,
    MetadataResolutionViewSetMixin,
):
    queryset = DatasetMetadataRecord.objects.select_related("licence")
    serializer_class = DatasetMetadataRecordSerializer
    filterset_class = DatasetMetadataRecordSpatialFilterSet
    search_fields = ("title", "abstract", "keywords__keyword")
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


@extend_schema_view(
    service_candidates=extend_schema(
        operation_id="service_candidates_DatasetMetadataRecord"),
    validate_service_candidate=extend_schema(
        operation_id="validate_service_candidate_DatasetMetadataRecord"),
)
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


class ServiceMetadataViewSetMixin(
    HistoryInformationViewSetMixin,
    PreloadNotIncludesMixin,
    MetadataResolutionViewSetMixin
):
    queryset = ServiceMetadataRecord.objects.select_related("licence")
    serializer_class = ServiceMetadataRecordSerializer
    filterset_class = ServiceMetadataRecordSpatialFilterSet
    search_fields = ("title", "abstract", "keywords__keyword")
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


@extend_schema_view(
    service_candidates=extend_schema(
        operation_id="service_candidates_ServiceMetadataRecord"),
    validate_service_candidate=extend_schema(
        operation_id="validate_service_candidate_ServiceMetadataRecord"),
)
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


class TimeExtentViewSet(ReadOnlyModelViewSet):
    queryset = TimeExtent.objects.all()
    serializer_class = TimeExtentSerializer


class LanguageViewSet(ReadOnlyModelViewSet):
    queryset = Language.objects.all()
    serializer_class = LanguageSerializer


class IsoCategoryViewSet(ReadOnlyModelViewSet):
    queryset = IsoCategory.objects.all()
    serializer_class = IsoCategorySerializer


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
