from django.db.models import Exists, F, Prefetch, QuerySet
from django.db.models import Value as V
from django.db.models import Window
from django.db.models.expressions import F, OuterRef
from django.db.models.functions import Coalesce, RowNumber
from django.db.models.manager import Manager
from extras.managers import DefaultHistoryManager
from mptt2.managers import TreeManager
from registry import models
from registry.querys.service import LayerQuerySet
from simple_history.models import HistoricalRecords

SIBLING_INDEX = Coalesce(
    Window(
        expression=RowNumber(),
        partition_by=[F("mptt_parent")],
        order_by=F("mptt_lft").asc(),
    ) - 1,
    V(0),
)


class WebMapServiceQuerySet(QuerySet):
    def prefetch_whole_service(
        self,
    ) -> "WebMapServiceQuerySet":
        from registry.models.metadata import Style
        from registry.models.service import Layer
        styles_prefetch = Prefetch(
            "styles",
            Style.objects.select_related(
                "legend_url",
                "legend_url__mime_type"
            )
        )

        layer_prefetch = Prefetch(
            "layers",
            Layer.objects.select_related(
                "mptt_parent"
            ).prefetch_related(
                "keywords",
                "reference_systems",
                "time_extents",
                styles_prefetch
            ).annotate(
                sibling_index=SIBLING_INDEX
            )
        )

        return self.select_related(
            "service_contact",
            "metadata_contact"
        ).prefetch_related(
            "operation_urls",
            "keywords",
            layer_prefetch
        )

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
    pass
