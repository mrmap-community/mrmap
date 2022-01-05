from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.contrib.gis.db.models import Union
from django.core.exceptions import ObjectDoesNotExist
from django.db import models
from django.db.models import (BooleanField, Exists, ExpressionWrapper, F,
                              OuterRef, Q, QuerySet)
from django.db.models import Value as V
from django.db.models.functions import Coalesce
from ows_client.request_builder import WebService, WfsService, WmsService
from registry.enums.service import HttpMethodEnum, OGCOperationEnum
from registry.settings import SECURE_ABLE_OPERATIONS_LOWER


class AllowedOperationManager(models.Manager):

    def filter_qs_by_secured_element(self, qs, request):
        dummy_service = WebService.manufacture_service(request.get_full_path())
        if isinstance(dummy_service, WmsService):
            layer_identifiers = dummy_service.get_requested_layers(
                query_params=request.query_parameters)
            qs.filter(
                secured_layers__identifier__iregex=r'(' +
                '|'.join(layer_identifiers) + ')'
            )
        elif isinstance(dummy_service, WfsService):
            feature_type_identifiers = dummy_service.get_requested_feature_types(query_params=request.query_parameters,
                                                                                 post_body=request.body)
            qs.filter(
                secured_feature_types__identifier__iregex=r'(' + '|'.join(
                    feature_type_identifiers) + ')'
            )
        return qs

    def find_all_allowed_areas_by_request(self, request) -> QuerySet:
        # todo: filter also by requesting user; otherwise allowed operations without user restriction will returned
        qs = self.get_queryset().filter(
            secured_service__pk=OuterRef('pk'),
            allowed_area__isnull=False
        )
        qs = self.filter_qs_by_secured_element(qs=qs, request=request)
        return qs

    def find_all_empty_allowed_areas_by_request(self, request) -> QuerySet:
        # todo: filter also by requesting user; otherwise allowed operations without user restriction will returned
        qs = self.get_queryset().filter(
            secured_service__pk=OuterRef('pk'),
            allowed_area__isnull=True
        )
        qs = self.filter_qs_by_secured_element(qs=qs, request=request)
        return qs

    def is_service_secured(self) -> Exists:
        return Exists(self.get_queryset().filter(
            secured_service__pk=OuterRef('pk')
        ))

    def is_spatial_secured(self, request):
        return ExpressionWrapper(Exists(self.find_all_allowed_areas_by_request(request=request)) and
                                 ~Exists(self.find_all_empty_allowed_areas_by_request(
                                     request=request)),
                                 output_field=BooleanField())

    def is_spatial_secured_and_covers(self, request) -> Exists:
        return Exists(self.get_queryset().filter(
            secured_service__pk=OuterRef('pk'),
            allowed_area__covers=request.bbox
        ))

    def is_spatial_secured_and_intersects(self, request) -> Exists:
        return Exists(self.get_queryset().filter(
            secured_service__pk=OuterRef('pk'),
            allowed_area__intersects=request.bbox
        ))

    def is_user_entitled(self, request) -> Exists:
        anonymous_user_groups_subquery = Group.objects \
            .filter(user=get_user_model().objects.get(username="AnonymousUser")) \
            .values_list("pk", flat=True)
        user_groups_subquery = request.user.groups.values_list("pk", flat=True)
        user_is_principle_entitled_subquery = self.get_queryset().filter(
            secured_service__pk=OuterRef('pk'),
            allowed_groups__pk__in=user_groups_subquery | anonymous_user_groups_subquery,
            operations__operation__iexact=request.query_parameters.get(
                "request")
        )
        return Exists(user_is_principle_entitled_subquery)

    def allowed_area_union(self, request) -> Union:
        return Union(self.find_all_allowed_areas_by_request(request=request).distinct("pk").values_list("allowed_area",
                                                                                                        flat=True))


class OperationUrlManager(models.Manager):

    def get_base_url(self, request) -> str:
        return self.get_queryset().filter(
            service=OuterRef('pk'),
            method=HttpMethodEnum.GET.value,
            operation__iexact=request.query_parameters.get("request")
        ).values_list('url', flat=True)[:1]

    def get_fallback_url(self) -> str:
        return self.get_queryset().filter(
            service=OuterRef('pk'),
            method=HttpMethodEnum.GET.value,
        ).values_list('url', flat=True)[:1]


class ServiceSecurityManager(models.Manager):

    def _collect_data_for_security_facade(self, request) -> QuerySet:
        from registry.models.security import \
            AllowedOperation  # to avoid circular import
        from registry.models.service import \
            OperationUrl  # to avoid circular import
        if request.query_parameters.get("request").lower() == OGCOperationEnum.GET_CAPABILITIES.value.lower():
            return super().get_queryset().select_related("document") \
                .annotate(camouflage=Coalesce(F("proxy_setting__camouflage"), V(False)),
                          base_operation_url=OperationUrl.security_objects.get_base_url(
                              request=request),
                          unknown_operation_url=OperationUrl.security_objects.get_fallback_url())
        elif request.query_parameters.get("request").lower() not in SECURE_ABLE_OPERATIONS_LOWER:
            return super().get_queryset() \
                .annotate(log_response=Coalesce(F("proxy_setting__log_response"), V(False)),
                          base_operation_url=OperationUrl.security_objects.get_base_url(
                              request=request),
                          unknown_operation_url=OperationUrl.security_objects.get_fallback_url())
        else:
            return super().get_queryset().select_related(
                "document",
                "service_type",
                "external_authentication", ) \
                .annotate(camouflage=Coalesce(F("proxy_setting__camouflage"), V(False)),
                          log_response=Coalesce(
                              F("proxy_setting__log_response"), V(False)),
                          is_spatial_secured=AllowedOperation.objects.is_spatial_secured(
                              request=request),
                          is_secured=AllowedOperation.objects.is_service_secured(),
                          user_is_principle_entitled=AllowedOperation.objects.is_user_entitled(
                              request=request),
                          base_operation_url=OperationUrl.security_objects.get_base_url(
                              request=request),
                          unknown_operation_url=OperationUrl.security_objects.get_fallback_url(),
                          is_spatial_secured_and_covers=AllowedOperation.objects.is_spatial_secured_and_covers(
                              request=request),
                          is_spatial_secured_and_intersects=AllowedOperation.objects.is_spatial_secured_and_intersects(
                              request=request),
                          allowed_area_united=AllowedOperation.objects.allowed_area_union(request=request))

    def construct_service(self, pk, request):
        service = None
        try:
            service_qs = self._collect_data_for_security_facade(
                request=request)
            if request.query_parameters.get("request").lower() in SECURE_ABLE_OPERATIONS_LOWER:
                dummy_remote_service = WebService.manufacture_service(
                    request.get_full_path())
                if isinstance(dummy_remote_service, WmsService):
                    service_qs.prefetch_related("allowed_operations")
                    service = service_qs.get(pk=pk)
                    layer_identifiers = dummy_remote_service.get_requested_layers(
                        query_params=request.query_parameters)
                    query = Q(secured_layers__identifier__iregex=r'(' +
                              '|'.join(layer_identifiers) + ')')
                    service.allowed_areas = service.allowed_operations \
                        .filter(query) \
                        .distinct("pk") \
                        .values_list("pk", "allowed_area")
                else:
                    service = service_qs.get(pk=pk)
            else:
                service = service_qs.get(pk=pk)
        except ObjectDoesNotExist:
            pass
        return service
