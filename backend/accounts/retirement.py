"""Retiring the legacy per-model role groups (#741).

Migration 0008 could not delete the per-model ``<Org> WebMapService Admins``
groups a running instance already had: django-guardian's rows point at a
``Group`` by key, so a group which is still granted something has to outlive
the bootstrap which wrote it. It marked them as *inactive roles* instead and
handed this module the list - ``Role.objects.retired()``, narrowed by
:func:`is_legacy_model_group` so that a role an administrator retired over the
api of #736 is never deleted by a migration.

Deleting one is only safe once what it granted has been reconciled, which is
what decision Q5 = B of #727 insists on ("do not delete guardian groups or rows
until the migrated role grants have been reconciled"). This module is exactly
that reconciliation, and nothing else:

* the **members** of the retired group are adopted into the *active* role of the
  same definition and organization - the successor. Their two role axes then
  answer through #734 the way they did through the group;
* every **object grant** of the retired group is classified one row at a time.
  A row whose permission the definition of the retired role holds, on an object
  of that same organization, is *covered*: the ORGANIZATION-role axis of #734
  already grants that person that permission over that object, so the row is
  redundant and goes with the group. A row nothing in the catalogue grants is
  *preserved* by writing it onto each member who already held it, which broadens
  nothing (only people who had it keep it) and loses nothing;
* the **mapping** of both - who went where, which row went which way - is
  recorded in ``LegacyGroupRetirement`` before the group is deleted, because a
  deleted ``Group`` has no history and its guardian rows cascade away with it.

A group whose reconciliation cannot be proven is **declined**: it stays retired
and the report names why. The guards which decide that are the anonymous viewer
(a grant must never become public through a migration - decision Q2 of #727) and
the ``Organization`` (whose row *is* an ``auth.Group`` row and must never be
deleted as one).

Everything here takes an app registry and reads no custom method of the live
models, so the same code runs from the data migration - with the migration state
- and from ``manage.py retire_legacy_role_groups`` - with the real registry -
including ``--dry-run``, which answers the report without writing a row.
"""

from django.apps import apps as global_apps
from django.conf import settings
from django.db import transaction

#: the disposition of a grant row which the successor's role already grants
#: through the facade of #734, so the row is redundant and goes with the group
COVERED_BY_ROLE = "covered_by_role"

#: the disposition of a grant row which no role grants: it is written onto the
#: members which already held it, so their rights stand while the group goes
PRESERVED_PER_USER = "preserved_per_user"

#: whether an uncovered grant is preserved per user (``True``) or dropped with
#: the group (``False``). ``True`` is the reading of Q5 = B this repository pins
#: in ``tests/django/accounts/test_role_migration.py``: the person who could
#: change something before the upgrade can change the same thing after it. The
#: catalogue of #731 grants no ``delete_<model>`` to any role, so the delete
#: grants of the legacy per-model administrators are exactly such an uncovered
#: grant: dropping them would silently narrow rights. An operator who decides
#: that the legacy delete right should lapse - Q5 = B also says legacy grants
#: are "not retained as an indefinite compatibility rule" - flips this one
#: constant, and the record of every affected row is in
#: ``LegacyGroupRetirement.grants`` either way.
PRESERVE_UNCOVERED_GRANTS = True

#: the slug which may never be a successor: taking a legacy group's grants onto
#: the anonymous viewer role would publish whatever that group holds
ANONYMOUS_VIEWER_SLUG = "anonymous_viewer"

#: the label of the model whose rows are the organizations
ORGANIZATION_LABEL = "accounts.Organization"

#: the suffix migration 0008 found on the per-model groups of an organization,
#: between the organization name and it the Django-lowercased model name
#: (``LEGACY_MODEL_ADMINS`` of that migration, repeated because a migration and
#: this module may not import each other's state)
LEGACY_MODEL_ADMINS = "Admins"


def is_legacy_model_group(apps, role) -> bool:
    """Whether ``role`` is one of the per-model groups migration 0008 left.

    The name is the evidence: 0008 only ever took a group called
    ``"<organization> <model> Admins"``, while a role created over the api of
    #736 carries ``"<organization>: <slug>"`` (``role_group_name``). Asking the
    shape instead of ``is_active`` matters: an administrator may retire a live
    role through the api to take it out of the member picker without deleting
    it, and such a role is nobody's migration business. The model token is
    asked of the ``ContentType`` table so a group which merely *reads* like a
    legacy one - an organization named after a model, say - is not retired on
    a coincidence.
    """
    organization = getattr(role, "organization", None)
    group = getattr(role, "group", None)
    if organization is None or group is None:
        return False
    prefix = f"{organization.name} "
    if not group.name.startswith(prefix) or not group.name.endswith(
            f" {LEGACY_MODEL_ADMINS}"):
        return False
    model_name = group.name[
        len(prefix):-len(LEGACY_MODEL_ADMINS) - 1]
    return apps.get_model("contenttypes", "ContentType").objects.filter(
        model=model_name).exists()


def _field_names(model) -> set:
    return {field.name for field in model._meta.get_fields()}


def is_generic(perm_model) -> bool:
    """Whether ``perm_model`` is guardian's shared table (text object pk).

    Asked by shape rather than by base class, because a migration app registry
    builds its own model classes which do not inherit
    ``UserObjectPermissionBase`` / ``GroupObjectPermissionBase``.
    """
    names = _field_names(perm_model)
    return "object_pk" in names and "content_type" in names


def _is_grant_table(model, grantee) -> bool:
    """Whether ``model`` stores an object grant for ``grantee`` ('user'/'group')."""
    names = _field_names(model)
    if grantee not in names or "permission" not in names:
        return False
    return "content_object" in names or is_generic(model)


def group_grant_models(apps) -> list:
    """Every model which stores an object grant of a *group*."""
    return [model for model in apps.get_models()
            if _is_grant_table(model, "group")]


def _user_grant_table(apps, group_model):
    """The model storing the same kind of grant for a *user*, or ``None``.

    The counterpart of a group table: its dedicated twin for the same target
    model, or guardian's shared ``UserObjectPermission`` for the shared table.
    Without a counterpart a grant can only be covered or declined, never
    preserved.
    """
    targets = {}
    for model in apps.get_models():
        if not _is_grant_table(model, "user"):
            continue
        generic = is_generic(model)
        target = None
        if not generic:
            target = model._meta.get_field(
                "content_object").related_model._meta.label
        targets[(generic, target)] = model
    if is_generic(group_model):
        return targets.get((True, None))
    related = group_model._meta.get_field(
        "content_object").related_model._meta.label
    return targets.get((False, related))


def group_grant_rows(apps, group):
    """Every guardian grant row which points at ``group``.

    Yields ``(grant_model, row)`` for each row of every group grant table. The
    permission is joined in: every classification asks it, so reading it is not
    a per-row surprise (the convention of #1388).
    """
    for grant_model in group_grant_models(apps):
        yield from grant_model.objects.filter(
            group=group).select_related("permission__content_type")


def grant_object(row):
    """The object ``row`` grants over, or ``None`` when it cannot be resolved.

    A dangling generic reference - a row whose object is gone - answers ``None``,
    which the caller reads as *not proven covered*. That is the safe side: an
    unresolvable object is never evidence that a role grants the row.
    """
    model = row._meta.model
    if is_generic(model):
        content_type = getattr(row, "content_type", None)
        if content_type is None:
            return None
        try:
            return content_type.get_object_for_this_type(pk=row.object_pk)
        except Exception:
            # any failure of the lookup means "no object", and "no object" is
            # not "covered"; the row itself stays in the report either way
            return None
    return getattr(row, "content_object", None)


def _object_of(apps, label, pk):
    """The row of ``label`` with ``pk``, read from the same registry."""
    model = apps.get_model(*label.split("."))
    return model.objects.filter(pk=pk).first()


def object_organization(apps, obj):
    """The organization ``obj`` belongs to, or ``None``.

    The same rule ``extras.permissions.object_organization`` applies on a
    request, read from the row's own columns so it costs nothing extra: an
    organization is its own organization, a secured resource is scoped by its
    typed ``owner``, anything else knows no organization. Models and fields are
    read through the app registry, because this runs from a data migration too.
    """
    if obj is None:
        return None
    if obj._meta.label == ORGANIZATION_LABEL:
        return obj
    owner_field = next(
        (field for field in obj._meta.get_fields()
         if field.name == "owner" and field.is_relation), None)
    if owner_field is None:
        return None
    owner_pk = getattr(obj, owner_field.attname, None)
    if owner_pk is None:
        return None
    return _object_of(apps, ORGANIZATION_LABEL, owner_pk)


def classify_grant(apps, role, row) -> dict:
    """What becomes of ``row`` when ``role``'s group is retired.

    The single place which decides the disposition, asked identically by
    ``plan_role`` and by the applier - a plan which is not the application would
    be a report nobody can trust.
    """
    permission = row.permission
    obj = grant_object(row)
    organization = object_organization(apps, obj)
    covered = (
        organization is not None
        and organization.pk == role.organization_id
        and permission is not None
        and role.role_definition.permissions.filter(
            pk=permission.pk).exists())
    if covered:
        disposition = COVERED_BY_ROLE
    elif PRESERVE_UNCOVERED_GRANTS:
        disposition = PRESERVED_PER_USER
    else:
        disposition = "dropped"
    return {
        "table": row._meta.model._meta.db_table,
        "row_pk": row.pk,
        "permission": (f"{permission.content_type.app_label}."
                       f"{permission.codename}"
                       if permission is not None else None),
        "object": str(getattr(row, "object_pk", None) or
                      getattr(row, "content_object_id", "") or ""),
        "disposition": disposition,
    }


def _member_users(apps, group) -> list:
    """The people whose rights the retired group carries.

    Guardian's anonymous user and every inactive user are never among them:
    adopting either into a role group would make whatever that group grants
    public, and Q2 of #727 allows no migration to publish anything.
    """
    anonymous = getattr(
        settings, "GUARDIAN_ANONYMOUS_USER_NAME", "AnonymousUser")
    return [user for user in group.user_set.all()
            if user.username != anonymous and user.is_active]


def _user_model_label() -> str:
    label, model = settings.AUTH_USER_MODEL.split(".")
    return f"{label}.{model}"


def plan_role(apps, role) -> dict:
    """What retiring ``role`` would do, without doing it.

    Returns the successor, the members and where each goes, one entry per grant
    row of the group with its disposition, and - when the group must not be
    deleted - ``declined`` naming the reason.
    """
    Role = apps.get_model("accounts", "Role")
    group = role.group
    plan = {
        "group_pk": group.pk,
        "group_name": group.name,
        "definition": role.role_definition.slug,
        "organization": (role.organization.name if role.organization
                         else None),
        "role_definition_pk": role.role_definition_id,
        "organization_pk": role.organization_id,
        "successor": None,
        "successor_pk": None,
        "members": [],
        "grants": [],
        "declined": None,
    }

    # an Organization IS an auth.Group row: 0008 never took one for a legacy
    # role, and nothing here ever deletes one either
    if apps.get_model("accounts", "Organization").objects.filter(
            pk=group.pk).exists():
        plan["declined"] = "the group row is an organization"
        return plan
    if role.organization_id is None:
        plan["declined"] = "a retired role which names no organization"
        return plan
    definition = role.role_definition
    if definition.slug == ANONYMOUS_VIEWER_SLUG:
        plan["declined"] = "the anonymous viewer role is never a successor"
        return plan

    successor = Role.objects.filter(
        role_definition=definition,
        organization=role.organization,
        is_active=True).select_related("group").first()
    if successor is None:
        # the members would lose the role, and the group its grants, with no
        # row left to point at: leave the group standing and say so
        plan["declined"] = (
            f"no active role of '{definition.slug}' for "
            f"{role.organization.name}")
        return plan
    plan["successor"] = str(successor)
    plan["successor_pk"] = successor.pk

    holding = set(successor.group.user_set.values_list(
        "username", flat=True))
    for user in _member_users(apps, group):
        plan["members"].append({
            "user": user.username,
            "action": ("already_in_successor" if user.username in holding
                       else "adopted"),
        })

    for _, row in group_grant_rows(apps, group):
        plan["grants"].append(classify_grant(apps, role, row))
    return plan


def _adopt_members(apps, plan, successor):
    """Give every member of the retired group the successor role.

    The membership row is the person-readable statement of the grant, the group
    is the enforcement; both are written here because the model's own ``save`` -
    which keeps them in step - is not in the migration state this may run from.
    """
    if successor is None:
        return
    RoleMembership = apps.get_model("accounts", "RoleMembership")
    User = apps.get_model(*_user_model_label().split("."))
    for entry in plan["members"]:
        if entry["action"] != "adopted":
            continue
        user = User.objects.filter(username=entry["user"]).first()
        if user is None:
            continue
        RoleMembership.objects.get_or_create(
            role=successor, user=user, defaults={"granted_by": None})
        # the group is what enforces, so it is written regardless of whether
        # the membership row was already there - a row without the group would
        # be the stale grant this whole module is about
        successor.group.user_set.add(user)


def _grant_model_by_table(apps, table):
    """The group grant model whose table is ``table`` (the plan names rows by it)."""
    for model in group_grant_models(apps):
        if model._meta.db_table == table:
            return model
    return None


def _preserve_grant(user_model, user, row, obj) -> bool:
    """Write ``row`` onto ``user`` directly, so their rights do not go with it.

    ``get_or_create`` rather than a bulk insert: a re-run may meet a row it
    wrote a moment ago, and a duplicate is exactly what guardian's
    ``unique_together`` keeps a grant single with. Answers whether the grant is
    written, including when it was already there.
    """
    if obj is None:
        # an unresolvable object cannot be granted to anybody; the row is
        # reported as dropped, which is the difference an operator must see
        return False
    grantee = {"user": user, "permission": row.permission}
    if is_generic(user_model):
        content_type = getattr(row, "content_type", None)
        if content_type is None:
            return False
        grantee["content_type"] = content_type
        grantee["object_pk"] = str(row.object_pk)
    else:
        grantee["content_object"] = obj
    user_model.objects.get_or_create(**grantee)
    return True


def _reconcile_grants(apps, plan, role) -> tuple:
    """Apply every disposition of ``plan`` and delete the rows.

    Returns ``(covered, preserved)``. Every row of the retired group goes - that
    is the point of the retirement - and every one of them is in
    ``plan["grants"]`` with its disposition before it does.
    """
    covered = preserved = 0
    by_username = {user.username: user for user in _member_users(
        apps, role.group)}
    members = [by_username[entry["user"]] for entry in plan["members"]
               if entry["user"] in by_username]

    for entry in plan["grants"]:
        grant_model = _grant_model_by_table(apps, entry["table"])
        row = (grant_model.objects.filter(pk=entry["row_pk"]).first()
               if grant_model is not None else None)
        if row is None:
            continue
        if entry["disposition"] == COVERED_BY_ROLE:
            covered += 1
        elif entry["disposition"] == PRESERVED_PER_USER:
            user_model = _user_grant_table(apps, grant_model)
            obj = grant_object(row)
            if user_model is None or obj is None:
                # nothing can hold the grant per user, or the object it pointed
                # at is gone: say so in the record instead of pretending
                entry["disposition"] = "dropped"
            else:
                for user in members:
                    _preserve_grant(user_model, user, row, obj)
                preserved += 1
        grant_model.objects.filter(pk=entry["row_pk"]).delete()
    return covered, preserved


def _record(apps, plan, covered, preserved):
    """Write the audit record of one retired group.

    Written *before* the group is deleted, keyed by its primary key: an auditor
    of an upgraded instance reads this table to answer whose rights came from
    which legacy group and whether anything was broadened.
    """
    LegacyGroupRetirement = apps.get_model("accounts", "LegacyGroupRetirement")
    Role = apps.get_model("accounts", "Role")
    successor = (Role.objects.filter(pk=plan["successor_pk"]).first()
                 if plan.get("successor_pk") else None)
    record, _ = LegacyGroupRetirement.objects.get_or_create(
        group_pk=plan["group_pk"],
        defaults={
            "group_name": plan["group_name"],
            "role_definition_id": plan["role_definition_pk"],
            "organization_id": plan["organization_pk"],
            "successor": successor,
            "members": plan["members"],
            "grants": plan["grants"],
            "grants_covered": covered,
            "grants_preserved": preserved,
        })
    return record


def retire_role(apps, role) -> dict:
    """Reconcile and delete one retired role with its group.

    Returns the plan which was applied, or the plan which names why nothing was
    applied. One group is one transaction - members, grants, record, role and
    group - because a group which is gone has to be gone with its mapping
    recorded, never half of it.
    """
    plan = plan_role(apps, role)
    if plan["declined"]:
        return plan

    Role = apps.get_model("accounts", "Role")
    successor = Role.objects.filter(pk=plan["successor_pk"]).first()
    with transaction.atomic():
        _adopt_members(apps, plan, successor)
        covered, preserved = _reconcile_grants(apps, plan, role)
        _record(apps, plan, covered, preserved)
        group = role.group
        role.delete()
        group.delete()
    plan["grants_covered"] = covered
    plan["grants_preserved"] = preserved
    return plan


def retire_legacy_role_groups(apps=None, dry_run=False) -> dict:
    """Retire every legacy group which reconciles; report the rest.

    Args:
        apps: the app registry to work on - the migration state from a data
            migration, ``django.apps.apps`` from the management command
        dry_run (bool): answer the plan of every group without writing

    Returns:
        dict: ``retired`` (the plans applied, or planned with ``dry_run``),
        ``declined`` (the plans which named a reason), ``skipped`` (the
        inactive roles which are not legacy per-model groups, named only) and
        ``dry_run``
    """
    if apps is None:
        apps = global_apps
    Role = apps.get_model("accounts", "Role")
    report = {"retired": [], "declined": [], "skipped": [],
              "dry_run": dry_run}
    # Role.objects.retired() is the named selection of #741; the manager's own
    # method is not in the migration state this runs from, so the filter is
    # spelled out here
    for role in list(Role.objects.filter(is_active=False).select_related(
            "group", "role_definition", "organization")):
        if not is_legacy_model_group(apps, role):
            # an inactive role of the api's own shape was retired by a person
            # who may still undo it: it is reported, never deleted
            report["skipped"].append(role.group.name)
            continue
        plan = plan_role(apps, role) if dry_run else retire_role(apps, role)
        report["declined" if plan["declined"] else "retired"].append(plan)
    return report
