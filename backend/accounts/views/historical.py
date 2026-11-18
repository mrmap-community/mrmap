"""The read-only api over the audit trail of the role system (#741).

Routes (registered in ``accounts/urls.py``):

* ``/historical-roledefinitions`` - what the catalogue meant at a moment,
  including who changed its permission set;
* ``/historical-roles`` - who created, retired and deleted a role;
* ``/historical-memberships`` - who granted a role to whom, and who took it
  back - including the revocations the expiry sweep of #741 wrote.

The read plan, the verbs and the ordering come from
:class:`extras.viewsets.HistoricalViewSetMixin`, which the registry's
changelogs use too. What differs is who may read: an audit row discloses
exactly what its live row discloses, so each viewset guards its history with
the very permission class of that resource, and the membership history - whose
payload *is* who-holds-what - is narrowed by the same
:func:`accounts.permissions.visible_memberships` the flat membership
collection applies. An answer about the past may not be wider than the answer
about the present.
"""
from accounts.models.roles import Role, RoleDefinition, RoleMembership
from accounts.permissions import (IsAuthenticatedReadOnlyOrPlatform,
                                  RoleAccessPermission,
                                  RoleMembershipAccessPermission,
                                  visible_memberships)
from accounts.serializers.historical import (RoleDefinitionHistorySerializer,
                                             RoleHistorySerializer,
                                             RoleMembershipHistorySerializer)
from extras.viewsets import HistoricalViewSetMixin
from rest_framework_json_api.views import ModelViewSet

#: the questions every changelog screen asks, named once: which object's
#: changelog ("show me the history of this role"), which kind of event, and
#: since when
HISTORY_FILTERS = {
    "history_relation": ["exact", "in"],
    "history_type": ["exact", "in"],
    "history_date": ["gte", "lte"],
    "history_user": ["exact"],
}


class RoleDefinitionHistoricalViewSet(HistoricalViewSetMixin, ModelViewSet):
    """The changelog of the catalogue, readable by every account.

    Reading what a role *means* is what the member picker needs from any
    account (#736), so its history is read under the same rule; writing one
    was never an option on a changelog.
    """

    queryset = RoleDefinition.change_log.all()
    serializer_class = RoleDefinitionHistorySerializer
    permission_classes = [IsAuthenticatedReadOnlyOrPlatform]
    filterset_fields = HISTORY_FILTERS


class RoleHistoricalViewSet(HistoricalViewSetMixin, ModelViewSet):
    """The changelog of the roles.

    A ``Role`` row names a definition and an organization and discloses no
    membership, so reading it - and its past - is open to every authenticated
    account, like the resource itself.
    """

    queryset = Role.change_log.all()
    serializer_class = RoleHistorySerializer
    permission_classes = [RoleAccessPermission]
    filterset_fields = HISTORY_FILTERS


class RoleMembershipHistoricalViewSet(HistoricalViewSetMixin, ModelViewSet):
    """The changelog of the grants, narrowed to the rows the caller may see.

    The audit trail of a membership answers who granted what to whom, so it is
    the same disclosure as the membership row itself and no less: the list
    carries the visible rows of :func:`visible_memberships` - a platform holder
    sees everything, an organization administrator their organizations, and
    everybody their own grants - and nothing else. Because a deleted row is
    exactly what an audit is asked about, the filter runs over
    ``history_relation``: the membership the audit row reports on.
    """

    queryset = RoleMembership.change_log.all()
    serializer_class = RoleMembershipHistorySerializer
    permission_classes = [RoleMembershipAccessPermission]
    filterset_fields = HISTORY_FILTERS

    def get_queryset(self):
        queryset = super().get_queryset()
        visible = visible_memberships(
            self.request.user, RoleMembership.objects.all())
        return queryset.filter(history_relation__in=visible)
