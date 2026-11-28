"""The route gate of the write across the public axis (#1808).

A ``PATCH`` naming ``visibility`` is the API's only carrier of publishing
(#739), and it is decided twice:

1. the endpoint gate of the viewset, which DRF's ``perms_map`` answers with
   the viewset's ``change_<model>``, and
2. the designated decision of ``VisibilitySerializerMixin``, which asks
   ``registry.publish_resource`` - and additionally
   ``registry.manage_access_rules`` for the way back from the public.

The shipped catalogue of #731 splits exactly those two rights over two roles:
``resource_editor`` holds ``change_webmapservice``, ``resource_publisher``
holds ``publish_resource`` (``accounts/management/commands/sync_role_definitions.py``)
and the creation bootstrap grants the object triple to the group of the role
whose *definition* may change the model - the editors' group. So a member of
``resource_publisher`` alone, the role the handbook names for publishing, was
answered 403 by gate 1 and never reached gate 2, while ``allowedActions`` -
which reports the capability axis of gate 2 - offered ``publish``. The share
route of the same viewset never had this problem, because
``ServiceSharePermissions`` asks the action's own capability instead of
``change``; this class is the same answer for the visibility write.

The rule of the class: a ``PATCH`` which names **nothing but** ``visibility``
speaks about the public axis only, and the public axis belongs to the publish
capability - ``registry.publish_resource``, plus
``registry.manage_access_rules`` for the withdrawal. Any other unsafe request,
including a ``PATCH`` which mixes visibility with content, keeps the
viewset's own gate untouched: editing stays the editor's axis, and such a
write needs both rights, exactly as the serializer already decides it.

Which value was asked is *not* decided here: ``restricted`` and an unknown
word are field answers of the serializer (400), and this gate only says who
may speak about visibility at all.
"""
from django.http import Http404

from extras.permissions import (DjangoObjectPermissionsOrAnonReadOnly,
                                Visibility, allowed)

#: the attribute whose write this gate decides
VISIBILITY_ATTRIBUTE = "visibility"

#: the members of a JSON:API document which are not attributes of the resource
DOCUMENT_KEYS = frozenset(("data", "type", "id", "attributes", "meta"))


def requested_visibility(request):
    """The visibility a ``PATCH`` asks for, or ``None`` for any other write.

    ``None`` answers for anything which is not a write across the public axis
    alone: another method, a body which names any other attribute (a mixed
    write is a content write too and stays on the viewset's ``change`` gate),
    or no body at all.

    Two shapes of a body are read, because a gate runs before the view's
    serializer and cannot know which parser answered: the JSON:API parser of
    the project hands the resource flat, its document members beside its
    snake_cased attributes, and a body which arrived unprocessed still
    carries the ``data`` envelope with its ``attributes``. Both carry the same
    information, so both decide the same.
    """
    if request.method != "PATCH":
        return None
    data = request.data if isinstance(request.data, dict) else {}
    document = data.get("data")
    if isinstance(document, dict):
        nested = document.get("attributes")
        attributes = nested if isinstance(nested, dict) else document
    else:
        attributes = data
    named = {key for key, value in attributes.items()
             if key not in DOCUMENT_KEYS and value not in (None, {}, [])}
    return attributes.get(VISIBILITY_ATTRIBUTE) \
        if named == {VISIBILITY_ATTRIBUTE} else None


class VisibilityWritePermissions(DjangoObjectPermissionsOrAnonReadOnly):
    """The gate of the services whose visibility the API writes (WMS, WFS).

    Everything is the viewset's class except the object gate of a
    visibility-only ``PATCH``, which opens for the publish pair of the facade
    as well: so the publisher of the owning organization publishes and the
    organization administrator who manages the access rules can take the
    resource back from the public.

    The ordinary axis is kept beside it - a caller which holds the viewset's
    ``change`` still reaches the serializer, which is the designated decision
    point and answers a would-be publisher without the publish permission
    with its own, readable refusal instead of the endpoint's generic one.
    """

    def has_object_permission(self, request, view, obj):
        if super().has_object_permission(request, view, obj):
            return True

        requested = requested_visibility(request)
        if requested is None:
            # not the public axis: the viewset's own answer above stands,
            # including its 404 for a caller which may not view the resource
            return False

        app_label = obj._meta.app_label
        checker = getattr(view, "perm_checker", None)
        user = request.user
        if allowed(user, f"{app_label}.publish_resource", obj,
                   checker=checker):
            return True
        if requested == Visibility.ORGANIZATION_INTERNAL.value \
                and allowed(user, f"{app_label}.manage_access_rules", obj,
                            checker=checker):
            # the way back is also the act of whoever manages the access
            # rules of the resource - the pair check_visibility_write decides
            return True

        # the 404-vs-403 shape of the base class: a caller which may not even
        # read the resource learns nothing about its existence
        if not allowed(user, f"{app_label}.view_{obj._meta.model_name}", obj,
                       checker=checker):
            raise Http404
        return False
