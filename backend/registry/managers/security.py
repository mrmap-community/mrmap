from abc import ABC
from typing import Any, List, Tuple

from django.contrib.auth.models import Group
from django.contrib.gis.db.models import Union
from django.contrib.postgres.expressions import ArraySubquery
from django.db import models
from django.db.models import (BooleanField, Exists, ExpressionWrapper, F,
                              OuterRef, QuerySet, Subquery)
from django.db.models import Value as V
from django.db.models.expressions import Value
from django.db.models.functions import Coalesce, JSONObject
from django.db.models.query_utils import Q
from django.http import HttpRequest
from registry.enums.service import OGCOperationEnum
from registry.managers.service import (WebFeatureServiceQuerySet,
                                       WebMapServiceQuerySet)
from registry.ows_lib.request.ogc_request import OGCRequest
from registry.settings import SECURE_ABLE_OPERATIONS_LOWER

GEOMETRY_DATA_TYPES = [
    "gml:MultiPolygonPropertyType",
    "gml:MultiSurfacePropertyType",
    "gml:PolygonPropertyType",
    "gml:SurfacePropertyType",
    "gml:MultiLineStringPropertyType",
    "gml:MultiCurvePropertyType",
    "gml:LineStringPropertyType",
    "gml:GeometryPropertyType",
    "gml:CurvePropertyType",
    "gml:PointPropertyType",
    "gml:MultiPointPropertyType"
]


class AllowedOgcServiceOperationQuerySet(ABC, models.QuerySet):

    def get_entity_identifiers(self, request) -> Tuple[str, List[str]]:
        raise NotImplementedError

    def filter_by_requested_entity(self, request):
        """Collects only the AllowedWebServiceOperation objects where all requested_entities are part of."""
        lookup, identifiers = self.get_entity_identifiers(request=request)
        query = Q()
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
            operations__value=OGCOperationEnum(request.operation),
        ).filter_by_requested_entity(request=request) | self.filter(
            secured_service__pk=service_pk,
            allowed_groups__pk__in=Group.objects.filter(
                user__username="AnonymouseUser"
            ).values_list("pk", flat=True)
            if request._djano_request.user.is_anonymous
            else request._djano_request.user.groups.values_list("pk", flat=True),
            operations__value=OGCOperationEnum(request.operation),
        ).filter_by_requested_entity(request=request)

    def get_allowed_areas(self, service_pk, request: HttpRequest):
        """Collect all allowed areas that are configured for all requested entities together.

            Returns: The subset of allowed operations that for given user and requested entities.
        """
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
        if request._djano_request.user.is_superuser:
            return Value(True)
        return Exists(self.for_user(service_pk=service_pk, request=request))


class AllowedWebMapServiceOperationQuerySet(WebMapServiceQuerySet, AllowedOgcServiceOperationQuerySet):

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


class AllowedWebFeatureServiceOperationQuerySet(WebFeatureServiceQuerySet, AllowedOgcServiceOperationQuerySet):
    def get_entity_identifiers(self, request):
        return "secured_feature_types__identifier__iexact", request.requested_entities


class WebMapServiceSecurityManager(models.Manager.from_queryset(AllowedWebMapServiceOperationQuerySet)):

    def is_unknown_layer(self, service_pk, request: HttpRequest) -> QuerySet:
        return ~Exists(self.filter(pk=service_pk, layer__identifier__in=request.requested_entities))

    def get_allowed_operation_qs(self) -> AllowedWebMapServiceOperationQuerySet:
        from registry.models.security import \
            AllowedWebMapServiceOperation  # to avoid circular import

        return AllowedWebMapServiceOperationQuerySet(
            model=AllowedWebMapServiceOperation,
            using=self._db,
        )

    def prepare_with_security_info(self, request: OGCRequest, qs=None):
        qs = qs if qs is not None else self.get_queryset()
        if request.is_get_capabilities_request:
            return qs.annotate(
                camouflage=Coalesce(F("proxy_setting__camouflage"), V(False))
            )
        elif (
            request.operation.lower()
            not in SECURE_ABLE_OPERATIONS_LOWER
        ):
            return qs.annotate(
                log_response=Coalesce(
                    F("proxy_setting__log_response"), V(False))
            )
        else:
            return (
                qs.select_related("auth")
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
                    ).values('secured_service__pk').annotate(geom=Union('allowed_area')).values('geom')
                )
            )

    def get_with_security_info(self, request: HttpRequest, *args: Any, **kwargs: Any):
        return self.prepare_with_security_info(request=request).get(*args, **kwargs)


class WebFeatureServiceSecurityManager(models.Manager.from_queryset(AllowedWebFeatureServiceOperationQuerySet)):

    def is_unknown_feature_type(self, service_pk, feature_types: List[str]) -> QuerySet:
        return ~Exists(self.filter(pk=service_pk, featuretype__identifier__in=feature_types))

    def get_allowed_operation_qs(self) -> AllowedWebFeatureServiceOperationQuerySet:
        from registry.models.security import \
            AllowedWebFeatureServiceOperation  # to avoid circular import

        return AllowedWebFeatureServiceOperationQuerySet(
            model=AllowedWebFeatureServiceOperation,
            using=self._db,
        )

    def prepare_with_security_info(self, request: OGCRequest, qs=None):
        """
        Prepare a queryset annotated with security and proxy metadata for a
        Web Feature Service (WFS) OGC request.

        The method returns a Django QuerySet of WFS services. Depending on the
        request type and operation, the queryset is annotated with different
        security-related fields used during request evaluation and response
        filtering.

        Annotation behavior by request type
        -----------------------------------
        1. GetCapabilities requests
        The queryset is annotated with:
        - camouflage (bool):
            Whether the service response should be camouflaged.
            Derived from proxy_setting.camouflage, defaults to False.

        2. Non-secureable operations
        (request.operation.lower() not in SECURE_ABLE_OPERATIONS_LOWER)
        The queryset is annotated with:
        - log_response (bool):
            Whether the service response should be logged.
            Derived from proxy_setting.log_response, defaults to False.

        3. GetFeature requests (secureable)
        The queryset is fully annotated with service-level and
        feature-type-level security information.

        Service-level annotations:
        - camouflage (bool)
        - log_response (bool)
        - is_unknown_feature_type (bool):
            True if at least one requested feature type is not known
            for the service.
        - is_secured (bool):
            True if the service has any security configuration.
        - is_user_principle_entitled (bool):
            True if the requesting user is entitled to access the service
            (superusers are always entitled).
        - is_spatial_secured (bool):
            True if spatial restrictions apply for the requested feature types
            and no unrestricted (empty) allowed areas exist.

        Feature-type-level annotation:
        - security_info_per_feature_type (List[dict]):
            An array of JSON objects, one per requested feature type, with the
            following structure:

            {
                "type_name": str,
                "geometry_property_name": str,
                "allowed_area_union": Geometry | None
            }

            where:
            - type_name:
                Identifier of the feature type.
            - geometry_property_name:
                Name of the geometry property of the feature type. If no
                geometry property is defined, defaults to "THE_GEOM".
            - allowed_area_union:
                A spatial union of all allowed areas applicable to the feature
                type for the requested operation, or None if no spatial
                restriction applies.

        Parameters
        ----------
        request : OGCRequest
            Parsed WFS OGC request containing operation, requested feature types,
            user information, and request parameters.

        Returns
        -------
        QuerySet
            A queryset of WFS services annotated with proxy and security metadata.
            For GetFeature requests, the queryset includes per-feature-type
            security information encoded as JSON.
        """
        qs = qs if qs is not None else self.get_queryset()
        if request.is_get_capabilities_request:
            return qs.annotate(
                camouflage=Coalesce(F("proxy_setting__camouflage"), V(False))
            )
        elif (
            request.operation.lower()
            not in SECURE_ABLE_OPERATIONS_LOWER
        ):
            return qs.annotate(
                log_response=Coalesce(
                    F("proxy_setting__log_response"), V(False))
            )
        elif request.is_get_feature_request:
            from registry.models.service import (FeatureType,
                                                 FeatureTypeProperty)

            # FIXME: filter for requesting user
            security_info = FeatureType.objects.filter(
                service__pk=OuterRef("pk"),
                identifier__in=request.requested_entities,
                allowed_operation__operations__value=OGCOperationEnum(
                    request.operation),
            ).annotate(
                allowed_area_union=Union("allowed_operation__allowed_area"),
                geometry_property_name=Subquery(FeatureTypeProperty.objects.filter(
                    feature_type__pk=OuterRef("pk"),
                    data_type__in=GEOMETRY_DATA_TYPES
                )[:1].values("name"))
            )

            return (
                qs
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
                    security_info_per_feature_type=ArraySubquery(
                        security_info.values(json=JSONObject(
                            type_name=F("identifier"),
                            geometry_property_name=Coalesce(
                                F("geometry_property_name"), V("THE_GEOM")),
                            allowed_area_union=F("allowed_area_union")
                        ))
                    )
                )
            )

    def get_with_security_info(self, request: OGCRequest, *args: Any, **kwargs: Any):
        return self.prepare_with_security_info(request=request).get(*args, **kwargs)
