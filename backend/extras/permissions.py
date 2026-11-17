"""The one answer of "may this user do this on this object" (#734).

Before this module, four call sites answered that question with four
different expressions - ``False`` for the global-permission axis in
``accounts/filters/groups.py``, ``True`` in ``notify/managers.py``, ``global
AND object`` in the ``can_edit`` hints of the serializers - and the list,
the detail endpoint and the edit button could disagree about one and the
same user. #727 called that split the bug, not the trade-off; decision Q5=B
retires the unrestricted global grant and decision Q6=A keeps
``User.is_superuser`` outside the role system as the audited break-glass of
the deployment.

The facade is ``allowed()``::

    allowed(user, perm, obj) :=
        audited_break_glass_superuser(user)
     or authorized_explicit_scoped_object_grant(user, perm, obj)
     or authorized_platform_scoped_perm(user, perm)
     or authorized_role_membership_grant(user, perm, obj)

(The object grant is asked first because the request's checker has usually
loaded it without a query; the disjunction itself is order-free.)

Every view, serializer and queryset which decides a permission asks one of
the three entry points of this module and nothing else:

* ``allowed(user, perm, obj)`` - the decision over one object: the detail
  endpoint and every write;
* ``allowed_actions(user, obj, checker)`` - the same decisions as the set of
  actions the API may offer for one object: the ``allowedActions`` hint of
  #738, which retires the ``can_edit`` / ``can_delete`` / ``is_accessible``
  trio that answered it with expressions which could disagree;
* ``allowed_model_scope(user, perm)`` - the same decision where no object
  exists yet: the ``add`` gate of a create;
* ``objects_for_user(user, perm, klass)`` - the same answer as a queryset:
  the list filters, the visibility scopes of ``notify/`` and the alerts.

The checker loads, the facade decides
-------------------------------------

``guardian`` stays the engine which fetches permissions in bulk: the
per-request ``ObjectPermissionChecker`` of
``extras.viewsets.ObjectPermissionCheckerViewSetMixin`` and the
``request.shared_perm_checker`` fallback of ``extras.serializers`` are how
the object grants of a page reach memory without one query per row. The
facade consumes a checker handed to it instead of building its own; callers
on a per-object loop pass the checker they already have. The two axes which
the checker cannot answer - the permissions of a *role definition* - are
queries over a handful of rows, memoized per checker, i.e. per request.

What the axes mean
------------------

``audited_break_glass_superuser``
    ``User.is_superuser``. Decision Q6=A of #727: this is infrastructure
    break-glass, not a role; it stays outside the role system and the
    catalogue can never revoke it. Its audit trail (#741) reads this call.

``authorized_platform_scoped_perm``
    A *currently valid* membership in an active role of a definition with
    ``PLATFORM`` scope which holds ``perm``. This is the "deliberately
    scoped platform permission" of Q5=B: the platform catalogue of #731
    (``platform_admin``, ``support``, ``service_account``) decides what
    reaches over all organizations - a raw ``Group`` permission does not.

``authorized_explicit_scoped_object_grant``
    A guardian object grant over this very object, held by the user
    directly or by any group they are in - including the group of a role
    (#732's creation grants) and including a retired role's group, which
    keeps granting until #741 deletes it. This is the only grant an
    ordinary organization member needs: the bootstrap of #732/#733 writes
    view/change/delete onto the managing role's group at creation.

``authorized_role_membership_grant``
    A *currently valid* membership in an active role of an
    ``ORGANIZATION`` scope definition which holds ``perm``, where the
    object belongs to that same organization. The object's organization is
    the typed ownership ``owner`` of #733, or the organization itself; a
    model which knows no organization answers nothing here and stays
    decided by object grants.

An expired membership is a revoked one for the two role axes: the facade
never let ``valid_until`` grant through the definition, and it stops the
moment the timestamp passes. A guardian grant of the role's *group* keeps
granting until the revoking task of #741 removes the membership row - that
is stated in ``accounts.models.roles.RoleMembership`` and this module
respects it: the group is guardian's enforcement engine, and only the
revocation flips the answer. What the facade guarantees is that all three
entry points - detail, list and hint - flip together, which is the
acceptance of this issue.

The legacy global permission
----------------------------

A global ``Permission`` held through ``user.user_permissions`` or a plain
``Group`` - the ``Default-Permissions`` shape every pre-role deployment
carried - is **not** an allow path of ``allowed()``. Q5=B retires it: the
mapping of what each such grant meant to the roles above is the migration
work of #732 and #741, and a global grant never opens the objects of an
organization the user does not otherwise reach. Two places still consult
it, and both are marked there:

* the ``add`` gate of a create (this module's permission class): the right
  to register is moving to the role definitions of #732, but the create
  gate is not an object decision and retires with its data migration, not
  with this module;
* Django's own admin and any code outside this repo's API.

Cache invalidation
------------------

Django caches the global permission strings on the user instance
(``_perm_cache``, ``_user_perm_cache``, ``_group_perm_cache``). A request
authenticates a fresh user and is naturally current; a process which
grants and then re-uses a loaded user instance must not read a stale
cache. The receivers of ``accounts.signals`` and the write paths of
``RoleMembership`` call ``invalidate_permission_caches()`` centrally - no
caller may pop those attributes by hand (that is what #734 replaces).
"""
from django.contrib.auth.models import Group
from django.db import models
from django.db.models import Q
from django.http import Http404
from django.utils import timezone
from guardian.core import ObjectPermissionChecker
from guardian.shortcuts import get_objects_for_user
from rest_framework.permissions import DjangoObjectPermissions
from rest_framework.permissions import SAFE_METHODS

#: the attributes Django's ``ModelBackend`` and its helpers cache on the
#: user instance with the global permission strings; ``accounts.signals``
#: and the ``RoleMembership`` write paths drop them centrally, and no
#: caller is allowed to pop them by hand (#734).
PERMISSION_CACHES = ("_perm_cache", "_user_perm_cache", "_group_perm_cache")

#: The policy constant of the *global permission* axis (decision Q5=B of
#: #727). ``False`` means: an unrestricted global grant is never an allow
#: path of ``allowed()``; it is neither the ``True`` of the old
#: ``notify/managers.py`` calls nor the first half of the old ``can_edit``
#: AND. The one remaining consumer of a legacy global grant is the ``add``
#: gate of a create, named in ``allowed_model_scope`` - a create is not a
#: decision over an object, and that grant retires with its data
#: migration. Keeping the constant here makes the retired semantics
#: impossible to re-enable under another name without touching this line.
GLOBAL_GRANTS_EFFECTIVE = False

#: The CRUD actions, in answer order. They are spelled per model: the ``change``
#: answer of an object asks ``change_<model_name>`` of the object's own model.
CRUD_ACTIONS = ("view", "change", "delete")

#: The capability actions, in answer order. They are not content-type scoped:
#: a role holds them as an app-level permission of the object's app, which the
#: app declares on whatever carrier model it has - see the comment on the
#: custom permissions of ``registry.models.service.WebMapService``. An app that
#: declares no capability never answers one, and a model that is not the carrier
#: still answers through the role axes and through explicit grants, which is
#: exactly how ``allowed()`` reads ``registry.<codename>`` anyway.
CAPABILITY_ACTIONS = {
    "registry": {
        "publish": "publish_resource",
        "share": "share_resource",
        "manage_access_rules": "manage_access_rules",
    },
}


class Visibility(models.TextChoices):
    """The three answers of "who may see this resource" (#739).

    The vocabulary is derived, never stored: it reads the guardian grants
    which already decide the detail endpoint, so the list, the detail route
    and the API hint cannot disagree about one and the same resource - the
    split #727 called the bug.

    ``PUBLIC``
        The anonymous viewer role group holds ``view_<model>`` over the
        resource (decision Q2 of #727: an explicit grant, and only the
        publish path of the API - gated on ``registry.publish_resource`` -
        ever writes it).

    ``ORGANIZATION_INTERNAL``
        A role group of the owning organization holds the view grant - the
        shape the creation bootstrap of #732/#733 writes, and therefore the
        state every newly registered resource starts in.

    ``RESTRICTED``
        Neither: shared only with individually named groups or users (the
        sharing of #740) or with nobody. Unpublished is the default; a
        resource which lost its organization lost its internal scope too.
    """

    PUBLIC = "public", "Public"
    ORGANIZATION_INTERNAL = "organization-internal", "Organization-internal"
    RESTRICTED = "restricted", "Restricted"


def list_is_permission_filtered(model) -> bool:
    """Whether the deployment enabled permission-filtered lists for ``model``.

    ``PERMISSION_FILTERED_LIST_MODELS`` (``MrMap/settings.py``, #739) is the
    per-model rollout switch; the system check of ``accounts/checks.py``
    refuses entries which are not role-managed, so here the answer is the
    plain lookup.
    """
    from django.conf import settings

    enabled = getattr(settings, "PERMISSION_FILTERED_LIST_MODELS", None)
    return bool(enabled) and model._meta.label in set(enabled)


def set_public(obj, is_public: bool) -> None:
    """Give or take the anonymous view grant of one resource (#739).

    The grant lands on the anonymous viewer role group - the only statement
    of "the public may view this" the platform knows - and guardian's
    dedicated object-permission table of the model (#735) stores it, the same
    table the visibility annotation of
    ``registry.expressions.visibility`` reads and the detail endpoint's
    checker consults. Making a resource non-public takes the grant back;
    every other grant is left exactly as it was: revoking the last one is
    #740's sharing surface, not an unpublish.

    Args:
        obj: the resource being published or withdrawn
        is_public (bool): whether anonymous visitors may view it

    Raises:
        RuntimeError: the database has no anonymous viewer role group - an
            un-migrated deployment rather than a caller mistake
    """
    from guardian.shortcuts import assign_perm, remove_perm

    from accounts.utils import anonymous_viewer_group

    group = anonymous_viewer_group()
    if group is None:
        raise RuntimeError(
            "The anonymous viewer role group of #739 does not exist; run "
            "the migrations before publishing anything.")
    perm = f"{obj._meta.app_label}.view_{obj._meta.model_name}"
    if is_public:
        assign_perm(perm, group, obj)
    else:
        remove_perm(perm, group, obj)


def _split_perm(perm, obj=None):
    """``(app_label, codename)`` of ``"app.codename"`` or ``"codename"``.

    Mirrors how guardian normalizes a permission name: without a prefix the
    app label comes from the object.
    """
    if "." in perm:
        app_label, codename = perm.split(".", 1)
    else:
        if obj is None:
            raise ValueError(
                f"permission '{perm}' names no app_label and no object "
                f"was given to answer it")
        app_label = obj._meta.app_label
        codename = perm
    return app_label, codename


def _memo_of(checker):
    """The per-request cache of the two role-definition axes.

    The axes are per ``(perm, organization)``, not per object, and a
    serializer asks them once per row. The checker already is the
    per-request permission context (the viewset mixin and the shared
    fallback attach it for exactly that reason), so the memo lives with it.
    """
    memo = getattr(checker, "_mrmap_role_memo", None)
    if memo is None:
        memo = {}
        setattr(checker, "_mrmap_role_memo", memo)
    return memo


def audited_break_glass_superuser(user) -> bool:
    """The break-glass of decision Q6=A: ``User.is_superuser`` alone.

    Deliberately not a role: the catalogue cannot grant it and no migration
    may retire it. It is *audited* break-glass - the audit trail #741 asks
    for traces this single call.
    """
    return bool(user is not None
                and getattr(user, "is_authenticated", False)
                and getattr(user, "is_superuser", False))


def _valid_memberships_queryset(user, app_label, codenames, scope):
    """The currently valid memberships through which a role grants any of ``codenames``.

    Shared by every role axis so "membership" answers identically everywhere:
    an *active* role, a membership whose ``valid_until`` has not passed (an
    expired membership is not valid, even while #741's revoking task has not
    deleted its row yet), and the definition holds the permission. Asked for
    a list of codenames it is the batched form of the per-permission query -
    one statement over the handful of memberships (#738).

    Args:
        user: the user to ask
        app_label (str): the app the codenames belong to
        codenames (list): permission codenames, e.g. ``["change_webmapservice"]``
        scope: the ``RoleScope`` the role's definition must have
    """
    from accounts.models.roles import RoleMembership

    if user is None or not getattr(user, "is_authenticated", False):
        return RoleMembership.objects.none()
    if getattr(user, "pk", None) is None:
        return RoleMembership.objects.none()

    now = timezone.now()
    return RoleMembership.objects.filter(
        user=user,
        role__is_active=True,
        role__role_definition__scope=scope,
        role__role_definition__permissions__content_type__app_label=app_label,
        role__role_definition__permissions__codename__in=list(codenames),
    ).filter(Q(valid_until__isnull=True) | Q(valid_until__gt=now))


def _valid_membership_queryset(user, perm, scope):
    """The currently valid memberships through which a role grants ``perm``.

    See ``_valid_memberships_queryset`` for what *currently valid* means.
    """
    app_label, codename = _split_perm(perm)
    return _valid_memberships_queryset(user, app_label, [codename], scope)


def _valid_membership_perm_exists(user, perm, scope,
                                  organization_id=None) -> bool:
    """Whether one currently valid membership grants ``perm`` through a role.

    See ``_valid_membership_queryset`` for what *currently valid* means.

    Args:
        organization_id: restrict to one organization; ``None`` asks the
            PLATFORM scope, which belongs to no organization
    """
    memberships = _valid_membership_queryset(user, perm, scope)
    if organization_id is None:
        memberships = memberships.filter(role__organization__isnull=True)
    else:
        memberships = memberships.filter(role__organization_id=organization_id)
    return memberships.exists()


def _valid_membership_organization_ids(user, perm, scope) -> list:
    """The organizations inside which a currently valid role grants ``perm``."""
    return list(_valid_membership_queryset(user, perm, scope)
                .values_list("role__organization_id", flat=True).distinct())


def authorized_platform_scoped_perm(user, perm, checker=None) -> bool:
    """The PLATFORM-scope axis: what a platform role may do anywhere.

    ``perm`` is granted by an active definition of ``PLATFORM`` scope which
    the user *currently validly* holds as a role. The raw global permission
    of a plain group never answers here - that is the retirement of Q5=B.
    """
    from accounts.models.roles import RoleScope

    app_label, codename = _split_perm(perm)
    perm_str = f"{app_label}.{codename}"
    memo = _memo_of(checker) if checker is not None else None
    if memo is not None:
        key = ("platform", perm_str)
        if key in memo:
            return memo[key]
    result = _valid_membership_perm_exists(user, perm_str, RoleScope.PLATFORM)
    if memo is not None:
        memo[key] = result
    return result


def object_organization(obj):
    """The organization ``obj``'s rights are scoped to, or ``None``.

    The typed ownership of #733 (``owner``) for the resources which store
    one; an ``Organization`` is its own organization; a model which knows
    no organization answers ``None`` and stays decided by object grants -
    inventing a scope for a model which has none is not this facade's job
    (#738, #740 scope the remaining kinds).

    The ``owner`` *id* is read from the loaded row, never through the
    related object, so asking this on every row of a list answers no
    additional query.
    """
    from accounts.models.groups import Organization

    if isinstance(obj, Organization):
        return obj
    owner_id = getattr(obj, "owner_id", None)
    if owner_id is None:
        return None
    owner = getattr(obj, "owner", None)
    if isinstance(owner, Organization):
        return owner
    return None


def authorized_explicit_scoped_object_grant(user, perm, obj,
                                            checker=None) -> bool:
    """The object axis: guardian grants over this very object.

    The user's own grants and the grants of every group they are in, the
    role groups of #732 included; the checker of the request is the loader,
    exactly as before this issue - only the *decision* moved here.
    """
    if user is None or obj is None:
        return False
    if checker is None:
        checker = ObjectPermissionChecker(user)
    app_label, codename = _split_perm(perm, obj)
    perm_str = f"{app_label}.{codename}"
    memo = _memo_of(checker) if checker is not None else None
    if memo is not None:
        key = ("grant", perm_str, obj.pk)
        if key in memo:
            return memo[key]
    result = checker.has_perm(perm_str, obj)
    if memo is not None:
        memo[key] = result
    return result


def authorized_role_membership_grant(user, perm, obj, checker=None) -> bool:
    """The ORGANIZATION-scope axis: a member role inside its own org.

    The definition's permission becomes effective exactly where #732 said
    it would - inside the organization of the role, on an object which
    belongs to it. An object without a known organization answers nothing
    here and falls back to the object-grant axis.
    """
    from accounts.models.roles import RoleScope

    if user is None or obj is None:
        return False
    organization = object_organization(obj)
    if organization is None:
        return False
    app_label, codename = _split_perm(perm, obj)
    perm_str = f"{app_label}.{codename}"
    memo = _memo_of(checker) if checker is not None else None
    if memo is not None:
        key = ("org", perm_str, organization.pk)
        if key in memo:
            return memo[key]
    result = _valid_membership_perm_exists(
        user, perm_str, RoleScope.ORGANIZATION,
        organization_id=organization.pk)
    if memo is not None:
        memo[key] = result
    return result


def authorized_public_object_grant(user, perm, obj, checker=None) -> bool:
    """The public axis: the anonymous viewer's grant holds for everyone.

    A ``view_<model>`` grant onto the anonymous viewer role group is the
    platform's one statement of "anyone may view this" (#739). A logged-in
    caller who may not see it would see *less* than the anonymous one on the
    very same row - the split between list and detail that #727 called the
    bug, rebuilt on a new axis. So the grant of that group answers for every
    user, and for view permissions only: publishing never says anything
    about change or delete.

    Costs one ``EXISTS`` over the dedicated guardian table of the model when
    the cheaper axes answered no - and nothing at all while the database
    holds no anonymous grant, which is every database until somebody
    publishes (#739's rollout by construction).
    """
    if user is None or obj is None:
        return False
    app_label, codename = _split_perm(perm, obj)
    if not codename.startswith("view_"):
        return False
    perm_str = f"{app_label}.{codename}"
    memo = _memo_of(checker) if checker is not None else None
    if memo is not None:
        key = ("public", perm_str, obj.pk)
        if key in memo:
            return memo[key]

    from guardian.utils import get_group_obj_perms_model

    from accounts.utils import anonymous_viewer_group

    group = anonymous_viewer_group()
    result = False
    if group is not None:
        through_model = get_group_obj_perms_model(obj)
        grants = through_model.objects.filter(
            group=group,
            permission__codename=codename,
            permission__content_type__app_label=app_label)
        if through_model.objects.is_generic():
            grants = grants.filter(
                content_type__app_label=app_label,
                content_type__model=obj._meta.model_name,
                object_pk=str(obj.pk))
        else:
            grants = grants.filter(content_object_id=obj.pk)
        result = grants.exists()
    if memo is not None:
        memo[key] = result
    return result


def public_object_ids(model, perm):
    """The row ids of ``model`` which the anonymous grant makes public.

    The list counterpart of ``authorized_public_object_grant`` - the same
    statement, to be OR-ed into a queryset. ``None`` answers silently: a
    request over several permissions, a codename which is no view permission,
    or a database without the group of #739.

    On a dedicated guardian table - every role-managed model, which is all the
    rollout switch allows - the answer stays a subquery, so a page narrows in
    one statement and no deployment ever hands back a list of ids as long as
    its public catalogue. The generic table stores the primary key as text, so
    there the ids are read out and adapted per value.
    """
    if isinstance(perm, (list, tuple)):
        return None
    app_label, codename = _split_perm(perm) if "." in perm \
        else (model._meta.app_label, perm)
    if not codename.startswith(f"view_{model._meta.model_name}"):
        return None

    from guardian.utils import get_group_obj_perms_model

    from accounts.utils import anonymous_viewer_group

    group = anonymous_viewer_group()
    if group is None:
        return None
    through_model = get_group_obj_perms_model(model)
    grants = through_model.objects.filter(
        group=group,
        permission__codename=codename,
        permission__content_type__app_label=app_label)
    if through_model.objects.is_generic():
        return list(grants.filter(
            content_type__app_label=app_label,
            content_type__model=model._meta.model_name).values_list(
                "object_pk", flat=True))
    return grants.values_list("content_object_id", flat=True)


def allowed(user, perm, obj, checker=None) -> bool:
    """The one answer of "may this user hold ``perm`` over ``obj``".

    The facade of #734; see the module docstring for the four axes and the
    policy. ``checker`` is the request's ``ObjectPermissionChecker`` when
    the caller has one - pass it and the decision is free for prefetched
    objects; without it the object axis builds a checker of its own, which
    is correct but one query per call.

    Args:
        user: the user asking; ``None`` and anonymous answer only the
            object axis, as an anonymous user holds no role
        perm (str): ``"app_label.codename"`` (guardian's app-label rule)
        obj: the object the decision is about
        checker: the request's permission checker, when there is one
    """
    if audited_break_glass_superuser(user):
        return True
    if user is None:
        return False
    if not getattr(user, "is_authenticated", False):
        # anonymous: only an explicit grant over the anonymous database
        # user's row reaches an object; the checker maps Django's
        # AnonymousUser to that row exactly like the direct checker calls
        # of before did. Asked before is_active, which Django's
        # AnonymousUser answers False.
        return authorized_explicit_scoped_object_grant(
            user, perm, obj, checker=checker)
    if not getattr(user, "is_active", False):
        # an inactive user grants nothing, superuser aside - the same rule
        # Django's ModelBackend already answers for the global store
        return False
    # the object axis first: the checker of the request has usually loaded
    # it already, so the common grant answers without a query; the two role
    # axes are per-request memoized queries behind it. The axes are a
    # disjunction, the order decides cost, never the answer.
    if authorized_explicit_scoped_object_grant(
            user, perm, obj, checker=checker):
        return True
    if authorized_public_object_grant(user, perm, obj, checker=checker):
        # public is public for the logged-in too (#739): the anonymous
        # group's view grant answers for every user, never for less
        return True
    if authorized_platform_scoped_perm(user, perm, checker=checker):
        return True
    if authorized_role_membership_grant(user, perm, obj, checker=checker):
        return True
    return False


def allowed_model_scope(user, perm, checker=None) -> bool:
    """The decision where no object exists yet: the right to register.

    #732's catalogue moved the right to add resources into the role
    definitions (``resource_editor`` holds ``registry.add_webmapservice``),
    so a create is answered by: the break-glass, a platform role, or a
    currently valid membership of *any* organization whose role definition
    holds the permission - the owning organization is validated afterwards
    by the create serializers of #733, which is what scopes the effect.

    The legacy global ``add`` is still consulted for the create gate, and
    only for it: ``GLOBAL_GRANTS_EFFECTIVE`` documents the exception, and a
    global ``add`` opens no object by itself.
    """
    from accounts.models.roles import RoleScope

    if audited_break_glass_superuser(user):
        return True
    if user is None or not getattr(user, "is_authenticated", False):
        return False

    if GLOBAL_GRANTS_EFFECTIVE and user.has_perm(perm):
        return True
    if authorized_platform_scoped_perm(user, perm, checker=checker):
        return True

    return _valid_membership_queryset(
        user, perm, RoleScope.ORGANIZATION).exists()


def _action_permissions(obj):
    """The ordered ``(action, perm)`` pairs ``obj`` answers its actions through.

    The CRUD actions first, spelled per model (``change_webmapservice``); then
    the capability actions of the object's app, spelled app-level
    (``registry.publish_resource``) exactly as the carrier note in
    ``registry.models.service.WebMapService.Meta`` tells the caller to ask.
    The order is fixed because it is the answer order of ``allowed_actions``.
    """
    app_label = obj._meta.app_label
    pairs = [(action, f"{app_label}.{action}_{obj._meta.model_name}")
             for action in CRUD_ACTIONS]
    pairs += [(action, f"{app_label}.{codename}") for action, codename
              in CAPABILITY_ACTIONS.get(app_label, {}).items()]
    return pairs


def _seed_action_role_memos(user, obj, checker):
    """Load both role axes for every action of ``obj`` with two queries.

    The per-permission role queries are correct one at a time, but a whole
    action batch on every row of a list would pay one query per distinct
    permission through ``_valid_membership_perm_exists``. So the two axes are
    asked once per request and app for the whole codename batch - the PLATFORM
    axis as a set of codenames, the ORGANIZATION axis as
    ``(organization_id, codename)`` pairs, both over the handful of rows of
    ``_valid_memberships_queryset`` - and the answers are seeded under the
    exact memo keys ``authorized_platform_scoped_perm`` and
    ``authorized_role_membership_grant`` read. A later ``allowed()`` on any of
    these permissions answers from the same memory; the batched and the single
    path cannot drift because they share the one memo (#738).
    """
    from accounts.models.roles import RoleScope

    memo = _memo_of(checker)
    app_label = obj._meta.app_label
    codenames = [perm.split(".", 1)[1] for _, perm in _action_permissions(obj)]
    batch = (app_label, tuple(codenames))

    platform_key = ("actions_platform", batch)
    if platform_key not in memo:
        memo[platform_key] = set(
            _valid_memberships_queryset(
                user, app_label, codenames, RoleScope.PLATFORM)
            .filter(role__organization__isnull=True)
            .values_list("role__role_definition__permissions__codename",
                         flat=True).distinct())
    platform = memo[platform_key]
    for codename in codenames:
        memo[("platform", f"{app_label}.{codename}")] = codename in platform

    organization = object_organization(obj)
    if organization is None:
        # an object without a known organization answers nothing on the org
        # axis, exactly as authorized_role_membership_grant does - and no
        # query is paid for it
        return
    org_key = ("actions_org", batch)
    if org_key not in memo:
        memo[org_key] = set(
            _valid_memberships_queryset(
                user, app_label, codenames, RoleScope.ORGANIZATION)
            .exclude(role__organization__isnull=True)
            .values_list("role__organization_id",
                         "role__role_definition__permissions__codename")
            .distinct())
    pairs = memo[org_key]
    for codename in codenames:
        memo[("org", f"{app_label}.{codename}", organization.pk)] = \
            (organization.pk, codename) in pairs


def allowed_actions(user, obj, checker=None) -> list:
    """The actions ``user`` may take on ``obj``, in the fixed answer order.

    The hint of #738: one answer for "what may this caller do here", shipped
    by the serializers as ``allowedActions`` and gated on by the frontend -
    replacing the ``can_edit`` / ``can_delete`` / ``is_accessible`` trio whose
    expressions could disagree with the endpoint. It widens nothing: every
    returned action is answered by ``allowed()`` for its permission, and an
    action an app does not declare is never answered (``_action_permissions``).

    The cost mirrors ``allowed()`` rather than adding to it: the object axis
    is asked first and is free for a prefetched page; the two role axes are
    only reached for the actions which hold no explicit grant, and then not
    one query per action but one batch per request and app
    (``_seed_action_role_memos``). A fully granted user therefore reads zero
    role queries - the same state the single ``is_accessible`` hint was in -
    which is what keeps the explorer list inside its pinned query budget
    (#738, ``tests_query_performance.py``).

    Args:
        user: the user asking; ``None`` and anonymous answer only the object
            axis, like ``allowed()``
        obj: the object the actions are about
        checker: the request's permission checker, when there is one
    """
    actions = _action_permissions(obj)
    if audited_break_glass_superuser(user):
        # the break-glass answers every action of the object and asks no query
        return [action for action, _ in actions]
    if user is None:
        return []
    if getattr(user, "is_authenticated", False) \
            and not getattr(user, "is_active", False):
        # an inactive user grants nothing, superuser aside - the rule of
        # allowed(), checked before the object axis which Django's
        # AnonymousUser answers False
        return []
    decisions = {}
    missing = []
    for action, perm in actions:
        # the object axis first: the checker of the request has usually
        # loaded it already, so the common grant answers without a query.
        # For an anonymous user this is the whole decision, exactly as
        # ``allowed()`` answers it.
        if authorized_explicit_scoped_object_grant(
                user, perm, obj, checker=checker):
            decisions[action] = True
        else:
            missing.append((action, perm))
    if not getattr(user, "is_authenticated", False):
        missing = []
    if missing and checker is not None:
        _seed_action_role_memos(user, obj, checker)
    for action, perm in missing:
        decisions[action] = bool(
            authorized_platform_scoped_perm(user, perm, checker=checker)
            or authorized_role_membership_grant(user, perm, obj,
                                                checker=checker))
    return [action for action, _ in actions if decisions.get(action)]


def _as_queryset(klass):
    """``klass`` (model, manager or queryset) as a queryset, scoping kept.

    ``get_objects_for_user`` answers a superuser the queryset *as given*
    (guardian's ``with_superuser``); the platform axis must not silently
    drop a filter the caller composed into it either.
    """
    if isinstance(klass, models.QuerySet):
        return klass.all()
    if isinstance(klass, models.Manager):
        return klass.get_queryset()
    return klass.objects.all()


def _organization_scope_lookup(model):
    """How the rows of ``model`` are named by their organization, or ``None``.

    The list counterpart of the scoping ``authorized_role_membership_grant``
    applies per object: an organization is its own organization, exactly as
    ``object_organization`` answers it on the detail endpoint; every other
    model which stores an ``owner`` is scoped by it; a model which stores
    neither is decided by object grants alone, and the caller which gets
    ``None`` must not widen it by an axis of its own.
    """
    from accounts.models.groups import Organization

    if issubclass(model, Organization):
        return "pk__in"
    if not any(field.name == "owner" and not field.auto_created
               for field in model._meta.get_fields()):
        return None
    return "owner_id__in"


def _organization_scope_ids(user, perms, any_perm):
    """The organizations whose valid organization-scope roles grant ``perms``.

    ``any_perm`` decides how several permissions are combined - their union or
    their intersection - exactly as the queryset the caller builds accepts
    them. ``None`` is the answer when there is nothing to combine, so the
    caller adds no axis at all.
    """
    from accounts.models.roles import RoleScope

    org_ids = None
    for perm in perms:
        ids = set(_valid_membership_organization_ids(
            user, perm, RoleScope.ORGANIZATION))
        if org_ids is None:
            org_ids = ids
        elif any_perm:
            org_ids |= ids
        else:
            org_ids &= ids
    return org_ids


def objects_for_user(user, perm, klass, any_perm=False):
    """The list axis: the rows of ``klass`` which ``allowed()`` will pass.

    The one answer replacing today's ``get_objects_for_user`` calls with
    their per-call-site ``accept_global_perms`` - always ``False`` now
    (Q5=B), widened only by the axes which are deliberately wider than one
    object grant:

    * the break-glass superuser sees all rows (guardian's own
      ``with_superuser`` answer, kept),
    * a platform role which holds the permission sees all rows - that is
      what the scope of a platform definition means,
    * an organization role which holds the permission sees the rows of its
      own organization - the same ``owner`` scoping
      ``authorized_role_membership_grant`` applies on the detail endpoint,
      on the models which store an owner.

    Every other row must carry an explicit object grant, i.e. the rows the
    facade also passes on the detail endpoint; list, detail and hint answer
    one and the same question for one and the same user (#734). The
    returned queryset is a queryset: the callers of ``notify/``, the alerts
    and the organization filter compose it with their own filters as they
    did with ``get_objects_for_user``.

    Args:
        user: the user asking
        perm: one permission string, or a list of them
        klass: model class, manager or queryset to scope
        any_perm (bool): guardian's ``any_perm``, unchanged - with a list
            of permissions the platform and role axes widen as the returned
            queryset accepts: any of them with ``any_perm``, all of them
            without it
    """
    if audited_break_glass_superuser(user):
        return _as_queryset(klass)
    perms = perm if isinstance(perm, (list, tuple)) else [perm]
    platform_holds = [authorized_platform_scoped_perm(user, p) for p in perms]
    if (any(platform_holds) if any_perm else all(platform_holds)):
        return _as_queryset(klass)
    granted = get_objects_for_user(
        user, perm, klass=klass,
        accept_global_perms=GLOBAL_GRANTS_EFFECTIVE,
        any_perm=any_perm)

    # the organization-role axis, so a service which predates the creation
    # bootstrap is listed exactly as far as its editor may open it - one
    # query over the handful of memberships, not one per row
    queryset = _as_queryset(klass)
    model = queryset.model
    scope_lookup = _organization_scope_lookup(model)
    if scope_lookup is None:
        # the model stores no organization; its rows stay decided by object
        # grants, as authorized_role_membership_grant answers nothing there
        return granted
    org_ids = _organization_scope_ids(user, perms, any_perm)
    if org_ids:
        granted = granted | queryset.filter(**{scope_lookup: list(org_ids)})
    # the public axis of #739: what the anonymous viewer group may view,
    # every authenticated caller may view too - list and detail answer the
    # same (authorized_public_object_grant is the other half)
    public_ids = public_object_ids(model, perms[0] if len(perms) == 1
                                   else perms)
    if public_ids is not None:
        granted = granted | queryset.filter(pk__in=public_ids)
    return granted


def invalidate_permission_caches(user_or_group):
    """Drop Django's cached global permission strings after a write.

    Django caches the global permission strings on the *user instance*;
    across a request boundary this is self-healing (every request
    authenticates a fresh user), but within one process - a management
    command, a signal chain, a test which re-uses a user instance - a
    membership or permission written now is invisible to the cached
    instance. The receivers of ``accounts.signals`` and the write paths of
    ``RoleMembership`` call this; a caller must never pop the attributes
    by hand (#734).

    For a ``Group`` every member reachable in this process is refreshed; a
    user instance is cleared directly.
    """
    if user_or_group is None:
        return
    if isinstance(user_or_group, Group):
        for user in user_or_group.user_set.all():
            _pop_permission_caches(user)
        return
    _pop_permission_caches(user_or_group)


def _pop_permission_caches(user):
    for cache in PERMISSION_CACHES:
        user.__dict__.pop(cache, None)


class DjangoObjectPermissionsOrAnonReadOnly(DjangoObjectPermissions):
    """The API's gate: DRF's object permissions decided by the facade.

    The class answers DRF's two gates the way ``allowed()`` reads them;
    what it deliberately changes against the DRF classes it replaces is
    the "global AND object" split #734 retires:

    ``has_permission`` (before the object is read)
        * safe methods: as before - authenticated users and, because this
          class is read-only for anonymous ones, anonymous callers pass;
          the decision over the one object happens on the object gate;
        * ``PUT``/``PATCH``/``DELETE``: authentication only - these are
          object-scoped by DRF's own mixins and ``has_object_permission``
          is where the facade answers them. A legacy global
          ``change``/``delete`` no longer opens the endpoint before the
          object is even read; an object grant decides, and only the
          deliberately global axes can replace it;
        * ``POST`` (a create has no object): the right to register - the
          model gate of DRF for ``add`` plus the role axes of
          ``allowed_model_scope``.

    ``has_object_permission``
        ``allowed()`` per required permission, with the same 404-vs-403
        shape DRF's class had (an object the caller may not even view
        answers like it does not exist - #1319 asks the same of the
        incident endpoint).

    A custom unsafe ``detail=False`` action - none exists today - would
    need to call the facade itself; this class only vouches that the
    standard CRUD mixins reach ``has_object_permission``, which they do.
    """

    authenticated_users_only = False

    def has_permission(self, request, view):
        if not request.user or (
                not request.user.is_authenticated
                and self.authenticated_users_only):
            return False

        # Workaround to ensure DjangoModelPermissions are not applied
        # to the root view when using DefaultRouter.
        if getattr(view, "_ignore_model_permissions", False):
            return True

        queryset = self._queryset(view)
        if request.method in SAFE_METHODS:
            # DRF's own map asks for nothing on safe methods; the detail
            # endpoint decides per object, the list endpoint is scoped by
            # ``objects_for_user`` where its rows are permission-scoped at
            # all (#734)
            return True

        perms = self.get_required_permissions(request.method, queryset.model)
        if not perms:
            return True

        user = request.user
        if not user or not user.is_authenticated:
            return False

        if request.method == "POST":
            # the create gate: DRF's model gate stays for the ``add``
            # permission (the legacy grant retires with its data
            # migration, not with this class), and the role catalogue of
            # #731 + platform roles reach it through the facade
            perm = perms[0]
            return bool(user.has_perm(perm)
                        or allowed_model_scope(user, perm))

        # change / delete: object-scoped actions; the one answer is the
        # facade on has_object_permission. Consulting the retired global
        # here as well is the AND-gate #727 lists as the bug.
        return True

    def has_object_permission(self, request, view, obj):
        queryset = self._queryset(view)
        model_cls = queryset.model
        user = request.user
        checker = getattr(view, "perm_checker", None)

        perms = self.get_required_object_permissions(request.method,
                                                     model_cls)
        if not all(allowed(user, perm, obj, checker=checker)
                   for perm in perms):
            if request.method in SAFE_METHODS:
                # read permission failed anyway: answer like the object
                # was never there, 403 would confirm it
                raise Http404

            read_perms = self.get_required_object_permissions(
                "GET", model_cls)
            if not all(allowed(user, perm, obj, checker=checker)
                       for perm in read_perms):
                raise Http404
            return False

        return True
