from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.contrib.gis.db.models import Union
from django.contrib.gis.geos import Polygon
from django.db.models.functions import Coalesce
from django.db.models import Value as V
from requests import Response

from resourceNew.enums.service import OGCOperationEnum
from resourceNew.ows_client.request_builder import WebService, WmsService, WfsService
from service.helper.enums import HttpMethodEnum
from django.db import models
from django.db.models import F, Exists, OuterRef, ExpressionWrapper, BooleanField, Q


class ServiceSecurityManager(models.Manager):
    def for_security_facade(self, request):
        from resourceNew.models.service import OperationUrl  # to avoid circular import
        from resourceNew.models.security import AllowedOperation  # to avoid circular import

        qs = super().get_queryset()

        base_url_subquery = OperationUrl.objects.filter(
            service=OuterRef('pk'),
            method=HttpMethodEnum.GET.value,
            operation__iexact=request.query_parameters.get("request")
        ).values_list('url', flat=True)[:1]
        # some services support for example GetLegendGraphic operation requests but doesn't provide it as operation url.
        # for that we use the first url we can found.
        unknown_operation_url_subquery = OperationUrl.objects.filter(
            service=OuterRef('pk'),
            method=HttpMethodEnum.GET.value,
        ).values_list('url', flat=True)[:1]

        if request.query_parameters.get("request").lower() == OGCOperationEnum.GET_CAPABILITIES.value.lower():
            return qs.select_related("document") \
                .annotate(camouflage=Coalesce(F("proxy_setting__camouflage"), V(False)),
                          base_operation_url=base_url_subquery,
                          unknown_operation_url=unknown_operation_url_subquery)
        else:

            dummy_service = WebService.manufacture_service(request.get_full_path())
            if isinstance(dummy_service, WmsService):
                # FIXME: mapserver processes case insensitive layer identifiers... This query won't work then..
                layer_identifiers = dummy_service.get_requested_layers(query_params=request.query_parameters)
                is_spatial_secured_subquery = AllowedOperation.objects.filter(
                    secured_service__pk=OuterRef('pk'),
                    secured_layers__identifier__in=layer_identifiers,
                    allowed_area__isnull=True
                )
                allowed_areas = AllowedOperation.objects \
                    .filter(secured_service__pk=OuterRef("pk"),
                            secured_layers__identifier__in=layer_identifiers,
                            allowed_area__isnull=False) \
                    .distinct("pk") \
                    .values_list("allowed_area", flat=True)
            elif isinstance(dummy_service, WfsService):
                feature_type_identifiers = dummy_service.get_requested_feature_types(query_params=request.query_parameters)
                is_spatial_secured_subquery = AllowedOperation.objects.filter(
                    secured_service__pk=OuterRef('pk'),
                    secured_feature_types__identifier__in=feature_type_identifiers,
                    allowed_area__isnull=False
                )
                allowed_areas = AllowedOperation.objects \
                    .filter(secured_service__pk=OuterRef("pk"),
                            secured_feature_types__identifier__in=feature_type_identifiers,
                            allowed_area__isnull=False) \
                    .distinct("pk") \
                    .values_list("allowed_area", flat=True)
            is_secured_subquery = AllowedOperation.objects.filter(
                secured_service__pk=OuterRef('pk')
            )
            anonymous_user_groups_subquery = Group.objects\
                .filter(user=get_user_model().objects.get(username="AnonymousUser")) \
                .values_list("pk", flat=True)
            user_groups_subquery = request.user.groups.values_list("pk", flat=True)
            user_is_principle_entitled_subquery = AllowedOperation.objects.filter(
                allowed_groups__pk__in=user_groups_subquery | anonymous_user_groups_subquery,
                operations__operation__iexact=request.query_parameters.get("request")
            )
            is_spatial_secured_and_covers = Exists(is_spatial_secured_subquery.filter(allowed_area__covers=request.bbox))
            is_spatial_secured_and_intersects = Exists(is_spatial_secured_subquery.filter(allowed_area__intersects=request.bbox))

            return qs.select_related(
                "document",
                "service_type",
                "external_authentication",) \
                .annotate(camouflage=Coalesce(F("proxy_setting__camouflage"), V(False)),
                          log_response=Coalesce(F("proxy_setting__log_response"), V(False)),
                          is_spatial_secured=Exists(is_spatial_secured_subquery),
                          is_secured=Exists(is_secured_subquery),
                          user_is_principle_entitled=Exists(user_is_principle_entitled_subquery),
                          base_operation_url=base_url_subquery,
                          unknown_operation_url=unknown_operation_url_subquery,
                          is_spatial_secured_and_covers=is_spatial_secured_and_covers,
                          is_spatial_secured_and_intersects=is_spatial_secured_and_intersects,
                          allowed_area_united=Union(allowed_areas))


class ProxyLogManager(models.Manager):
    def create(self, response: Response, **kwargs):
        obj = super().create(**kwargs)
        obj.log_response(response=response)
        return obj
