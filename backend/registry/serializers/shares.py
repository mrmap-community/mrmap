"""JSON payloads of the share endpoints of a service (#740).

Two plain serializers, no model: a share is a guardian grant row of the
service's own through-tables, and its answer shape is a *projection* over
that row - the target named through the role it belongs to, the action cut
back to the vocabulary of ``registry.models.shares``. The schedule preview of
#1327 established that a non-resource action of this API answers a plain
JSON body; these serializers carry that body for the schema and for one
canonical shape between view and response.

The registry *share* and the OGC proxy's *access rules* are deliberately not
one vocabulary (#740): a share writes guardian object grants and is answered
under the service's own ``/share`` route; an access rule is an
``Allowed*Operation`` row with its own nested resources. The naming here is
what the UI shows apart.
"""
from django.contrib.auth import get_user_model
from django.core.exceptions import ObjectDoesNotExist
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from accounts.models.roles import Role
from registry.models.shares import action_for

User = get_user_model()


def _role_of_group(group):
    """The ``Role`` a granted group answers to, or ``None``.

    The share target is the group *of a role* (#732), so a group row names
    its role through the reverse one-to-one; the legacy shape of a grant
    onto a whole organization (``add_publisher`` before #740) and a plain
    group have no role behind them and answer by themselves.
    """
    try:
        return group.role
    except ObjectDoesNotExist:
        return None


def _organization_of_group(group):
    """The ``Organization`` a granted group is, or ``None``.

    An ``Organization`` *is* a ``Group`` (multi-table inheritance), so the
    child row is reached through the implicit one-to-one accessor and is
    simply absent for a plain group.
    """
    try:
        return group.organization
    except ObjectDoesNotExist:
        return None


class ShareGrantSerializer(serializers.Serializer):
    """The answer shape of one share grant, for the OpenAPI document.

    The response is built by ``share_grant_payload`` as a plain dict (the
    schedule preview of #1327 established that a non-resource action of this
    API answers plain JSON); this serializer states the same fields for the
    schema and is not instantiated.
    """

    id = serializers.CharField(read_only=True)
    #: "role" | "organization" | "user" - what the grant was written onto
    target_kind = serializers.CharField(read_only=True)
    #: the primary key of the answer target (the role, the organization or
    #: the user) - what a revoke of the whole target would address later
    target_id = serializers.IntegerField(read_only=True, allow_null=True)
    #: the human-readable name of the target, ready for the share list
    target_name = serializers.CharField(read_only=True)
    #: the slug of the role definition behind a role target, else None
    role = serializers.CharField(read_only=True, allow_null=True)
    #: the organization the role belongs to (role targets), or the
    #: organization the grant sits on directly (legacy), else None
    organization = serializers.CharField(read_only=True, allow_null=True)
    #: the action name from ``registry.models.shares.SHARE_ACTIONS`` +
    #: ``publish``, cut from the permission codename
    action = serializers.CharField(read_only=True)
    #: the guardian permission codename behind the action
    permission = serializers.CharField(read_only=True)
    #: who wrote the grant; the list only contains rows with a decider -
    #: the bootstrap grants of the owning organization are not shares
    granted_by = serializers.CharField(read_only=True, allow_null=True)
    created_at = serializers.DateTimeField(read_only=True)


def share_grant_payload(kind, row) -> dict:
    """The dict answer of one ``(kind, row)`` grant pair.

    Field names and semantics are ``ShareGrantSerializer``; the keys are
    camelCased as written because the answer is a plain ``JsonResponse``
    (the preview pattern of #1327) which the JSON:API renderer does not
    touch. Keeping the projection in one function is what stops view and
    schema from naming different shapes.
    """
    target_kind = target_id = target_name = role_slug = organization = None
    if kind == "user":
        target_kind, target_id, target_name = "user", row.user.pk, str(row.user)
    else:
        group = row.group
        role = _role_of_group(group)
        organization_of_group = _organization_of_group(group)
        if role is not None:
            target_kind = "role"
            target_id, role_slug = role.pk, role.role_definition.slug
            organization = str(role.organization) if role.organization else None
            # the readable name says whose role it is, not just what it is
            target_name = str(role)
        elif organization_of_group is not None:
            # the legacy shape of a grant onto the whole organization
            target_kind, organization = "organization", str(
                organization_of_group)
            target_id, target_name = (organization_of_group.pk,
                                      str(organization_of_group))
        else:
            target_kind, target_id, target_name = ("group", group.pk,
                                                   str(group))
    return {
        "id": f"{kind}-{row.pk}",
        "targetKind": target_kind,
        "targetId": target_id,
        "targetName": target_name,
        "role": role_slug,
        "organization": organization,
        "action": action_for(row.permission.codename),
        "permission": row.permission.codename,
        "grantedBy": str(row.granted_by) if row.granted_by_id else None,
        "createdAt": row.created_at.isoformat() if row.created_at else None,
    }


class ShareRequestSerializer(serializers.Serializer):
    """The payload of a share POST: one target and a subset of actions.

    Exactly one of the two shapes names the target: a ``user`` id, or an
    ``organization`` id plus the ``role`` slug whose role group within that
    organization receives the grants. The service is context, not payload:
    it is the object the route already selected.
    """

    user = serializers.IntegerField(required=False, write_only=True)
    organization = serializers.IntegerField(required=False, write_only=True)
    role = serializers.CharField(required=False, write_only=True)
    actions = serializers.ListField(
        child=serializers.CharField(), allow_empty=False)

    def validate(self, attrs):
        from registry.models.shares import shareable_actions

        service = self.context["service"]
        has_user = "user" in attrs
        has_org = "organization" in attrs or "role" in attrs
        if has_user and has_org:
            raise serializers.ValidationError({
                "non_field_errors": _(
                    "A share names one target: a user, or an organization "
                    "with a role.")})
        if not has_user and not has_org:
            raise serializers.ValidationError({
                "non_field_errors": _(
                    "A share names a target: a user, or an organization "
                    "with a role.")})
        if "organization" in attrs and "role" not in attrs:
            raise serializers.ValidationError({
                "role": _(
                    "Sharing with an organization shares with one of its "
                    "roles; name the role definition slug.")})
        if "user" in attrs and not User.objects.filter(
                pk=attrs["user"]).exists():
            raise serializers.ValidationError({
                "user": _("No user with this id.")})
        if "organization" in attrs:
            from accounts.models.groups import Organization

            if not Organization.objects.filter(
                    pk=attrs["organization"]).exists():
                raise serializers.ValidationError({
                    "organization": _("No organization with this id.")})
            role = Role.objects.for_org(
                attrs["organization"]).with_definition(attrs["role"]).first()
            if role is None:
                raise serializers.ValidationError({
                    "role": _(
                        "The organization has no active role of this "
                        "definition.")})
            attrs["role_group"] = role.group
        elif "user" in attrs:
            attrs["user_instance"] = User.objects.get(pk=attrs["user"])
        unknown = [action for action in attrs["actions"]
                   if action not in shareable_actions(service)]
        if unknown:
            raise serializers.ValidationError({
                "actions": _(
                    "Actions this service cannot share: %(actions)s. "
                    "Shareable: %(shareable)s.") % {
                        "actions": ", ".join(unknown),
                        "shareable": ", ".join(shareable_actions(service))}})
        return attrs

    def resolve_target(self):
        """The ``Group`` (role group) or ``User`` the payload names."""
        validated = self.validated_data
        if "role_group" in validated:
            return validated["role_group"]
        return validated["user_instance"]
