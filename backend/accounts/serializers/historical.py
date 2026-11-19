"""The api shape of the audit trail of the role system (#741).

A changelog answers the same questions whatever model it trails - who, when,
what changed - so the row serializer is the shared ``HistorySerializerMixin``
of ``extras.serializers``; this module only names the model and the relations
each of the three role tables can include.

None of them declares ``history_relation`` as an *included* serializer, unlike
the registry's changelogs: an audit row of a role which was retired by #741
points at a ``Role`` row which no longer exists, and an include would ask that
row out of the database for every screen which shows the feed. The relation is
still answered as a relationship id, and DRF skips the field for a row whose
object is gone - which is what an audit of a deleted object has to look like.
"""
from accounts.models.roles import Role, RoleDefinition, RoleMembership
from accounts.serializers.users import UserSerializer
from extras.serializers import HistorySerializerMixin

#: what stays out of an audit answer: ``history_id`` is the primary key of the
#: row, which the resource already answers as ``id``. ``delta_size`` is not
#: listed as the registry's changelog serializers do - that column belongs to
#: ``DeltaSizeHistoricalModel``, whose per-day statistics the registry
#: aggregates; the role histories deliberately do not use that base, because
#: the permission set of a definition is tracked as a many-to-many and the
#: count of changed columns cannot see it (``registry.querys.historical.
#: with_delta_size`` refuses exactly that combination).
EXCLUDE = ("history_id",)


class RoleDefinitionHistorySerializer(HistorySerializerMixin):
    """One row of the audit trail of the role catalogue."""

    included_serializers = {
        "history_user": UserSerializer,
    }

    class Meta:
        model = RoleDefinition.change_log.model
        exclude = EXCLUDE


class RoleHistorySerializer(HistorySerializerMixin):
    """One row of the audit trail of one role."""

    included_serializers = {
        "history_user": UserSerializer,
    }

    class Meta:
        model = Role.change_log.model
        exclude = EXCLUDE


class RoleMembershipHistorySerializer(HistorySerializerMixin):
    """One row of the audit trail of one grant of a role to a person."""

    included_serializers = {
        "history_user": UserSerializer,
    }

    class Meta:
        model = RoleMembership.change_log.model
        exclude = EXCLUDE
