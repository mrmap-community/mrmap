"""Sharing one service: role-scoped object grants (#740).

A *share* is a guardian object grant over one service, written onto the
**group of a role** (or onto one named user) with the decision recorded next
to it. Granting to the role group - not to each member and not to the whole
organization - is what makes leaving a role revoke everything at once
(#732: a ``Role`` *is* the enforcing group), and the metadata columns of
``extras.models.GrantMetadataMixin`` keep this write explainable down to the
person who did it (#741). There is no second ACL store: the rows written here
are the rows ``extras.permissions.allowed()`` reads, so list, detail and the
``allowedActions`` hint answer the same question a share changes.

The vocabulary the API and the publishing workflow share is defined here:

* ``shareable_actions`` - the actions a share of one service can carry: the
  three content-type scoped CRUD actions of the service model, plus the
  ``publish`` capability. The capability belongs to exactly one
  ``Permission`` row of the ``registry`` app - the one whose content type is
  ``webmapservice`` (see the carrier note on ``registry.models.service.
  WebMapService.Meta.permissions``) - so it is shareable where the object is
  that carrier. A grant row always points at the service it shares, and a
  guardian object grant and its permission must agree on the content type;
  inventing a second row per service kind would be a second vocabulary, not a
  second table.
* ``publisher_actions`` - what an accepted ``PublishRequest`` writes onto the
  requested organization's resources: ``view`` everywhere (without it the
  publisher cannot even reach the object) plus ``publish`` on the carrier.

The rows are written directly on the concrete through-models (the dedicated
performance tables of #735) instead of through ``guardian.shortcuts``: the
metadata is part of the same ``get_or_create``, and a re-share which finds the
row already there keeps its original provenance - the earlier decision is on
record, not the one which changed nothing. One existing row does get decided
by a later write: a bootstrap row of the owning organization's own roles
carries no ``granted_by``; if somebody explicitly shares exactly that action
with exactly that role, the share is the decision this row was missing and
stamps it, so the API never answers 201 for a grant its own listing then
hides.
"""
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.db import transaction

from registry.models.guardian import (
    WebFeatureServiceGroupObjectPermission,
    WebFeatureServiceUserObjectPermission,
    WebMapServiceGroupObjectPermission,
    WebMapServiceUserObjectPermission)
from registry.models.service import (WebFeatureService, WebMapService)

#: the CRUD actions a share can carry; they are spelled per model
#: (``change_webmapservice``), the way ``extras.permissions.CRUD_ACTIONS``
#: asks them
SHARE_ACTIONS = ("view", "change", "delete")

#: the capability action a share can carry additionally, where the service
#: model is the carrier of the registry capabilities
PUBLISH_ACTION = "publish"

#: the codename of the ``publish`` capability in the ``registry`` app
PUBLISH_CODENAME = "publish_resource"

#: the models whose shares are written to dedicated through-models; a model
#: outside this mapping shares nothing (its endpoint answers no share action)
THROUGH_MODELS = {
    WebMapService: {
        "group": WebMapServiceGroupObjectPermission,
        "user": WebMapServiceUserObjectPermission,
    },
    WebFeatureService: {
        "group": WebFeatureServiceGroupObjectPermission,
        "user": WebFeatureServiceUserObjectPermission,
    },
}

#: kind marker of a grant row in an API identifier (``"group-12"``); the two
#: tables of one service keep independent primary keys, so the id names the
#: kind next to the pk
GRANT_KINDS = ("group", "user")


def _through_models(service):
    """``{"group": model, "user": model}`` of ``service``'s own tables."""
    models = THROUGH_MODELS.get(service.__class__)
    if models is None:
        raise ValueError(
            f"{service.__class__.__name__} is not a shareable service model")
    return models


def is_shareable(model_or_instance) -> bool:
    """Whether ``model_or_instance`` is a model (or instance) whose grants
    the share machinery writes (the two service kinds of #740).

    The creation bootstrap of ``accounts.signals`` asks this before granting
    to publishers: a role-managed model which joins the list of #735 before
    joining ``THROUGH_MODELS`` must not break the registration it protects.
    """
    model = model_or_instance
    if not isinstance(model_or_instance, type):
        model = model_or_instance.__class__
    return model in THROUGH_MODELS


def permission_for(service, action) -> Permission:
    """The ``Permission`` row behind ``action`` of ``service``.

    CRUD actions name themselves after the model (``view_webmapservice``);
    ``publish`` is the app capability whose single row is carried by
    ``webmapservice`` (``shareable_actions`` is what keeps a caller from
    asking it of another model).
    """
    if action == PUBLISH_ACTION:
        codename = PUBLISH_CODENAME
        content_type = ContentType.objects.get_for_model(WebMapService)
    else:
        codename = f"{action}_{service._meta.model_name}"
        content_type = ContentType.objects.get_for_model(service)
    return Permission.objects.get(codename=codename,
                                  content_type=content_type)


def is_capability_carrier(service) -> bool:
    """Whether ``service``'s model carries the registry capabilities."""
    return isinstance(service, WebMapService)


def action_for(codename: str) -> str:
    """The action name an object-grant permission codename answers with.

    ``change_webmapservice`` is ``change``; the capability row of the
    carrier is ``publish``. The inverse of what ``permission_for`` builds.
    """
    if codename == PUBLISH_CODENAME:
        return PUBLISH_ACTION
    for action in SHARE_ACTIONS:
        if codename.startswith(f"{action}_"):
            return action
    return codename


def shareable_actions(service) -> tuple:
    """The actions a share of ``service`` can carry."""
    actions = list(SHARE_ACTIONS)
    if is_capability_carrier(service):
        actions.append(PUBLISH_ACTION)
    return tuple(actions)


def publisher_actions(service) -> tuple:
    """The actions an accepted ``PublishRequest`` writes onto ``service``.

    ``view`` so the publisher of the other organization reaches the object at
    all - the facade's object axis asks ``view_<model>`` like any other read
    - and ``publish`` where the model carries the capability.
    """
    actions = ["view"]
    if is_capability_carrier(service):
        actions.append(PUBLISH_ACTION)
    return tuple(actions)


def grant_actions(service, target, actions, granted_by=None) -> list:
    """Write the object grants of ``actions`` over ``service`` to ``target``.

    Args:
        service: the WMS or WFS the grants are over
        target: the ``Group`` (normally the group of a role) or the ``User``
            receiving the grants
        actions: names from ``shareable_actions(service)``
        granted_by: the person the write is credited to; ``None`` marks a
            mechanical write (the bootstrap path of a new resource, #741)

    Returns:
        list: ``(kind, row)`` pairs like ``share_grants`` answers, so that
            the caller can answer the same grant id it would list
    """
    models = _through_models(service)
    is_user = isinstance(target, get_user_model())
    if not is_user and not isinstance(target, Group):
        raise TypeError(
            "a share target is a user or a group (the group of a role), "
            f"not {target.__class__.__name__}")
    kind = "user" if is_user else "group"
    model = models[kind]
    grants = []
    with transaction.atomic():
        for action in actions:
            permission = permission_for(service, action)
            row, created = model.objects.get_or_create(
                permission=permission,
                content_object=service,
                **{kind: target},
                defaults={"granted_by": granted_by})
            if not created and granted_by is not None \
                    and row.granted_by is None:
                # The creation bootstrap wrote this row without a decider;
                # this call IS the decision - stamp it, or the share would
                # answer 201 and then not appear in its own listing. A row
                # that already names a decider keeps it: the earlier
                # decision is on record, not the one which changed nothing.
                row.granted_by = granted_by
                row.save(update_fields=["granted_by"])
            grants.append((kind, row))
    return grants


def share_grants(service) -> list:
    """The decided grants over ``service``, newest last.

    A row *with* a ``granted_by`` is a decision a person or an accepting
    workflow wrote - a share, or the resource grants of an accepted
    ``PublishRequest`` (whose own row is gone after acceptance, #740). The
    bootstrap grants of the owning organization's own roles carry no
    ``granted_by`` and are not shares: they are who manages the resource at
    home, not somebody it was shared with.
    """
    models = _through_models(service)
    group_rows = list(models["group"].objects.filter(
        content_object=service, granted_by__isnull=False).select_related(
            "group", "group__role", "group__role__organization",
            "group__role__role_definition", "granted_by", "permission"))
    user_rows = list(models["user"].objects.filter(
        content_object=service, granted_by__isnull=False).select_related(
            "user", "granted_by", "permission"))
    grants = [("group", row) for row in group_rows]
    grants += [("user", row) for row in user_rows]
    grants.sort(key=lambda item: (item[1].created_at, item[0], item[1].pk))
    return grants


def grant_id(kind: str, row) -> str:
    """The API identifier of one grant row."""
    return f"{kind}-{row.pk}"


def revoke_share(service, grant: str) -> bool:
    """Delete exactly one decided grant row over ``service``.

    Only rows ``share_grants`` lists are revocable: a bootstrap grant of the
    owning organization's own roles is not a share, and reaching its pk
    through another path must not turn it into one - administering those
    grants stays with the role work, not with this endpoint.

    Args:
        service: the service whose share is revoked
        grant: the ``grant_id`` the API answered (``"<kind>-<pk>"``)

    Returns:
        bool: whether a decided grant of *this* service was deleted - a
            foreign pk, an undecided row or an unknown kind deletes nothing
            and says so
    """
    kind, _sep, pk = grant.partition("-")
    if kind not in GRANT_KINDS:
        return False
    try:
        row_pk = int(pk)
    except ValueError:
        return False
    models = _through_models(service)
    deleted, _detail = models[kind].objects.filter(
        pk=row_pk, content_object=service,
        granted_by__isnull=False).delete()
    return bool(deleted)
