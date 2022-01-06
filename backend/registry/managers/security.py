from typing import Any

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.contrib.gis.db.models import Union
from django.contrib.gis.geos.geometry import GEOSGeometry
from django.core.exceptions import ObjectDoesNotExist
from django.db import models
from django.db.models import (BooleanField, Exists, ExpressionWrapper, F,
                              OuterRef, Q, QuerySet)
from django.db.models import Value as V
from django.db.models.expressions import Value
from django.db.models.functions import Coalesce
from django.db.models.query import Prefetch
from django.http import HttpRequest
from ows_client.request_builder import WebService, WfsService, WmsService
from registry.enums.service import HttpMethodEnum, OGCOperationEnum
from registry.settings import SECURE_ABLE_OPERATIONS_LOWER


class AllowedWebMapServiceOperationQuerySet(models.QuerySet):

    def __init__(self, service_pk, request: HttpRequest, *args, **kwargs) -> None:
        self.service_pk = service_pk
        self.request = request
        super().__init__(*args, **kwargs)

    def filter_qs_by_secured_element(self) -> QuerySet:
        dummy_service = WebService.manufacture_service(
            self.request.get_full_path())
        layer_identifiers = dummy_service.get_requested_layers(
            query_params=self.request.query_parameters)
        return self.filter(secured_layers__identifier__iregex=r'%s' %
                           f"({'|'.join(layer_identifiers)})")

    def find_all_allowed_areas_by_request(self) -> QuerySet:
        # TODO: filter also by requesting user; otherwise allowed operations without user restriction will returned
        return self.filter(
            secured_service__pk=self.service_pk,
            allowed_area__isnull=False
        ).filter_qs_by_secured_element()

    def find_all_empty_allowed_areas_by_request(self) -> QuerySet:
        # TODO: filter also by requesting user; otherwise allowed operations without user restriction will returned
        return self.filter(
            secured_service__pk=self.service_pk,
            allowed_area__isnull=True
        ).filter_qs_by_secured_element()

    def is_spatial_secured_and_intersects(self, geom: GEOSGeometry) -> Exists:
        return Exists(self.filter(
            secured_service__pk=self.service_pk,
            allowed_area__intersects=geom
        ))

    def is_service_secured(self) -> Exists:
        return Exists(self.filter(
            secured_service__pk=self.service_pk
        ))

    def is_spatial_secured(self):
        return ExpressionWrapper(Exists(self.find_all_allowed_areas_by_request()) and
                                 ~Exists(
                                     self.find_all_empty_allowed_areas_by_request()),
                                 output_field=BooleanField())

    def is_spatial_secured_and_covers(self) -> Exists:
        return Exists(self.get_queryset().filter(
            secured_service__pk=self.service_pk,
            allowed_area__covers=self.request.bbox
        ))

    def is_spatial_secured_and_intersects(self) -> Exists:
        return Exists(self.get_queryset().filter(
            secured_service__pk=self.service_pk,
            allowed_area__intersects=self.request.bbox
        ))

    def is_user_entitled(self) -> Exists:
        """checks if the user of the request is member of any AllowedOperation object"""
        if self.request.user.is_superuser:
            return Value(True)
        anonymous_user_groups_subquery = Group.objects.filter(user=get_user_model(
        ).objects.get(username="AnonymousUser")).values_list("pk", flat=True)
        user_groups_subquery = self.request.user.groups.values_list(
            "pk", flat=True)
        user_is_principle_entitled_subquery = self.filter(
            secured_service__pk=self.service_pk,
            allowed_groups__pk__in=user_groups_subquery | anonymous_user_groups_subquery,
            operations__operation__iexact=self.request.query_parameters.get(
                "request")
        )
        return Exists(user_is_principle_entitled_subquery)

    def allowed_area_union(self) -> Union:
        return Union(self.find_all_allowed_areas_by_request().distinct("pk").values_list("allowed_area", flat=True))


class WebMapServiceOperationUrlQuerySet(models.QuerySet):

    def __init__(self, service_pk, request: HttpRequest, *args, **kwargs) -> None:
        self.service_pk = service_pk
        self.request = request
        super().__init__(*args, **kwargs)

    def get_base_url(self) -> str:
        return self.filter(
            service=self.service_pk,
            method=HttpMethodEnum.GET.value,
            operation__iexact=self.request.query_parameters.get("request")
        ).values_list('url', flat=True)[:1]

    def get_fallback_url(self) -> str:
        return self.get_queryset().filter(
            service=self.service_pk,
            method=HttpMethodEnum.GET.value,
        ).values_list('url', flat=True)[:1]


class WebMapServiceSecurityManager(models.Manager):

    def get_allowed_operation_qs(self, service_pk) -> QuerySet:
        from registry.models.security import \
            AllowedWebMapServiceOperation  # to avoid circular import

        # TODO: pass service pk
        return AllowedWebMapServiceOperationQuerySet(service_pk=service_pk, model=AllowedWebMapServiceOperation, using=self._db)

    def get_operation_url_qs(self, service_pk) -> QuerySet:
        from registry.models.service import \
            WebMapServiceOperationUrl  # to avoid circular import

        # TODO: pass service pk
        return WebMapServiceOperationUrlQuerySet(service_pk=service_pk, model=WebMapServiceOperationUrl, using=self._db)

    def prepare_with_security_info(self, request: HttpRequest) -> QuerySet:
        if request.query_parameters.get("request").lower() == OGCOperationEnum.GET_CAPABILITIES.value.lower():
            return self.get_queryset() \
                .annotate(camouflage=Coalesce(F("proxy_setting__camouflage"), V(False)),
                          base_operation_url=self.get_operation_url_qs().get_base_url(
                              request=request),
                          unknown_operation_url=self.get_operation_url_qs().get_fallback_url())
        elif request.query_parameters.get("request").lower() not in SECURE_ABLE_OPERATIONS_LOWER:
            return self.get_queryset() \
                .annotate(log_response=Coalesce(F("proxy_setting__log_response"), V(False)),
                          base_operation_url=self.get_operation_url_qs().get_base_url(
                              request=request),
                          unknown_operation_url=self.get_operation_url_qs().get_fallback_url())
        else:
            return self.get_queryset().select_related("auth",) \
                .annotate(camouflage=Coalesce(F("proxy_setting__camouflage"), V(False)),
                          log_response=Coalesce(
                              F("proxy_setting__log_response"), V(False)),
                          is_spatial_secured=self.get_allowed_operation_qs(service_pk=OuterRef('pk')).is_spatial_secured(
                              request=request),
                          is_secured=self.get_allowed_operation_qs(
                              service_pk=OuterRef('pk')).is_service_secured(),
                          user_is_principle_entitled=self.get_allowed_operation_qs(service_pk=OuterRef('pk')).is_user_entitled(
                              request=request),
                          base_operation_url=self.get_operation_url_qs().get_base_url(
                              request=request),
                          unknown_operation_url=OperationUrl.security_objects.get_fallback_url(),
                          is_spatial_secured_and_covers=self.get_allowed_operation_qs(service_pk=OuterRef('pk')).is_spatial_secured_and_covers(
                              request=request),
                          is_spatial_secured_and_intersects=self.get_allowed_operation_qs(service_pk=OuterRef('pk')).is_spatial_secured_and_intersects(
                              request=request),
                          allowed_area_united=self.get_allowed_operation_qs(service_pk=OuterRef('pk')).allowed_area_union(request=request))

    def get_with_security_info(self, request: HttpRequest, *args: Any, **kwargs: Any):
        service = None
        self.dummy_remote_service = WebService.manufacture_service(
            request.get_full_path())
        try:
            service_qs = self.prepare_with_security_info(
                request=request)
            if request.query_parameters.get("request").lower() in SECURE_ABLE_OPERATIONS_LOWER:

                if isinstance(self.dummy_remote_service, WmsService):
                    from registry.models.security import \
                        AllowedWebMapServiceOperation  # to avoid circular import
                    layer_identifiers = self.dummy_remote_service.get_requested_layers(
                        query_params=request.query_parameters)
                    query = Q(secured_layers__identifier__iregex=r'%s' %
                              f"({'|'.join(layer_identifiers) })")
                    prefetch = Prefetch(
                        "allowed_operations",
                        queryset=AllowedWebMapServiceOperation.objects.filter(query).distinct(
                            "pk").only("pk", "allowed_area"),
                        to_attr='allowed_areas')
                    service = service_qs.prefetch_related(
                        prefetch).get(*args, **kwargs)
                else:
                    service = service_qs.get(*args, **kwargs)
            else:
                service = service_qs.get(*args, **kwargs)

        # TODO: check if we should catch ObjectDoesNotExist?
        except ObjectDoesNotExist:
            pass
        return service
