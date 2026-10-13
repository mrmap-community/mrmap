from time import timezone

from django.db.models import (Exists, F, Manager, OuterRef, Prefetch, Q,
                              QuerySet, Value, Window)
from django.db.models.functions import Coalesce, RowNumber
from extras.managers import DefaultHistoryManager
from mptt2.managers import TreeManager
from registry import models
from registry.enums.update import UpdateJobStatusEnum
from registry.models.monitoring import (GetCapabilitiesProbeResult,
                                        WebMapServiceMonitoringRun)
from registry.models.update import (WebMapServiceUpdateJob,
                                    WebMapServiceUpdateSetting)
from registry.querys.service import LayerQuerySet

SIBLING_INDEX = Coalesce(
    Window(
        expression=RowNumber(),
        partition_by=[F("mptt_parent")],
        order_by=F("mptt_lft").asc(),
    ) - 1,
    Value(0),
)


class WebMapServiceQuerySet(QuerySet):
    def update_candidates(self):
        return self.filter(
            update_candidate_of__isnull=False
        )

    def real_services(self):
        return self.filter(
            update_candidate_of__isnull=True
        )

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
                F("proxy_setting__camouflage"), Value(False)),
            log_response=Coalesce(
                F("proxy_setting__log_response"), Value(False)),
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

    def with_alert_information(self):
        # small stand for example, how to determin alert information with queryset
        # The overdue check, can be done in python by prefetching the crontab schedule configurations and check them against overdue.
        self.annotate(

            has_blocking_update=Exists(
                WebMapServiceUpdateJob.objects.filter(
                    service_id=OuterRef("pk"),
                    status=UpdateJobStatusEnum.REVIEW_REQUIRED
                )
            ),
            has_failing_monitoring=Exists(
                GetCapabilitiesProbeResult.objects.filter(
                    Q(
                        Q(registry_getcapabilititesproberesult__check_response_is_valid_xml_success=False),
                        Q(registry_getcapabilititesproberesult__check_response_does_contain_success=False),
                        Q(registry_getcapabilititesproberesult__check_response_does_not_contain_success=False)
                    ),
                    setting__service_id=OuterRef("pk"),

                )
            ),
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
                F("proxy_setting__camouflage"), Value(False)),
            log_response=Coalesce(
                F("proxy_setting__log_response"), Value(False)),
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


class LayerManager(Manager.from_queryset(LayerQuerySet), DefaultHistoryManager, TreeManager):
    pass
