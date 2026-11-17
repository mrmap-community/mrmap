"""ViewSets of the role API of #736.

Routes (registered in ``accounts/urls.py``):

* ``/roledefinitions``, ``/roledefinitions/{id}`` - the catalogue;
* ``/roles``, ``/roles/{id}`` - the roles of the instance;
* ``/roles/{id}/memberships`` - the members of one role (list and create);
* ``/memberships``, ``/memberships/{id}`` - the same rows by membership,
  readable and revocable;
* ``/users/{id}/roles`` and ``/organizations/{id}/roles`` - nested reads via
  ``NestedModelViewSet``, the pattern ``accounts/urls.py`` already uses;
* ``/organizations/{id}/members`` - the users of an organization with their
  roles in one answer.

The guard rails themselves are the permission classes of
:mod:`accounts.permissions` and the validation of
:mod:`accounts.serializers.roles`; these classes only select rows - a list
never answers what the caller may not see - and delegate deletion of a role
to :meth:`accounts.models.roles.Role.delete_with_group` so no orphan
``GroupObjectPermission`` row survives the group.
"""
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError as DjangoValidationError
from django.http import Http404
from django.utils.translation import gettext_lazy as _
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, status
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework_json_api.views import ModelViewSet

from accounts.models.groups import Organization
from accounts.models.roles import RoleDefinition, RoleMembership
from accounts.permissions import (RoleAccessPermission,
                                  RoleMembershipAccessPermission,
                                  IsAuthenticatedReadOnlyOrPlatform,
                                  may_administer_organization,
                                  may_grant_platform_role,
                                  may_see_roles_of, visible_memberships)
from accounts.serializers.roles import (RoleCreateSerializer,
                                        RoleDefinitionSerializer,
                                        RoleMembershipSerializer,
                                        RoleSerializer, roles_queryset)
from accounts.serializers.users import (OrganizationMemberAddSerializer,
                                        OrganizationMemberSerializer)
from extras.viewsets import (NestedModelViewSet,
                             ObjectPermissionCheckerViewSetMixin)

User = get_user_model()


def _parent_or_404(model, value):
    """The parent object of a nested route, 404 for a lost parent.

    A nested route under an id which does not exist must answer like the
    detail route of that resource - with a 404 - and not with a 500 over an
    unparseable uuid nor with the empty list of a filter over nothing.
    """
    try:
        return model.objects.get(pk=value)
    except (model.DoesNotExist, DjangoValidationError, ValueError):
        raise Http404(
            "No %s matches the given id." % model._meta.verbose_name)


class RoleDefinitionViewSetMixin:
    queryset = RoleDefinition.objects.prefetch_related("permissions")
    serializer_class = RoleDefinitionSerializer
    permission_classes = [IsAuthenticatedReadOnlyOrPlatform]
    filterset_fields = {
        'id': ['exact', 'in'],
        'slug': ['exact', 'icontains', 'contains'],
        'label': ['exact', 'icontains', 'contains'],
        'scope': ['exact', 'in'],
        'is_builtin': ['exact'],
        'is_default': ['exact'],
        'is_assignable': ['exact'],
    }
    ordering_fields = [
        "id", "slug", "label", "scope", "is_default", "is_assignable",
    ]


class RoleDefinitionViewSet(
    ObjectPermissionCheckerViewSetMixin,
    RoleDefinitionViewSetMixin,
    ModelViewSet
):
    """The catalogue of what a role means (#731).

    Readable by every account so the member picker of #737 can render the
    assignable roles; writes are platform acts. A builtin row cannot be
    deleted - the model raises ``ProtectedError`` for it - so the API does
    not offer DELETE at all, and the DELETE of ``ModelViewSet`` which would
    reach ``ProtectedError`` and answer 500 stays switched off.
    """

    http_method_names = ["get", "head", "options", "post", "patch"]


class RoleViewSetMixin:
    queryset = roles_queryset().prefetch_related("memberships")
    serializer_classes = {
        "default": RoleSerializer,
        "create": RoleCreateSerializer,
    }
    permission_classes = [RoleAccessPermission]
    filterset_fields = {
        'id': ['exact', 'in'],
        'is_active': ['exact'],
        'organization': ['exact'],
        'role_definition': ['exact'],
        'role_definition__slug': ['exact', 'in'],
        'organization__name': ['exact', 'icontains'],
    }
    ordering_fields = [
        "id", "is_active", "organization__name", "role_definition__slug",
        "string_representation",
    ]

    def get_serializer_class(self):
        return self.serializer_classes.get(
            self.action, self.serializer_classes["default"]
        )


class RoleViewSet(
    ObjectPermissionCheckerViewSetMixin,
    RoleViewSetMixin,
    ModelViewSet
):
    """Roles: readable by everybody authenticated, written in scope.

    ``PUT`` stays out (the PATCH-only convention of this API) and DELETE
    answers through ``delete_with_group`` so a removed role leaves no group
    and no orphan ``GroupObjectPermission`` row behind (#736's guard rail).
    """

    http_method_names = [
        "get", "head", "options", "post", "patch", "delete"]

    def perform_destroy(self, instance):
        instance.delete_with_group()


class NestedRoleViewSetMixin(RoleViewSetMixin):
    """Nested reads answer the same Role resource, unfiltered by visibility.

    A ``Role`` row discloses no membership (only ``RoleMembership`` rows do)
    and reading is open to every account, so the nested routes need no
    narrowing of their own - the parent lookup is the filter.
    """


class NestedUserRolesViewSet(
    NestedRoleViewSetMixin,
    NestedModelViewSet
):
    """``/users/{id}/roles`` - the roles one user holds.

    The parent lookup ``memberships__user`` follows the rows of
    ``RoleMembership``; who may look is :func:`may_see_roles_of`: the user
    themselves, a platform holder, or an administrator of an organization
    the target belongs to - never a stranger of an unrelated organization.
    """

    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        target = _parent_or_404(
            User, self.kwargs["parent_lookup_memberships__user"])
        if not may_see_roles_of(self.request.user, target):
            raise PermissionDenied(_(
                "Roles of other users are only visible to an administrator "
                "of an organization they share with you."))
        return super().get_queryset()


class NestedOrganizationRolesViewSet(
    NestedRoleViewSetMixin,
    NestedModelViewSet
):
    """``/organizations/{id}/roles`` - the roles of one organization."""

    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        # the parent must exist; reading a role is open, so nothing else is
        # asked here
        _parent_or_404(
            Organization, self.kwargs["parent_lookup_organization"])
        return super().get_queryset()


class RoleMembershipViewSetMixin:
    queryset = RoleMembership.objects.select_related(
        "role__role_definition", "role__organization", "user", "granted_by")
    serializer_class = RoleMembershipSerializer
    permission_classes = [RoleMembershipAccessPermission]
    filterset_fields = {
        'id': ['exact', 'in'],
        'role': ['exact'],
        'user': ['exact'],
        'role__organization': ['exact'],
        'granted_by': ['exact'],
    }
    ordering_fields = ["id", "granted_at", "valid_until"]


class RoleMembershipViewSet(
    ObjectPermissionCheckerViewSetMixin,
    RoleMembershipViewSetMixin,
    ModelViewSet
):
    """Memberships by their own id: read the visible ones, revoke one.

    The list is narrowed to :func:`visible_memberships` - an administrator
    gets the rows of their organizations, everybody gets their own rows,
    nobody gets an unrelated organization. A detail lookup is not narrowed
    (so revoking as an outsider answers 403 with the JSON:API error naming
    the reason instead of a bare 404, as AC1 asks), gated by the object
    permission of the same rule.
    """

    http_method_names = ["get", "head", "options", "delete"]

    def get_queryset(self):
        queryset = super().get_queryset()
        if self.action == 'list':
            queryset = visible_memberships(self.request.user, queryset)
        return queryset


class NestedRoleMembershipViewSet(
    ObjectPermissionCheckerViewSetMixin,
    RoleMembershipViewSetMixin,
    mixins.CreateModelMixin,
    NestedModelViewSet
):
    """``/roles/{id}/memberships`` - list the members of a role, add one.

    Authority and parent match are decided before the row is written: the
    permission class for the nested create (403 for an outsider, 404 for a
    lost parent), the serializer for a legal assignment. ``granted_by`` is
    the caller - the serializer fills it, the payload may not set it.
    """

    http_method_names = ["get", "head", "options", "post"]


class NestedOrganizationMemberViewSet(
    mixins.CreateModelMixin,
    NestedModelViewSet
):
    """``/organizations/{id}/members`` - the users of one organization.

    "Member of an organization" is membership of its group: an
    ``Organization`` *is* a ``Group``, which is exactly the parent lookup
    ``groups``. The answer carries each user with their roles **in that
    organization** - roles of another organization stay invisible, which is
    #727's Q3 applied to the members screen of #737. Reading and writing the
    member list is administering: delegated to the organization's
    administrators and to platform holders. A POST adds an existing user to
    the organization (the "add a member" of #736's AC1) - assigning a role
    of it is the separate, separately guarded step against ``/roles``.
    """

    queryset = User.objects.with_string_representation().prefetch_related(
        "role_memberships__role__role_definition",
        "role_memberships__role__organization")
    serializer_class = OrganizationMemberSerializer
    permission_classes = [IsAuthenticated]
    ordering_fields = ["id", "username", "string_representation"]
    http_method_names = ["get", "head", "options", "post"]

    def _organization_or_denied(self):
        """The parent organization, and the caller's authority over it."""
        organization = _parent_or_404(
            Organization, self.kwargs["parent_lookup_groups"])
        if not (may_administer_organization(self.request.user, organization)
                or may_grant_platform_role(self.request.user)):
            raise PermissionDenied(_(
                "The members of an organization are only visible to its "
                "administrators."))
        return organization

    def get_queryset(self):
        # the serializer scopes the roles it answers to this organization
        self.organization = self._organization_or_denied()
        return super().get_queryset().prefetch_related(
            "role_memberships__role__role_definition",
            "role_memberships__role__organization")

    @extend_schema(
        request=OrganizationMemberAddSerializer,
        responses={(201, "application/vnd.api+json"):
                   OrganizationMemberSerializer})
    def create(self, request, *args, **kwargs):
        """Add an existing user to the organization.

        There is no membership row to answer here - the organization's
        group is the membership - so after linking the user, the answer is
        the user in the members shape. The roles the answer carries are the
        ones this organization has already granted: adding a member grants
        no role, that is the POST to ``/roles/{id}/memberships``.
        """
        organization = self._organization_or_denied()
        serializer = OrganizationMemberAddSerializer(
            data=request.data, context=self.get_serializer_context())
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data["user"]
        organization.user_set.add(user)

        # the json:api renderer asks the view which type of resource the
        # answer carries; this answer is a User, seen through the members
        # serializer
        self.resource_name = "User"
        response_serializer = OrganizationMemberSerializer(
            user, context=self.get_serializer_context())
        return Response(
            response_serializer.data,
            status=status.HTTP_201_CREATED,
            headers=self.get_success_headers(response_serializer.data))
