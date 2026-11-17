"""The share endpoints of a service (#740).

``POST /api/registry/{wms|wfs}/{id}/share`` writes role-scoped guardian
grants over the one service, ``GET`` answers the decided grants, and
``DELETE …/share/{grant}`` removes exactly one of those rows. This is the
**registry access** axis of #740: the OGC proxy keeps its own rules
(``Allowed*Operation`` with ``allowed_groups``, ``operations`` and
``allowed_area`` under the ``allowed-*-operations`` routes) and different
semantics - the naming of this module is what the UI shows apart.

Permission shape - one axis per method, all decided by the facade of #734:

* the endpoint answers registered callers only: a grant list names who got
  rights, which is administration information, not public service content;
* ``GET`` needs the object's ``view`` permission, the same read axis as
  the detail endpoint;
* ``POST`` and ``DELETE`` need ``registry.share_resource`` over this very
  service - held through the ``resource_publisher`` role or an explicit
  grant, answered by ``extras.permissions.allowed()`` with the request's
  checker, exactly where ``DjangoObjectPermissionsOrAnonReadOnly`` puts the
  object gate (its docstring assigns custom unsafe actions to call the
  facade themselves; this permission class *is* that call, in one place).

The payloads are plain JSON answers like the live preview's (#1327): the
grants are rows of guardian through-tables, not resources of the registry,
and inventing a JSON:API resource type for them would be a contract without
a model. The request body accepts the JSON:API document (the parser hands
the unwrapped attributes on) as well as the plain spelling.
"""
from django.http import JsonResponse
from drf_spectacular.utils import OpenApiTypes, extend_schema
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound
from rest_framework.permissions import SAFE_METHODS
from rest_framework.response import Response

from extras.permissions import DjangoObjectPermissionsOrAnonReadOnly
from extras.viewsets import NestedModelViewSet
from registry.models.shares import grant_actions
from registry.models.shares import revoke_share as revoke_share_row
from registry.models.shares import share_grants
from registry.serializers.shares import (ShareRequestSerializer,
                                         share_grant_payload)

#: the capability which gates writing shares, spelled app-level as the
#: carrier note of ``registry.models.service.WebMapService.Meta`` tells
SHARE_PERMISSION = "registry.share_resource"


def _attributes(request):
    """The submitted share payload, in one flat dictionary.

    Same normalization the schedule preview of #1327 does: the project's
    JSON:API parser hands on the unwrapped, snake_cased attributes, a plain
    JSON body still carries the document envelope.
    """
    data = request.data if isinstance(request.data, dict) else {}
    document = data.get("data")
    if isinstance(document, dict):
        attributes = document.get("attributes")
        if not isinstance(attributes, dict):
            attributes = {key: value for key, value in document.items()
                          if key not in ("type", "id")}
        return attributes
    return data


class ServiceSharePermissions(DjangoObjectPermissionsOrAnonReadOnly):
    """The DRF gate of the share actions, decided by the facade.

    Read keeps the viewset's own object axis (``view_<model>`` over the
    service, with the 404-vs-403 shape of the base class); every write
    asks ``registry.share_resource`` over the service instead of the
    viewset's ``change`` axis - a publisher who may share but not edit
    legitimately shares, and one who may edit but not share does not.
    """

    def has_permission(self, request, view) -> bool:
        # before any object is read: shares are administration information
        return bool(request.user and request.user.is_authenticated)

    def get_required_permissions(self, method, model_cls) -> list:
        # no model-level gate: a share is an object decision from the first
        # argument, and the retired global ``add`` of Q5=B opens nothing
        return []

    def get_required_object_permissions(self, method, model_cls) -> list:
        if method in SAFE_METHODS:
            return super().get_required_object_permissions(method, model_cls)
        return [SHARE_PERMISSION]


class ServiceShareViewSetMixin:
    """The share actions of one shareable service viewset.

    Mixed into ``WebMapServiceViewSet`` and ``WebFeatureServiceViewSet``;
    the operation ids are named per viewset there, the way the preview
    action's are. ``self.get_object()`` runs the viewset's queryset, which
    is what attaches the request's permission checker the facade consumes.
    """

    @classmethod
    def get_extra_actions(cls):
        actions = super().get_extra_actions()
        # Nested relationship viewsets inherit the service UI customizations
        # (ServicePreviewMixin does the same for preview), but shares only
        # belong to the canonical registered-service endpoint.
        if issubclass(cls, NestedModelViewSet):
            return [item for item in actions
                    if item.__name__ not in {"share", "revoke_share"}]
        return actions

    @action(detail=True, methods=["get", "post"], url_path="share",
            permission_classes=[ServiceSharePermissions],
            filter_backends=[])
    @extend_schema(
        request=ShareRequestSerializer,
        responses={200: OpenApiTypes.OBJECT, 201: OpenApiTypes.OBJECT,
                   400: OpenApiTypes.OBJECT, 403: OpenApiTypes.OBJECT,
                   404: OpenApiTypes.OBJECT},
        description="Registry shares of one service: guardian object "
                    "grants written onto one role of one organization or "
                    "one user, with the decision recorded next to them. "
                    "GET answers {\"grants\": [ShareGrant]}, POST writes "
                    "the named actions for one target, DELETE "
                    "…/share/{grant} revokes exactly one grant id. "
                    "Distinct from the OGC proxy's access rules, which "
                    "live on the allowed-*-operations routes.",
    )
    def share(self, request, pk=None, *args, **kwargs):
        service = self.get_object()
        # the object gate of the action's permission classes: view to read
        # the list, the share capability to write
        self.check_object_permissions(request, service)
        if request.method == "GET":
            return JsonResponse({"grants": [
                share_grant_payload(kind, row)
                for kind, row in share_grants(service)]})
        serializer = ShareRequestSerializer(
            data=_attributes(request), context={"service": service})
        serializer.is_valid(raise_exception=True)
        rows = grant_actions(
            service, serializer.resolve_target(),
            serializer.validated_data["actions"], granted_by=request.user)
        return JsonResponse(
            {"grants": [share_grant_payload(kind, row)
                        for kind, row in rows]},
            status=201)

    @action(detail=True, methods=["delete"],
            url_path=r"share/(?P<grant>[^/.]+)",
            permission_classes=[ServiceSharePermissions],
            filter_backends=[])
    @extend_schema(
        request=None,
        responses={204: None, 403: OpenApiTypes.OBJECT,
                   404: OpenApiTypes.OBJECT},
        description="Revoke exactly one registry share grant of this "
                    "service, named by the id GET answered "
                    "(\"<kind>-<pk>\"). Grants the creation bootstrap "
                    "wrote for the owning organization's own roles are "
                    "not shares and are not revoked here.",
    )
    def revoke_share(self, request, pk=None, grant=None, *args, **kwargs):
        service = self.get_object()
        self.check_object_permissions(request, service)
        if not revoke_share_row(service, grant):
            raise NotFound
        return Response(status=204)
