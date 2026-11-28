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
from django.contrib.auth.models import Group
from django.db.models import Q
from django.db.models.query import QuerySet
from django.http import Http404
from extras.permissions import (audited_break_glass_superuser,
                                authorized_platform_scoped_perm,
                                allowed, object_organization)
from guardian.shortcuts import get_objects_for_user
from rest_framework.permissions import (SAFE_METHODS, BasePermission,
                                        DjangoObjectPermissions)

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


#: the read right of the account rows, named once because the guard, the
#: serializer and the catalogue all ask exactly this permission (#1807)
USER_READ_PERM = "accounts.view_user"

#: the read right of the group rows and of their members relation; a group
#: here is ``"<organization>: <role>"`` and its members are the accounts which
#: hold that role, so relation and row are decided together (#1807)
GROUP_READ_PERM = "auth.view_group"

#: what a member picker needs of an account: the resource identifier and the
#: display string the picker renders and sorts by (#1035). Everything else -
#: ``email``, ``isStaff``, ``isSuperuser``, ``lastLogin``, ``dateJoined`` and
#: the three confirmation flags - travels with ``accounts.view_user`` (#1807)
PICKER_FIELDS = ("url", "id", "username", "string_representation",
                 "groups", "roles")


def _any_of(conditions):
    """The ``OR`` of a list of ``Q`` objects, as one ``Q``."""
    combined = Q()
    for condition in conditions:
        combined |= condition
    return combined


def _cached_on(request, name, compute):
    """The answer of ``compute`` remembered on ``request``.

    A page of accounts asks the same question per row; one statement per
    request is the read plan the serializers of #1448 keep.
    """
    if request is None:
        return compute()
    memo = getattr(request, "_account_read_scope", None)
    if memo is None:
        memo = request._account_read_scope = {}
    if name not in memo:
        memo[name] = compute()
    return memo[name]


def reads_every_account(user, request=None) -> bool:
    """Whether ``user`` reads accounts over all organizations.

    The PLATFORM axis of the facade, which is where the shipped catalogue
    put ``accounts.view_user`` (``platform_admin`` and ``support``). The
    break-glass is named separately: ``User`` takes no part in the role
    system - #727's Q6 keeps the break-glass outside it - so a superuser
    holds no platform role whose definition could answer here.
    """
    if not user or not getattr(user, "is_authenticated", False):
        return False
    return _cached_on(
        request, ("every_account", user.pk),
        lambda: audited_break_glass_superuser(
            user) or bool(authorized_platform_scoped_perm(user, USER_READ_PERM)))


def reads_every_group(user, request=None) -> bool:
    """Whether ``user`` reads groups over all organizations.

    The same PLATFORM axis as :func:`reads_every_account`, asked of
    ``auth.view_group`` - which the shipped catalogue names for nobody, so
    out of the box only the break-glass answers here and the read of the
    group rows is scoped to the caller's own organizations.
    """
    if not user or not getattr(user, "is_authenticated", False):
        return False
    return _cached_on(
        request, ("every_group", user.pk),
        lambda: audited_break_glass_superuser(
            user) or bool(
                authorized_platform_scoped_perm(user, GROUP_READ_PERM)))


def organizations_of(user) -> QuerySet:
    """The organizations the caller belongs to, by any group behind them.

    ``User.groups`` holds both shapes a membership takes since #732: the
    organization row itself - the bootstrap member group - and the group of a
    role, whose organization is the one the person works in. A retired role
    (#741) is no statement of membership anymore, so its group does not count.
    """
    if not user or not getattr(user, "is_authenticated", False):
        return Organization.objects.none()
    from accounts.models.roles import Role

    role_groups = Role.objects.filter(
        memberships__user=user, is_active=True).values_list(
            "group_id", flat=True)
    return Organization.objects.filter(
        Q(pk__in=user.groups.values("pk"))
        | Q(roles__group_id__in=role_groups,
            roles__is_active=True)).distinct()


def may_read_account(user, target, request=None) -> bool:
    """Whether ``user`` may read the account ``target`` at all.

    The authorities, in the order of the facade's own axes: the account
    itself - what ``who-am-i`` of the read-only baseline (#833) and the
    client's own cache answer; the PLATFORM axis, undivided; a member of the
    organization of the target, which is what the member picker and the
    members screen of #737 read; the unclaimed account an administrator
    searches for in the "add a member" dialog; and an explicit grant over
    this very row, the axis guardian enforces for every other resource of
    this API.
    """
    if not user or not getattr(user, "is_authenticated", False):
        return False
    if user == target:
        return True
    if reads_every_account(user, request):
        return True
    if readable_organizations_of(user).filter(
            pk__in=organizations_of(target)).exists():
        return True
    if not target.groups.exists() and administered_organizations(
            user).exists():
        # the person the "add a member" dialog of #737 has just found: an
        # account which belongs to no organization yet is not another
        # organization's people, and the answer over it is the picker surface
        return True
    return allowed(user, USER_READ_PERM, target)


def account_fields(user, target, request=None):
    """The account attributes ``user`` may read of ``target``, or ``None``.

    ``None`` answers "everything": the caller's own row and the reader with
    the platform read right. Everybody else gets :data:`PICKER_FIELDS`, which
    is what a picker, a changelog and a member row render - never the address
    of a person, the fact that they are a superuser or when they last signed
    in. Asked of the same functions which decide the row, so the field surface
    cannot drift from the guard.

    An authenticated caller always gets the picker surface, even for a row the
    guard refuses: ``createdBy`` and ``historyUser`` of #738 answer an account
    the viewer of a service has no relationship with, and the audit trail of
    #741 goes silent without a name. The refusal of a *row* - the enumeration
    this issue is about - happens on the viewset's gates, not here. The
    anonymous caller of the read-only baseline gets the same surface: a
    published record still names who registered it, and never more.
    """
    if not user or not getattr(user, "is_authenticated", False):
        return PICKER_FIELDS
    if user == target or reads_every_account(user, request):
        return None
    return PICKER_FIELDS


class AccountAccessPermission(DjangoObjectPermissions):
    """Read an account as the catalogue says, write as before (#1807).

    The viewset named DRF's stock ``DjangoObjectPermissions``, whose
    ``perms_map`` answers a safe method with *no* permission at all: both
    gates reduce to ``user.has_perms([])`` → ``True``. Every authenticated
    principal - the machine account of a harvesting integration included,
    whose own catalogue description says "no human signs in with it" - read
    the whole account table with ``email``, ``isStaff``, ``isSuperuser``,
    ``lastLogin`` and the confirmation flags, while the shipped catalogue
    names ``accounts.view_user`` for two of its nine definitions.

    The class deliberately stays on DRF's stock base rather than the facade's
    ``DjangoObjectPermissionsOrAnonReadOnly``: the write half of #1448 is the
    global model gate before the object plus the object grant after, and the
    facade's class would answer a ``PATCH`` of an account from the role axes
    instead - a write policy change which #1807 does not ask for. The read
    half takes the branch the issue offers for the member picker, because the
    picker of #737 is a documented requirement and the platform's own doctrine
    ("Because reads need no grant",
    ``docs/source/administration/permissions.md``) keeps the *list* of
    resources open by design:

    * rows are scoped to the caller's organizations by
      :func:`readable_accounts` - another organization's people are not an
      answer, for a viewer, for a harvester or for a service account alike;
    * fields are reduced to :data:`PICKER_FIELDS` by :func:`account_fields`,
      so the address of a person, the fact that they are a superuser and when
      they last signed in travel with ``accounts.view_user`` and not with a
      session.

    An account outside that scope answers 404 and not 403 - the shape the
    parent class uses for a row the caller may not view, because a refusal
    would confirm the account exists (#1319). Anonymity stays refused: the
    baseline of #833 publishes services, never people.
    """

    def has_permission(self, request, view):
        if request.method not in SAFE_METHODS:
            return super().has_permission(request, view)
        user = request.user
        # the rows themselves are narrowed by ``readable_accounts`` and by the
        # object gate below; what the collection asks for is an identity,
        # which is what the users screens of the frontend already needed
        return bool(user and user.is_authenticated)

    def has_object_permission(self, request, view, obj):
        if request.method not in SAFE_METHODS:
            return super().has_object_permission(request, view, obj)
        if not may_read_account(request.user, obj, request):
            raise Http404
        return True


def readable_accounts(user, queryset: QuerySet, request=None) -> QuerySet:
    """The accounts ``user`` may read - never another organization's people.

    The list counterpart of :func:`may_read_account`, so a row cannot be
    missing from the list and reachable by id (#727 called that split the
    bug). The rows of an explicit guardian grant join the answer, which keeps
    the last authority of :func:`may_read_account` visible in the list too.
    """
    if not user or not getattr(user, "is_authenticated", False):
        return queryset.none()
    if reads_every_account(user, request):
        return queryset
    from accounts.models.roles import Role
    from accounts.models.users import User

    organizations = readable_organizations_of(user)
    role_groups = Role.objects.filter(
        organization__in=organizations,
        is_active=True).values_list("group_id", flat=True)
    granted = get_objects_for_user(
        user, USER_READ_PERM, klass=User,
        accept_global_perms=False, any_perm=True)
    scopes = [
        Q(groups__in=organizations),
        Q(groups__in=role_groups),
        Q(pk=user.pk),
        Q(pk__in=granted),
    ]
    if administered_organizations(user).exists():
        # the "add a member" dialog of #737 searches the accounts the platform
        # created and nobody has claimed yet - an account in no organization
        # is no organization's people. Only the picker surface of these rows
        # is ever answered, and only to an administrator.
        scopes.append(Q(groups__isnull=True))
    # both shapes of #732: the organization row *is* the bootstrap member
    # group and every role of it is a group of its own, so ``groups`` alone
    # answers a member, the roles of the organization answer its members
    return queryset.filter(_any_of(scopes)).distinct()


def readable_organizations_of(user) -> QuerySet:
    """The organizations whose people ``user`` reads: its own and its own admin.

    :func:`organizations_of` answers where the caller works;
    :func:`administered_organizations` adds what the delegation of #727's Q7
    gives an ``organization_admin`` whose membership is recorded only as an
    object grant. Both are needed: a member reads the colleagues they work
    with, the administrator reads the people they administer.

    The union runs over the pks and not over the two querysets: the guardian
    answer of ``administered_organizations`` joins the permission tables
    distinct, and Django refuses to ``|`` a distinct query with a plain one.
    """
    return Organization.objects.filter(
        Q(pk__in=organizations_of(user).values("pk"))
        | Q(pk__in=administered_organizations(user).values("pk")))


def member_readable_group_ids(user, request=None):
    """The pks of the groups whose member list ``user`` may read, or ``None``.

    ``None`` answers "every group". One statement answers a whole page, which
    is why the question is a set of ids and not an answer per row: the group
    serializer of #1448 reads the members of every group of its answer, and a
    decision per row there would be a decision per row of the page - the read
    plan of ``test_groups_api_permissions`` measures exactly that statement.
    """
    if not user or not getattr(user, "is_authenticated", False):
        return frozenset()
    return _cached_on(request, ("member_groups", user.pk),
                      lambda: _member_readable_group_ids(user))


def _member_readable_group_ids(user):
    """The unanswered question behind :func:`member_readable_group_ids`."""
    # ``grant_platform_role`` is the platform holder of the role system: the
    # same authority ``visible_memberships`` and ``may_view_memberships_of``
    # answer "all" for. Asked of the facade, not of ``has_perm``, because a
    # platform role of a definition is the grant (#732); beside it the
    # catalogue right over the group rows.
    if reads_every_group(user) or authorized_platform_scoped_perm(
            user, GRANT_PLATFORM_ROLE_PERM):
        return None
    from accounts.models.roles import Role

    # the organizations the caller belongs to plus the ones it administers -
    # the same scope which answers the accounts of those organizations, so a
    # member and an administrator see the members of exactly the same
    # organizations' groups (#1807)
    organizations = readable_organizations_of(user)
    return frozenset(Group.objects.filter(
        Q(user=user)
        | Q(pk__in=organizations.values_list("pk", flat=True))
        | Q(pk__in=Role.objects.filter(
            organization__in=organizations,
            is_active=True).values_list("group_id", flat=True))
        | Q(pk__in=get_objects_for_user(
            user, GROUP_READ_PERM, klass=Group,
            accept_global_perms=False, any_perm=True))).values_list(
                "pk", flat=True))


def may_read_members_of(user, group, readable_ids=None) -> bool:
    """Whether the answer for ``group`` may name the accounts in it.

    The members of a role group *are* the membership rows of that role, which
    #727's Q3 and ``RoleMembershipAccessPermission`` put behind the
    organization; the same authorities answer the relation here. An unrelated
    caller reads the row - what a picker needs - and not who is in it, which
    is the difference between a picker and a directory.

    ``readable_ids`` is the page-wide answer of
    :func:`member_readable_group_ids`; a serializer which answers a page hands
    it once instead of asking per row.
    """
    # ``readable_ids`` of ``[]`` and of ``None`` are both answers - an empty
    # set is "none", ``None`` is "all" - so the caller's cache is decided by
    # whether the argument was passed at all
    if not user or not getattr(user, "is_authenticated", False):
        return False
    if readable_ids is None:
        readable_ids = member_readable_group_ids(user)
    if readable_ids is None:
        return True
    return group.pk in readable_ids


def may_see_groups_of(user, target) -> bool:
    """Whether ``user`` may read which groups the account ``target`` is in.

    The same authorities as :func:`may_see_roles_of`, because the answer is
    that payload spelled on the group side: onesself always, a platform holder
    always, and a member of an organization the two share - which is what the
    member screens read on ``/users/{id}/groups``.
    """
    if not user or not user.is_authenticated:
        return False
    if user == target or reads_every_group(user):
        return True
    return organizations_of(user).filter(
        pk__in=organizations_of(target)).exists()


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
