from abc import ABC

from django.db import models
from django.db.models import Exists, OuterRef
from django.db.models.query_utils import Q


class WebMapServiceMonitoringRunQuerySet(ABC, models.QuerySet):

    def with_is_successful(self):
        from registry.models.monitoring import (GetCapabilitiesProbeResult,
                                                GetMapProbeResult)

        return (
            self.annotate(
                is_get_capabilities_failed=Exists(
                    GetCapabilitiesProbeResult.objects.filter(
                        Q(check_response_is_valid_xml_success=False) |
                        Q(check_response_is_valid_xml_message=False) |
                        Q(check_response_does_not_contain_success=False) |
                        Q(check_response_does_contain_success=False),
                        run=OuterRef("pk"),
                    )
                ),
                is_get_map_failed=Exists(
                    GetMapProbeResult.objects.filter(
                        Q(check_response_image_success=False) |
                        Q(check_response_does_not_contain_success=False),
                        run=OuterRef("pk"),
                    )
                )
            ).annotate(
                success=Q(
                    is_get_capabilities_failed=False,
                    is_get_map_failed=False,
                )
            )
        )


class WebMapServiceMonitoringRunManager(models.Manager.from_queryset(WebMapServiceMonitoringRunQuerySet)):
    def with_success(self):
        return self.get_queryset().with_is_successful()
