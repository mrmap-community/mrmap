from typing import Any

from django.contrib.auth.models import Group
from django.contrib.gis.db.models import Union
from django.contrib.postgres.aggregates import ArrayAgg
from django.db import models
from django.db.models import (BooleanField, Exists, ExpressionWrapper, F,
                              OuterRef, QuerySet)
from django.db.models import Value as V
from django.db.models.expressions import Value
from django.db.models.functions import Coalesce
from django.http import HttpRequest
from ows_client.request_builder import WebService
from registry.enums.service import HttpMethodEnum, OGCOperationEnum
from registry.settings import SECURE_ABLE_OPERATIONS_LOWER


class AllowedWebMapServiceOperationQuerySet(models.QuerySet):
    def filter_qs_by_secured_element(self, request):
        dummy_service = WebService.manufacture_service(request.get_full_path())
        layer_identifiers = dummy_service.get_requested_layers(
            query_params=request.query_parameters
        )
        return self.filter(
            secured_layers__identifier__iregex=r"%s"
            % f"({'|'.join(layer_identifiers)})"
        )

    def find_all_allowed_areas_by_request(self, service_pk, request: HttpRequest):
        return (
            self.filter(secured_service__pk=service_pk,
                        allowed_area__isnull=False)
            .filter_qs_by_secured_element(request=request)
            .for_user(service_pk=service_pk, request=request)
        )

    def find_all_empty_allowed_areas_by_request(self, service_pk, request: HttpRequest):
        return (
            self.filter(secured_service__pk=service_pk,
                        allowed_area__isnull=True)
            .filter_qs_by_secured_element(request=request)
            .for_user(service_pk=service_pk, request=request)
        )

    def is_service_secured(self, service_pk) -> Exists:
        return Exists(self.filter(secured_service__pk=service_pk))

    def is_spatial_secured(self, service_pk, request: HttpRequest) -> ExpressionWrapper:
        return ExpressionWrapper(
            Exists(
                self.find_all_allowed_areas_by_request(
                    service_pk=service_pk, request=request
                )
            )
            and ~Exists(
                self.find_all_empty_allowed_areas_by_request(
                    service_pk=service_pk, request=request
                )
            ),
            output_field=BooleanField(),
        )

    def is_spatial_secured_and_covers(self, service_pk, request: HttpRequest) -> Exists:
        return Exists(
            self.filter(
                secured_service__pk=service_pk,
                allowed_area__covers=request.bbox,
            )
        )

    def is_spatial_secured_and_intersects(
        self, service_pk, request: HttpRequest
    ) -> Exists:
        return Exists(
            self.filter(
                secured_service__pk=service_pk,
                allowed_area__intersects=request.bbox,
            )
        )

    def for_user(self, service_pk, request: HttpRequest):
        return self.filter(
            secured_service__pk=service_pk,
            allowed_groups=None,
            operations__operation__iexact=request.query_parameters.get(
                "request"),
        ) | self.filter(
            secured_service__pk=service_pk,
            allowed_groups__pk__in=Group.objects.filter(
                user__username="AnonymouseUser"
            ).values_list("pk", flat=True)
            if request.user.is_anonymous
            else request.user.groups.values_list("pk", flat=True),
            operations__operation__iexact=request.query_parameters.get(
                "request"),
        )

    def is_user_entitled(self, service_pk, request: HttpRequest) -> Exists:
        """checks if the user of the request is member of any AllowedOperation object"""
        if request.user.is_superuser:
            return Value(True)
        return Exists(self.for_user(service_pk=service_pk, request=request))

    def get_allowed_areas(self, service_pk, request: HttpRequest) -> QuerySet:
        return self.find_all_allowed_areas_by_request(
            service_pk=service_pk, request=request)


class WebMapServiceOperationUrlQuerySet(models.QuerySet):
    def get_base_url(self, service_pk, request: HttpRequest) -> str:
        return self.filter(
            service=service_pk,
            method=HttpMethodEnum.GET.value,
            operation__iexact=request.query_parameters.get("request"),
        ).values_list("url", flat=True)[:1]

    def get_fallback_url(self, service_pk) -> str:
        return self.filter(
            service=service_pk,
            method=HttpMethodEnum.GET.value,
        ).values_list("url", flat=True)[:1]


class WebMapServiceSecurityManager(models.Manager):
    request = None

    def get_allowed_operation_qs(self) -> AllowedWebMapServiceOperationQuerySet:
        from registry.models.security import \
            AllowedWebMapServiceOperation  # to avoid circular import

        return AllowedWebMapServiceOperationQuerySet(
            model=AllowedWebMapServiceOperation,
            using=self._db,
        )

    def get_operation_url_qs(self) -> WebMapServiceOperationUrlQuerySet:
        from registry.models.service import \
            WebMapServiceOperationUrl  # to avoid circular import

        return WebMapServiceOperationUrlQuerySet(
            model=WebMapServiceOperationUrl,
            using=self._db,
        )

    def prepare_with_security_info(self):
        if (
            self.request.query_parameters.get("request").lower()
            == OGCOperationEnum.GET_CAPABILITIES.value.lower()
        ):
            return self.get_queryset().annotate(
                camouflage=Coalesce(F("proxy_setting__camouflage"), V(False)),
                base_operation_url=self.get_operation_url_qs().get_base_url(
                    service_pk=OuterRef("pk"), request=self.request
                ),
                unknown_operation_url=self.get_operation_url_qs().get_fallback_url(
                    service_pk=OuterRef("pk")
                ),
            )
        elif (
            self.request.query_parameters.get("request").lower()
            not in SECURE_ABLE_OPERATIONS_LOWER
        ):
            return self.get_queryset().annotate(
                log_response=Coalesce(
                    F("proxy_setting__log_response"), V(False)),
                base_operation_url=self.get_operation_url_qs().get_base_url(
                    service_pk=OuterRef("pk"), request=self.request
                ),
                unknown_operation_url=self.get_operation_url_qs().get_fallback_url(
                    service_pk=OuterRef("pk")
                ),
            )
        else:
            return (
                self.get_queryset()
                .select_related("auth")
                .annotate(
                    camouflage=Coalesce(
                        F("proxy_setting__camouflage"), V(False)),
                    log_response=Coalesce(
                        F("proxy_setting__log_response"), V(False)),
                    is_spatial_secured=self.get_allowed_operation_qs().is_spatial_secured(
                        service_pk=OuterRef("pk"), request=self.request
                    ),
                    is_secured=self.get_allowed_operation_qs().is_service_secured(
                        service_pk=OuterRef("pk")
                    ),
                    is_user_principle_entitled=self.get_allowed_operation_qs().is_user_entitled(
                        service_pk=OuterRef("pk"), request=self.request
                    ),
                    is_spatial_secured_and_covers=self.get_allowed_operation_qs().is_spatial_secured_and_covers(
                        service_pk=OuterRef("pk"), request=self.request
                    ),
                    is_spatial_secured_and_intersects=self.get_allowed_operation_qs().is_spatial_secured_and_intersects(
                        service_pk=OuterRef("pk"), request=self.request
                    ),
                    allowed_area_union=self.get_allowed_operation_qs().get_allowed_areas(
                        service_pk=OuterRef("pk"), request=self.request
                    ).values('secured_service__pk').annotate(geom=Union('allowed_area')).values('geom'),
                    allowed_area_pks=self.get_allowed_operation_qs().get_allowed_areas(
                        service_pk=OuterRef("pk"), request=self.request
                    ).values('secured_service__pk').annotate(pks=ArrayAgg('pk')).values('pks'),
                    base_operation_url=self.get_operation_url_qs().get_base_url(
                        service_pk=OuterRef("pk"), request=self.request
                    ),
                    unknown_operation_url=self.get_operation_url_qs().get_fallback_url(
                        service_pk=OuterRef("pk")
                    ),
                )
            )

    def get_with_security_info(self, request: HttpRequest, *args: Any, **kwargs: Any):
        service = None
        self.request = request
        service = self.prepare_with_security_info().get(*args, **kwargs)

        return service
