"""The visibility of a resource as an SQL expression (#739).

Visibility is not a column - it is an answer about the guardian object grants
of a resource, and the #734 facade answers that answer from the very same
grants which decide the detail endpoint:

* **public** - the anonymous viewer role group of the platform (#739) holds
  ``view_<model>`` over the resource; the guardian anonymous user is a member
  of that group, so this grant is what an anonymous list endpoint must
  reproduce, exactly and in SQL,
* **organization-internal** - a group which *is* a role of the resource's
  owning organization holds ``view_<model>``; the organization is read through
  ``group__role__organization_id`` against the outer row's ``owner_id``, so a
  null owner answers "no organization grant" the way SQL compares nulls and
  never needs a second condition,
* **restricted** - everything else: a resource granted to individually named
  groups or users only (#740 shares with these), or with no grant at all.

All three are one ``CASE`` over ``EXISTS`` subqueries on the dedicated
guardian tables of the model (#735), so the answer costs no query per row and
none per role - the serializer answers it on every page.
"""
from django.apps import apps
from django.db.models import (Case, CharField, Exists, OuterRef, Value, When)
from django.db.models.functions import Cast

#: ``{model: through-model or None}`` - the app registry does not change after
#: startup, so the walk of ``dedicated_obj_perm_models`` is worth one per model
_group_perms_cache = {}


def group_perms_model(model):
    """The class of ``model``'s group grants, or None for the generic table.

    guardian's ``get_group_obj_perms_model`` answers the same question, but it
    decides by comparing *content types*, which reads ``django_content_type``.
    An annotation is built by code which may not read a database at all: the
    schema and permission paths of ``tests_nested_service_schema.py`` build one
    without allowing a query, and #739's first CI run died there. So this asks
    the declaration the checks of #735 audit instead - the same source E002
    compares against the code, which is what makes the two answers unable to
    drift apart.

    Args:
        model: the model whose group grants are asked

    Returns:
        model class or None: the dedicated ``…GroupObjectPermission`` of
            ``model``, or ``None`` when its grants live in guardian's generic
            table - which includes the half a pair E002 reports, because a
            missing group side means exactly that table holds the grants
    """
    if model not in _group_perms_cache:
        from accounts.checks import SIDES, dedicated_obj_perm_models

        pair = dedicated_obj_perm_models().get(model)
        _group_perms_cache[model] = pair[SIDES[1]] if pair else None
    return _group_perms_cache[model]


def _granted_to_view_expr(model, group_condition):
    """An ``EXISTS`` over the object grants of ``view_<model>``.

    Args:
        model: the model whose grants are asked
        group_condition: kwargs naming the holding group, e.g.
            ``group_id__in=<subquery>`` or a join through the role's
            organization

    Returns:
        Exists: the expression for the outer row
    """
    from guardian.models import GroupObjectPermission

    through_model = group_perms_model(model)
    generic = through_model is None
    if generic:
        # no dedicated table: the grants of every model share guardian's
        # generic pair, which names the object by content type and text
        through_model = GroupObjectPermission
    grants = through_model.objects.filter(
        permission__codename=f"view_{model._meta.model_name}",
        permission__content_type__app_label=model._meta.app_label,
        **group_condition)
    if generic:
        grants = grants.filter(
            content_type__app_label=model._meta.app_label,
            content_type__model=model._meta.model_name,
            object_pk=Cast(OuterRef("pk"), output_field=CharField()))
    else:
        grants = grants.filter(content_object_id=OuterRef("pk"))
    return Exists(grants)


def anonymous_viewer_group_ids():
    """A subquery of the pk of the anonymous viewer's group, or none.

    Resolved through the ``Role`` row of the definition - never through the
    name of the group (#732) - so a rename of anything changes no visibility.
    An un-migrated database answers no id, which makes every resource
    non-public rather than raising over a missing row.
    """
    Role = apps.get_model("accounts", "Role")
    from accounts.models.roles import ANONYMOUS_VIEWER_ROLE

    return Role.objects.filter(
        role_definition__slug=ANONYMOUS_VIEWER_ROLE,
        is_active=True).values("group_id")


def visibility_expression(model):
    """The ``CASE`` which annotates ``visibility`` on a queryset of ``model``.

    The order of the ``WHEN``s is the precedence: a public resource which is
    also held by its organization's roles reads **public** - the statement
    about anonymous visitors is the one an operator needs to see.

    Args:
        model: a role-managed model, i.e. one with an ``owner`` to its
            organization (#733) and dedicated guardian tables (#735)

    Returns:
        Case: the annotation expression, answering the values of
            ``extras.permissions.Visibility``
    """
    from extras.permissions import Visibility

    public = _granted_to_view_expr(
        model, {"group_id__in": anonymous_viewer_group_ids()})
    organization_internal = _granted_to_view_expr(
        model, {"group__role__organization_id": OuterRef("owner_id")})
    return Case(
        When(public, then=Value(Visibility.PUBLIC.value)),
        When(organization_internal,
             then=Value(Visibility.ORGANIZATION_INTERNAL.value)),
        default=Value(Visibility.RESTRICTED.value),
        output_field=CharField())
