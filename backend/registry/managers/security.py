from abc import ABC
from typing import Any, List

from django.contrib.auth.models import Group
from django.contrib.gis.db.models import Union
from django.contrib.postgres.aggregates import ArrayAgg
from django.contrib.postgres.expressions import ArraySubquery
from django.db import models
from django.db.models import (BooleanField, Exists, ExpressionWrapper, F,
                              OuterRef, QuerySet)
from django.db.models import Value as V
from django.db.models.expressions import Value
from django.db.models.functions import Coalesce, JSONObject
from django.db.models.query_utils import Q
from django.http import HttpRequest
from ows_lib.models.ogc_request import OGCRequest
from ows_lib.xml_mapper.xml_responses.consts import GEOMETRY_DATA_TYPES
from registry.settings import SECURE_ABLE_OPERATIONS_LOWER


class AllowedOgcServiceOperationQuerySet(ABC, models.QuerySet):

    def get_entity_identifiers(self, request) -> tuple[str, List[str]]:
        raise NotImplementedError

    def filter_by_requested_entity(self, request):
        lookup, identifiers = self.get_entity_identifiers(request=request)
        query = None
        for identifier in identifiers:
            _query = Q(**{lookup: identifier})
            if query:
                query &= _query
            else:
                query = _query
        return self.filter(query)

    def for_user(self, service_pk, request: OGCRequest):
        return self.filter(
            secured_service__pk=service_pk,
            allowed_groups=None,
            operations__operation__iexact=request.operation,
        ).filter_by_requested_entity(request=request) | self.filter(
            secured_service__pk=service_pk,
            allowed_groups__pk__in=Group.objects.filter(
                user__username="AnonymouseUser"
            ).values_list("pk", flat=True)
            if request.request.user.is_anonymous
            else request.request.user.groups.values_list("pk", flat=True),
            operations__operation__iexact=request.operation,
        ).filter_by_requested_entity(request=request)

    def get_allowed_areas(self, service_pk, request: HttpRequest):
        return (
            self.filter(secured_service__pk=service_pk,
                        allowed_area__isnull=False)
            .filter_by_requested_entity(request=request)
            .for_user(service_pk=service_pk, request=request)
        )

    def get_empty_allowed_areas(self, service_pk, request: HttpRequest):
        return (
            self.filter(secured_service__pk=service_pk,
                        allowed_area__isnull=True)
            .filter_by_requested_entity(request=request)
            .for_user(service_pk=service_pk, request=request)
        )

    def is_service_secured(self, service_pk) -> Exists:
        return Exists(self.filter(secured_service__pk=service_pk))

    def is_spatial_secured(self, service_pk, request: HttpRequest) -> ExpressionWrapper:
        return ExpressionWrapper(
            Exists(
                self.get_allowed_areas(
                    service_pk=service_pk, request=request
                )
            )
            and ~Exists(
                self.get_empty_allowed_areas(
                    service_pk=service_pk, request=request
                )
            ),
            output_field=BooleanField(),
        )

    def is_user_entitled(self, service_pk, request: OGCRequest) -> Exists:
        """checks if the user of the request is member of any AllowedOperation object"""
        if request.request.user.is_superuser:
            return Value(True)
        return Exists(self.for_user(service_pk=service_pk, request=request))


class AllowedWebMapServiceOperationQuerySet(AllowedOgcServiceOperationQuerySet):

    def get_entity_identifiers(self, request):
        return "secured_layers__identifier__iexact", request.requested_entities

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


class AllowedWebFeatureServiceOperationQuerySet(AllowedOgcServiceOperationQuerySet):
    def get_entity_identifiers(self, request):
        return "secured_feature_types__identifier__iexact",  request.requested_entities


class WebMapServiceSecurityManager(models.Manager):

    def is_unknown_layer(self, service_pk, request: HttpRequest) -> QuerySet:
        return ~Exists(self.filter(pk=service_pk, layer__identifier__in=request.requested_entities))

    def get_allowed_operation_qs(self) -> AllowedWebMapServiceOperationQuerySet:
        from registry.models.security import \
            AllowedWebMapServiceOperation  # to avoid circular import

        return AllowedWebMapServiceOperationQuerySet(
            model=AllowedWebMapServiceOperation,
            using=self._db,
        )

    def prepare_with_security_info(self, request: OGCRequest):
        if request.is_get_capabilities_request:
            return self.get_queryset().annotate(
                camouflage=Coalesce(F("proxy_setting__camouflage"), V(False))
            )
        elif (
            request.operation.lower()
            not in SECURE_ABLE_OPERATIONS_LOWER
        ):
            return self.get_queryset().annotate(
                log_response=Coalesce(
                    F("proxy_setting__log_response"), V(False))
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
                    is_unknown_layer=self.is_unknown_layer(
                        service_pk=OuterRef("pk"), request=request),
                    is_spatial_secured=self.get_allowed_operation_qs().is_spatial_secured(
                        service_pk=OuterRef("pk"), request=request
                    ),
                    is_secured=self.get_allowed_operation_qs().is_service_secured(
                        service_pk=OuterRef("pk")
                    ),
                    is_user_principle_entitled=self.get_allowed_operation_qs().is_user_entitled(
                        service_pk=OuterRef("pk"), request=request
                    ),
                    is_spatial_secured_and_covers=self.get_allowed_operation_qs().is_spatial_secured_and_covers(
                        service_pk=OuterRef("pk"), request=request
                    ),
                    is_spatial_secured_and_intersects=self.get_allowed_operation_qs().is_spatial_secured_and_intersects(
                        service_pk=OuterRef("pk"), request=request
                    ),
                    allowed_area_union=self.get_allowed_operation_qs().get_allowed_areas(
                        service_pk=OuterRef("pk"), request=request
                    ).values('secured_service__pk').annotate(geom=Union('allowed_area')).values('geom'),
                    allowed_area_pks=self.get_allowed_operation_qs().get_allowed_areas(
                        service_pk=OuterRef("pk"), request=request
                    ).values('secured_service__pk').annotate(pks=ArrayAgg('pk')).values('pks'),


                )
            )

    def get_with_security_info(self, request: HttpRequest, *args: Any, **kwargs: Any):
        return self.prepare_with_security_info(request=request).get(*args, **kwargs)


class WebFeatureServiceSecurityManager(models.Manager):

    def is_unknown_feature_type(self, service_pk, feature_types: list[str]) -> QuerySet:
        return ~Exists(self.filter(pk=service_pk, featuretype__identifier__in=feature_types))

    def get_allowed_operation_qs(self) -> AllowedWebFeatureServiceOperationQuerySet:
        from registry.models.security import \
            AllowedWebFeatureServiceOperation  # to avoid circular import

        return AllowedWebFeatureServiceOperationQuerySet(
            model=AllowedWebFeatureServiceOperation,
            using=self._db,
        )

    def prepare_with_security_info(self, request: OGCRequest):
        if request.is_get_capabilities_request:
            return self.get_queryset().annotate(
                camouflage=Coalesce(F("proxy_setting__camouflage"), V(False))
            )
        elif (
            request.operation.lower()
            not in SECURE_ABLE_OPERATIONS_LOWER
        ):
            return self.get_queryset().annotate(
                log_response=Coalesce(
                    F("proxy_setting__log_response"), V(False))
            )
        elif request.is_get_feature_request:
            from registry.models.service import FeatureTypeProperty

            # FIXME: only property names for secured feature types are neded.
            geometry_property_names_query = FeatureTypeProperty.objects.filter(
                feature_type__service__pk=OuterRef("pk"),
                feature_type__identifier__in=request.requested_entities,

                data_type__in=GEOMETRY_DATA_TYPES).values(
                json=JSONObject(
                    type_name=F("feature_type__identifier"),
                    geometry_property_name=Coalesce(F("name"), V("THE_GEOM")))  # luky shot, THE_GEOM is the most popular default property name for the geometry...
            )

            return (
                self.get_queryset()
                .select_related("auth")
                .annotate(
                    camouflage=Coalesce(
                        F("proxy_setting__camouflage"), V(False)),
                    log_response=Coalesce(
                        F("proxy_setting__log_response"), V(False)),
                    is_unknown_feature_type=self.is_unknown_feature_type(
                        service_pk=OuterRef("pk"), feature_types=request.requested_entities),
                    is_spatial_secured=self.get_allowed_operation_qs().is_spatial_secured(
                        service_pk=OuterRef("pk"), request=request
                    ),
                    is_secured=self.get_allowed_operation_qs().is_service_secured(
                        service_pk=OuterRef("pk")
                    ),
                    is_user_principle_entitled=self.get_allowed_operation_qs().is_user_entitled(
                        service_pk=OuterRef("pk"), request=request
                    ),
                    allowed_area_union=self.get_allowed_operation_qs().get_allowed_areas(
                        service_pk=OuterRef("pk"), request=request
                    ).values('secured_service__pk').annotate(geom=Union('allowed_area')).values('geom'),
                    geometry_property_names=ArraySubquery(
                        geometry_property_names_query)
                )
            )

    def get_with_security_info(self, request: OGCRequest, *args: Any, **kwargs: Any):
        return self.prepare_with_security_info(request=request).get(*args, **kwargs)
