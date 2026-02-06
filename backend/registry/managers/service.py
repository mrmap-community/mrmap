from django.db.models import Exists, F, Prefetch, QuerySet
from django.db.models import Value as V
from django.db.models import Window
from django.db.models.expressions import F, OuterRef
from django.db.models.functions import Coalesce, RowNumber
from django.db.models.manager import Manager
from extras.managers import DefaultHistoryManager
from extras.utils import build_queryset, merge_spec_auto
from mptt2.managers import TreeManager
from registry import models
from registry.querys.service import LayerQuerySet
from simple_history.models import HistoricalRecords

PREFETCH_SPEC = {
    "select": ["service_contact", "metadata_contact"],
    "prefetch": {
        "operation_urls": {},
        "keywords": {},
        "layers": {
            "model": "registry.Layer",
            "select": [],
            "prefetch": {
                "keywords": {},
                "reference_systems": {},
                "time_extents": {},
                "styles": {
                    "model": "registry.Style",
                    "select": ["legend_url", "legend_url__mime_type"],
                },
            },
            "annotate": {
                "sibling_index": Window(
                    expression=RowNumber(),
                    partition_by=[F("mptt_parent")],
                    order_by=F("mptt_lft").asc(),
                ) - 1

            },
        },
    },

}

SIBLING_INDEX_DEFINITION = Window(
    expression=RowNumber(),
    partition_by=[F("mptt_parent")],
    order_by=F("mptt_lft").asc(),
) - 1

SIBLING_INDEX_SPEC = {
    "prefetch": {
        "layers": {
            # "select": ["mptt_parent"],
            "annotate": {
                "sibling_index": SIBLING_INDEX_DEFINITION
            },
            "prefetch": {
                "mptt_parent": {
                    "model": "registry.Layer",
                    "annotate": {
                        "sibling_index": SIBLING_INDEX_DEFINITION
                    }
                }
            }
        }
    }
}


class WebMapServiceQuerySet(QuerySet):
    def prefetch_whole_service(
        self,
        prefetch_spec: dict | None = None,
        with_sibling_index: bool = False,
    ) -> "WebMapServiceQuerySet":
        """
        Prefetch and select all related objects required to efficiently
        load a complete Web Map Service hierarchy, optionally adding
        annotations such as a sibling index for hierarchical layers.

        This method applies a declarative prefetch specification to the
        queryset, allowing fine-grained control over which related
        objects are fetched via ``select_related`` and ``prefetch_related``.
        Nested relations and custom querysets are supported.

        By default, a canonical ``PREFETCH_SPEC`` is used. Callers may
        extend or override it by passing a partial ``prefetch_spec``
        dictionary. Only specified keys are overridden; all unspecified
        relations fall back to the defaults.

        Additionally, setting ``with_sibling_index=True`` annotates
        all layers with a ``sibling_index`` field, calculated using
        a SQL window function (RowNumber) partitioned by ``parent_id``
        and ordered by the MPTT left value. This is useful for
        efficiently accessing the position of a layer among its siblings.

        Args:
            prefetch_spec (dict, optional):
                A partial prefetch specification used to extend or override
                the default behavior. Supports nested ``select``,
                ``prefetch``, and ``annotate`` keys.
            with_sibling_index (bool, optional):
                If True, adds a ``sibling_index`` annotation to each layer,
                representing its zero-based position among sibling layers.

        Returns:
            WebMapServiceQuerySet:
                A queryset with all configured relations eagerly loaded,
                and annotations applied if requested.

        Example:
            # Default prefetch
            >>> WebMapService.objects.prefetch_whole_service()

            # Prefetch with sibling index annotation
            >>> WebMapService.objects.prefetch_whole_service(
            ...     with_sibling_index=True
            ... )

            # Prefetch with sibling index and custom select override
            >>> WebMapService.objects.prefetch_whole_service(
            ...     with_sibling_index=True,
            ...     prefetch_spec={
            ...         "prefetch": {
            ...             "layers": {
            ...                 "select": ["mptt_parent"],
            ...             }
            ...         }
            ...     }
            ... )
        """
        spec = (
            merge_spec_auto(PREFETCH_SPEC, prefetch_spec)
            if prefetch_spec
            else PREFETCH_SPEC
        )

        if with_sibling_index:
            spec = merge_spec_auto(spec, SIBLING_INDEX_SPEC)

        return build_queryset(self, spec)

    def with_security_information(self) -> "WebMapServiceQuerySet":
        return self.annotate(
            camouflage=Coalesce(
                F("proxy_setting__camouflage"), V(False)),
            log_response=Coalesce(
                F("proxy_setting__log_response"), V(False)),
            is_secured=Exists(
                models.AllowedWebMapServiceOperation.objects.filter(
                    secured_service__id__exact=OuterRef("pk"),
                )
            ),
            is_spatial_secured=Exists(
                models.AllowedWebMapServiceOperation.objects.filter(
                    secured_service__id__exact=OuterRef("pk"),
                    allowed_area__isnull=False
                )
            )
        )


class WebFeatureServiceQuerySet(QuerySet):
    def prefetch_whole_service(self) -> "WebFeatureServiceQuerySet":
        featuretypes = Prefetch(
            "featuretypes",
            queryset=models.FeatureType.objects.prefetch_related(
                "keywords", "output_formats", "reference_systems"),
        )
        return self.select_related("service_contact", "metadata_contact").prefetch_related(
            "operation_urls__mime_types", "keywords", featuretypes
        )

    def with_security_information(self) -> "WebFeatureServiceQuerySet":
        return self.annotate(
            camouflage=Coalesce(
                F("proxy_setting__camouflage"), V(False)),
            log_response=Coalesce(
                F("proxy_setting__log_response"), V(False)),
            is_secured=Exists(
                models.AllowedWebFeatureServiceOperation.objects.filter(
                    secured_service__id__exact=OuterRef("pk"),
                )
            ),
            is_spatial_secured=Exists(
                models.AllowedWebFeatureServiceOperation.objects.filter(
                    secured_service__id__exact=OuterRef("pk"),
                    allowed_area__isnull=False
                )
            )
        )


class CatalogueServiceQuerySet(QuerySet):
    def prefetch_whole_service(self) -> "CatalogueServiceQuerySet":
        return self.select_related("service_contact", "metadata_contact").prefetch_related(
            "operation_urls__mime_types", "keywords"
        )


class CatalogueServiceManager(Manager.from_queryset(CatalogueServiceQuerySet), Manager.from_queryset(DefaultHistoryManager)):
    pass


class FeatureTypeElementXmlManager(Manager):

    def _reset_local_variables(self, **kwargs):
        # bulk_create will not call the default save() of CommonInfo model. So we need to set the attributes manual. We
        # collect them once.
        if hasattr(HistoricalRecords.context, "request") and hasattr(HistoricalRecords.context.request, "user"):
            self.current_user = HistoricalRecords.context.request.user

    def create_from_parsed_xml(self, parsed_xml, related_object, *args, **kwargs):
        self._reset_local_variables(**kwargs)

        db_element_list = []
        for element in parsed_xml.elements:
            db_element_list.append(self.model(feature_type=related_object,
                                              *args,
                                              **element.get_field_dict()))
        return self.model.objects.bulk_create(objs=db_element_list)


class LayerManager(Manager.from_queryset(LayerQuerySet), DefaultHistoryManager, TreeManager):
    pass
