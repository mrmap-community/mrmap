from abc import ABC
from typing import Any

from django.contrib.auth.models import Group
from django.contrib.gis.db.models import Union
from django.contrib.postgres.expressions import ArraySubquery
from django.db import models
from django.db.models import (BooleanField, Count, Exists, ExpressionWrapper,
                              F, OuterRef, Prefetch, QuerySet, Subquery)
from django.db.models import Value as V
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
    def get_entity_identifiers(self, request) -> tuple[str, list[str]]:
        raise NotImplementedError

    def filter_by_requested_entity(self, request):
        """Filter only AllowedWebServiceOperation objects where all
        requested_entities are present.

        Previous implementation applied one filter per identifier which
        produced repeated self-joins on the related "secured_layers"/
        "secured_feature_types" tables and exploded the planner's
        join combinations. Instead, count matching related items and
        require the distinct match count to equal the number of
        requested identifiers. This uses a single join with
        conditional aggregation and avoids the Cartesian blowup.
        """
        lookup, identifiers = self.get_entity_identifiers(request=request)
        if not identifiers:
            return self.none()

        # The related field name is the part before the lookup suffix
        # e.g. "secured_layers__identifier__iexact" -> "secured_layers"
        related_field = lookup.split("__")[0]

        # Annotate how many distinct related entities match any of the
        # requested identifiers, then require the count to equal the
        # number of requested identifiers (i.e. all are present).
        return (
            self.annotate(
                _matched_count=Count(
                    related_field,
                    filter=Q(
                        **{f"{related_field}__identifier__in": identifiers}),
                    distinct=True,
                )
            )
            .filter(_matched_count=len(identifiers))
        )

    def filter_by_request(self, request: OGCRequest):
        """Filter operations allowed for the authenticated user and service.

        Args:
            request: OGCRequest object containing user and operation info

        Returns:
            QuerySet filtered for user permissions and requested entities
        """
        group_pks = (
            Group.objects.filter(
                user__username="AnonymousUser").values_list("pk", flat=True)
            if request._django_request.user.username == "AnonymousUser"
            else request._django_request.user.groups.values_list("pk", flat=True)
        )

        return (
            self.filter(
                operations__value=OGCOperationEnum(request.operation),
            )
            .filter(Q(allowed_groups=None) | Q(allowed_groups__pk__in=group_pks))
            .filter_by_requested_entity(request=request)
        )

    def is_user_entitled(self, service_pk, request: OGCRequest) -> Exists:
        """Check if the user of the request is entitled to access this service.

        Other users must be members of an
        AllowedOperation object matching their groups or anonymous access.

        Args:
            service_pk: Primary key of the service to check
            request: OGCRequest object containing user information

        Returns:
            Exists or Value expression indicating user entitlement
        """
        return Exists(self.filter_by_service_and_request(service_pk=service_pk, request=request))

    def for_service(self, service_pk):
        return self.filter(secured_service_id=service_pk)

    def is_service_secured(self, service_pk) -> Exists:
        return Exists(self.for_service(service_pk))

    def is_service_spatial_secured(self, service_pk) -> ExpressionWrapper:
        service_qs = self.for_service(service_pk)

        return ExpressionWrapper(
            Exists(service_qs)
            & ~Exists(service_qs.filter(allowed_area__isnull=True)),
            output_field=BooleanField(),
        )


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
        """Get a fresh QuerySet instance for allowed WMS operations.

        Returns:
            AllowedWebMapServiceOperationQuerySet: Fresh QuerySet instance
        """
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
            allowed_operations_prefetch = Prefetch(
                "allowed_operations",
                queryset=self.get_allowed_operation_qs().filter_by_request(
                    request=request),
                to_attr="relevant_allowed_operations"
            )

            return (
                qs.select_related("auth")
                .prefetch_related(
                    allowed_operations_prefetch
                )
                .annotate(
                    camouflage=Coalesce(
                        F("proxy_setting__camouflage"), V(False)),
                    log_response=Coalesce(
                        F("proxy_setting__log_response"), V(False)),
                    is_unknown_layer=self.is_unknown_layer(
                        service_pk=OuterRef("pk"), request=request),
                    is_secured=self.get_allowed_operation_qs(
                    ).is_service_secured(OuterRef("pk")),
                    is_spatial_secured=self.get_allowed_operation_qs(
                    ).is_service_spatial_secured(OuterRef("pk")),
                )
            )

    def get_with_security_info(self, request: HttpRequest, *args: Any, **kwargs: Any):
        return self.prepare_with_security_info(request=request).get(*args, **kwargs)


class WebFeatureServiceSecurityManager(models.Manager.from_queryset(AllowedWebFeatureServiceOperationQuerySet)):

    def is_unknown_feature_type(self, service_pk, feature_types: list[str]) -> QuerySet:
        return ~Exists(self.filter(pk=service_pk, featuretype__identifier__in=feature_types))

    def get_allowed_operation_qs(self) -> AllowedWebFeatureServiceOperationQuerySet:
        """Get a fresh QuerySet instance for allowed WFS operations.

        Returns:
            AllowedWebFeatureServiceOperationQuerySet: Fresh QuerySet instance
        """
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
            allowed_operations_prefetch = Prefetch(
                "allowed_operations",
                queryset=self.get_allowed_operation_qs().filter_by_request(
                    request=request),
                to_attr="relevant_allowed_operations"
            )
            return (
                qs
                .select_related("auth")
                .prefetch_related(
                    allowed_operations_prefetch
                )
                .annotate(
                    camouflage=Coalesce(
                        F("proxy_setting__camouflage"), V(False)),
                    log_response=Coalesce(
                        F("proxy_setting__log_response"), V(False)),
                    is_unknown_feature_type=self.is_unknown_feature_type(
                        service_pk=OuterRef("pk"), feature_types=request.requested_entities),
                    is_secured=self.get_allowed_operation_qs(
                    ).is_service_secured(OuterRef("pk")),
                    is_spatial_secured=self.get_allowed_operation_qs(
                    ).is_service_spatial_secured(OuterRef("pk")),
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
