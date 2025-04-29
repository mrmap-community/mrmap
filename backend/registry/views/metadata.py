from django.db.models.query import Prefetch
from extras.permissions import DjangoObjectPermissionsOrAnonReadOnly
from extras.viewsets import (NestedModelViewSet, PreloadNotIncludesMixin,
                             SerializerClassesMixin)
from registry.models.metadata import (DatasetMetadataRecord, Keyword, Licence,
                                      MetadataContact, ReferenceSystem,
                                      ServiceMetadataRecord, Style)
from registry.models.service import (CatalogueService, FeatureType, Layer,
                                     WebFeatureService, WebMapService)
from registry.serializers.metadata import (DatasetMetadataRecordSerializer,
                                           KeywordSerializer,
                                           LicenceSerializer,
                                           MetadataContactSerializer,
                                           ReferenceSystemDefaultSerializer,
                                           ReferenceSystemRetrieveSerializer,
                                           ServiceMetadataRecordSerializer,
                                           StyleSerializer)
from rest_framework_json_api.views import ModelViewSet


class KeywordViewSetMixin():
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


class LicenceViewSetMixin():
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


class StyleViewSetMixin():
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


class DatasetMetadataViewSetMixin(
    PreloadNotIncludesMixin,
):
    queryset = DatasetMetadataRecord.objects.all()
    serializer_class = DatasetMetadataRecordSerializer
    filterset_fields = {
        'id': ['exact', 'icontains', 'contains', 'in'],
        "title": ["exact", "icontains", "contains"],
        "abstract": ["exact", "icontains", "contains"],
        "keywords__keyword": ["exact", "icontains", "contains"],
        "harvested_dataset_metadata_relation__harvesting_job": ["exact"],
        "harvested_dataset_metadata_relation__collecting_state": ["exact"],
        # "harvested_by": ['exact', 'icontains', 'contains', 'in'],
        # "harvested_by__background_process__started_at": ['gte', 'lte', 'exact', 'gt', 'lt', 'range'],
        # "ignored_by": ['exact', 'icontains', 'contains', 'in'],
        # "updated_by": ['exact', 'icontains', 'contains', 'in'],
        # "updated_by__background_process__started_at": ['gte', 'lte', 'exact', 'gt', 'lt', 'range'],
    }
    search_fields = ("title", "abstract", "keywords__keyword")
    ordering_fields = ["id", "title", "abstract", "hits", "date_stamp"]
    select_for_includes = {
        "metadata_contact": ["metadata_contact"],
        "dataset_contact": ["dataset_contact"],
        "selfPointingLayers.service": ["metadata_contact", "dataset_contact"],
        "selfPointingFeatureType.service": ["metadata_contact", "dataset_contact"],
    }
    prefetch_for_includes = {
        # "__all__": [],
        "selfPointingLayers.service": [
            Prefetch(
                "self_pointing_layers",
                queryset=Layer.objects.with_inherited_attributes()
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
        "selfPointingLayers": [
            Prefetch(
                "self_pointing_layers",
                queryset=Layer.objects.with_inherited_attributes()
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
        "selfPointingFeatureTypes.service": [
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
        "selfPointingFeatureTypes": [
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
        "harvestedThrough": [
            Prefetch(
                "harvested_through",
                queryset=CatalogueService.objects.prefetch_related(
                    "keywords",
                    "registry_datasetmetadatarecord_metadata_records",
                ),
            )
        ],
        "keywords": ["keywords"],
        "referenceSystems": ["reference_systems"],
        # "operation_urls": [Prefetch("operation_urls", queryset=WebMapServiceOperationUrl.objects.select_related("service").prefetch_related("mime_types"))]
    }
    prefetch_for_not_includes = {
        "selfPointingLayers": [
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
        "selfPointingFeatureTypes": [
            Prefetch(
                "self_pointing_feature_types",
                queryset=FeatureType.objects.only("id", "service_id"),
            )
        ],
        "harvestedThrough": [
            Prefetch(
                "harvested_through",
                queryset=CatalogueService.objects.only("id"),
            )
        ],
        "keywords": [
            Prefetch("keywords", queryset=Keyword.objects.only("id"))
        ],
        "referenceSystems": [
            Prefetch(
                "reference_systems", queryset=ReferenceSystem.objects.only("id")
            )
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


class ServiceContactViewSet(
    MetadataContactViewSetMixin,
    ModelViewSet
):
    resource_name = 'ServiceContact'
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


class NestedDatasetContactViewSet(
    MetadataContactViewSetMixin,
    NestedModelViewSet
):
    resource_name = 'DatasetContact'


class ServiceMetadataViewSetMixin(
    PreloadNotIncludesMixin
):
    queryset = ServiceMetadataRecord.objects.all()
    serializer_class = ServiceMetadataRecordSerializer
    filterset_fields = {
        'id': ['exact', 'icontains', 'contains', 'in'],
        "title": ["exact", "icontains", "contains"],
        "abstract": ["exact", "icontains", "contains"],
        "keywords__keyword": ["exact", "icontains", "contains"],
        "harvested_service_metadata_relation__harvesting_job": ["exact"],
        "harvested_service_metadata_relation__collecting_state": ["exact"],
    }
    search_fields = ("title", "abstract", "keywords__keyword")
    ordering_fields = ["id", "title", "abstract", "hits", "date_stamp"]
    select_for_includes = {

        "metadata_contact": ["metadata_contact"],
    }
    prefetch_for_includes = {
        "harvestedThrough": [
            Prefetch(
                "harvested_through",
                queryset=CatalogueService.objects.prefetch_related("keywords"),
            )
        ],
        "keywords": ["keywords"],
        "referenceSystems": ["reference_systems"],
        # "operation_urls": [Prefetch("operation_urls", queryset=WebMapServiceOperationUrl.objects.select_related("service").prefetch_related("mime_types"))]
    }
    prefetch_for_not_includes = {
        "harvestedThrough": [
            Prefetch(
                "harvested_through",
                queryset=CatalogueService.objects.only("id"),
            )
        ],
        "keywords": [
            Prefetch("keywords", queryset=Keyword.objects.only("id"))
        ],
        "referenceSystems": [
            Prefetch(
                "reference_systems", queryset=ReferenceSystem.objects.only("id")
            )
        ],
        "selfPointingLayers": [
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
        "selfPointingFeatureTypes": [
            Prefetch(
                "self_pointing_feature_types",
                queryset=FeatureType.objects.only("id", "service_id"),
            )
        ],
        "selfPointingWms": [
            Prefetch(
                "self_pointing_wms",
                queryset=WebMapService.objects.only("id")
            )
        ],
        "selfPointingWfs": [
            Prefetch(
                "self_pointing_wfs",
                queryset=WebFeatureService.objects.only("id")
            )
        ],
        "selfPointingCsw": [
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
