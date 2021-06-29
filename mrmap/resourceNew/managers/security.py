from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.contrib.gis.geos import Polygon
from django.db.models.functions import Coalesce
from django.db.models import Value as V
from requests import Response

from service.helper.enums import HttpMethodEnum
from django.db import models
from django.db.models import F, Exists, OuterRef, ExpressionWrapper, BooleanField, Q


class ServiceSecurityManager(models.Manager):
    def for_security_facade(self, query_parameters, user, bbox: Polygon):
        from resourceNew.models.service import OperationUrl  # to avoid circular import
        from resourceNew.models.security import AllowedOperation  # to avoid circular import
        # todo: analyze query_parameters.get("request"); only if a secured operation like GetMap, GetFeatureInfo is
        #  requested, we need to calculate extra things like the is_spatial_secured query
        qs = super().get_queryset()
        is_secured_subquery = AllowedOperation.objects.filter(
            secured_service__pk=OuterRef('pk')
        )
        is_spatial_secured_subquery = AllowedOperation.objects.filter(
            secured_service__pk=OuterRef('pk'),
            allowed_area__isnull=False
        )
        anonymous_user_groups_subquery = Group.objects\
            .filter(user=get_user_model().objects.get(username="AnonymousUser")) \
            .values_list("pk", flat=True)
        user_groups_subquery = user.groups.values_list("pk", flat=True)
        user_is_principle_entitled_subquery = AllowedOperation.objects.filter(
            allowed_groups__pk__in=user_groups_subquery | anonymous_user_groups_subquery,
            operations__operation__iexact=query_parameters.get("request")
        )
        base_url_subquery = OperationUrl.objects.filter(
            service=OuterRef('pk'),
            method=HttpMethodEnum.GET.value,
            operation__iexact=query_parameters.get("request")
        ).values_list('url', flat=True)[:1]
        # some services support for example GetLegendGraphic operation requests but doesn't provide it as operation url.
        # for that we use the first url we can found.
        unknown_operation_url_subquery = OperationUrl.objects.filter(
            service=OuterRef('pk'),
            method=HttpMethodEnum.GET.value,
        ).values_list('url', flat=True)[:1]
        is_spatial_secured_and_covers = Exists(is_spatial_secured_subquery.filter(allowed_area__covers=bbox))
        is_spatial_secured_and_intersects = Exists(is_spatial_secured_subquery.filter(allowed_area__intersects=bbox))

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
                      is_spatial_secured_and_intersects=is_spatial_secured_and_intersects)


class ProxyLogManager(models.Manager):
    def create(self, response: Response, **kwargs):
        obj = super().create(**kwargs)
        obj.log_response(response=response)
        return obj
