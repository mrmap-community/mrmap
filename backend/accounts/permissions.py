"""The guard rails of the role API of #736.

The issue puts them here and in the serializers, not in the UI: an
ORGANIZATION-scoped role belongs to the members of that organization, a
PLATFORM-scoped role is assigned by a platform act, and managing the
memberships of an organization is the delegated scope of whoever administers
that organization (#727 decision Q3: membership in one organization says
nothing about another, Q7: organization administrators manage within their
delegated scope).

Two authorities answer all of it, both already enforced by guardian:

* ``accounts.change_organization`` **as an object permission** of the
  organization in question - the grant the bootstrap of #732 writes onto the
  ``organization_admin`` role group. Asking it per organization is what keeps
  an administrator of one organization out of the memberships of another, and
  it is deliberately *not* the global permission of the same codename: the
  permissions of a role definition are applied by the facade of #734, and a
  global grant here would be the cross-organization escalation #727 rules
  out.
* ``accounts.grant_platform_role`` - the global permission of this app which
  guards assigning a role over all organizations (see ``RoleScope``). The
  seeded catalogue grants it to no group with members (decision Q6), so in
  practice its holders are the break-glass superusers until #734 applies the
  ``platform_admin`` definition.

``user.has_perm`` consults both of these through the authentication backends
of ``MrMap/settings.py`` (``ModelBackend`` + guardian's
``ObjectPermissionBackend``), so a superuser passes everywhere without the
functions below naming that case.
"""
from django.db.models import Q
from django.db.models.query import QuerySet
from django.http import Http404
from extras.permissions import object_organization
from guardian.shortcuts import get_objects_for_user
from rest_framework.permissions import SAFE_METHODS, BasePermission

from accounts.models.groups import Organization

#: the object permission which answers "may administer this organization";
#: the grant of the ``organization_admin`` role group, see the module docstring
ORGANIZATION_ADMIN_PERM = "accounts.change_organization"

#: the global permission which guards assigning a role over all organizations
GRANT_PLATFORM_ROLE_PERM = "accounts.grant_platform_role"


def may_grant_platform_role(user) -> bool:
    """Whether ``user`` may assign PLATFORM-scoped roles."""
    return bool(user and user.is_authenticated) and user.has_perm(
        GRANT_PLATFORM_ROLE_PERM)


def may_administer_organization(user, organization) -> bool:
    """Whether ``user`` administers exactly this organization.

    Asked per organization on purpose: the delegated scope of an organization
    administrator is their organization, never the collection of all of them.
    """
    if organization is None or not user or not user.is_authenticated:
        return False
    return user.has_perm(ORGANIZATION_ADMIN_PERM, organization)


def administered_organizations(user) -> QuerySet:
    """The organizations whose memberships ``user`` may manage.

    Guardians answer of the object grants; a holder of the *global*
    ``change_organization`` gets all organizations (``accept_global_perms``),
    which is how #734's facade can widen an operator without a grant per row.
    """
    return get_objects_for_user(
        user, ORGANIZATION_ADMIN_PERM, klass=Organization,
        accept_global_perms=True, any_perm=True)


def visible_memberships(user, queryset: QuerySet) -> QuerySet:
    """The memberships ``user`` may see - never those of an unrelated org.

    A platform holder sees all; everybody else sees the memberships of the
    organizations they administer plus their own rows. The "plus their own"
    is what lets ``who-am-i`` and the client's own cache stay truthful
    without disclosing who else holds what.
    """
    if not user or not user.is_authenticated:
        return queryset.none()
    if may_grant_platform_role(user):
        return queryset
    return queryset.filter(
        Q(role__organization__in=administered_organizations(user))
        | Q(user=user)).distinct()


def may_view_memberships_of(user, role) -> bool:
    """Whether ``user`` may read (and change) the memberships of ``role``.

    A personal member of the role may see who else shares it - the role is
    shared knowledge by being held together -; the administrators of the
    role's organization may manage them; a PLATFORM role is platform ground.
    """
    if not user or not user.is_authenticated:
        return False
    if may_grant_platform_role(user):
        return True
    if role.organization_id is None:
        return False
    return (may_administer_organization(user, role.organization)
            or role.memberships.filter(user=user).exists())


def may_see_roles_of(user, target) -> bool:
    """Whether ``user`` may read the roles held by the user ``target``.

    Onesself always; a platform holder always; otherwise only when the two
    share an organization which ``user`` administers - the delegated scope
    which also lets ``user`` list the members of that organization.
    """
    if not user or not user.is_authenticated:
        return False
    if user == target or may_grant_platform_role(user):
        return True
    # an Organization's own pk *is* the pk of its Group parent row, so the
    # administered organizations and the groups of the target intersect
    # directly
    return administered_organizations(user).filter(
        pk__in=target.groups.values("pk")).exists()


def may_audit_permissions_of(user, obj) -> bool:
    """Whether ``user`` may ask *why* the grants over ``obj`` look as they do.

    #741's explain endpoint answers the grants behind a decision, which
    discloses who holds which role over which object - more than the caller's
    own rights. Two authorities answer that: the platform holder and the superuser
    (whose duty is the whole instance), and the administrator of the
    organization the object belongs to (the delegated scope of #727's Q3, which
    stops at its own organization). An object which knows no organization is
    nobody's delegated business, so only the first two answer it.

    It is deliberately *not* the only gate of that endpoint: a caller whose own
    rights over the object answer "allowed" has a stake in the answer about
    themselves, which the view checks beside this.
    """
    if not user or not user.is_authenticated:
        return False
    if getattr(user, "is_superuser", False) or may_grant_platform_role(user):
        return True
    organization = object_organization(obj)
    return may_administer_organization(user, organization)


class IsAuthenticatedReadOnlyOrPlatform(BasePermission):
    """Read for every authenticated user, write only for a platform holder.

    The role *definitions* describe what a role means; reading them is what
    the member picker of #737 needs from any account, while adding or
    adjusting one changes what a role *is* - a platform act.
    """

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if request.method in SAFE_METHODS:
            return True
        return may_grant_platform_role(user)


class RoleAccessPermission(BasePermission):
    """Read the roles for everybody authenticated, write within the scope.

    A ``Role`` row names a definition and an organization; it discloses no
    membership, so reading it is unproblematic. Writing one - creating the
    role of a definition for an organization, retiring it, deleting it and
    its group - is delegated to whoever administers that organization, or to
    a platform holder for a PLATFORM role.
    """

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated)

    def has_object_permission(self, request, view, obj):
        if request.method in SAFE_METHODS:
            return True
        if obj.organization_id is None:
            return may_grant_platform_role(request.user)
        return (may_administer_organization(request.user, obj.organization)
                or may_grant_platform_role(request.user))


class RoleMembershipAccessPermission(BasePermission):
    """Guard the membership rows, whose payload *is* who-holds-what.

    The list is narrowed to the visible rows of
    :func:`visible_memberships`; a nested collection under a role and a
    create against one are refused wholesale with a 403 for whoever neither
    administers the role's organization, holds the role themselves, nor
    grants platform roles - an outsider is answered with a reason, not with
    an empty list which would invite them to keep guessing.
    """

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        parent_role_id = view.kwargs.get("parent_lookup_role")
        if parent_role_id is None:
            # the flat collection: a list answers the visible rows whatever
            # the caller administers, so being authenticated is enough
            return True
        from accounts.models.roles import Role
        try:
            role = Role.objects.get(pk=parent_role_id)
        except (Role.DoesNotExist, ValueError, TypeError):
            # a nested collection under a role which is not there answers
            # like the role's own detail route, and not like a refusal
            raise Http404("No Role matches the given id.")
        return may_view_memberships_of(user, role)

    def has_object_permission(self, request, view, obj):
        return may_view_memberships_of(request.user, obj.role)
