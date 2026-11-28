from accounts.models.groups import Organization
from accounts.permissions import (may_read_members_of,
                                  member_readable_group_ids)
from django.contrib.auth.models import Group
from extras.serializers import (StringRepresentationSerializer,
                                SystemInfoSerializerMixin)
from rest_framework.relations import HyperlinkedIdentityField
from rest_framework_json_api.serializers import ModelSerializer
from rest_framework_json_api.relations import \
    SerializerMethodResourceRelatedField
from django.utils.translation import gettext_lazy as _


class GroupSerializer(
        StringRepresentationSerializer,
        SystemInfoSerializerMixin,
        ModelSerializer):

    url = HyperlinkedIdentityField(
        view_name='accounts:group-detail',
    )
    # readable, never writable: who belongs to a group is written by the
    # members endpoint of #736 (`POST /organizations/{id}/members`), which
    # decides the organization the group belongs to. A writable relation here
    # handed the permissions granted to the group out to whoever could reach
    # the endpoint (#1448); the admin UI of #737 uses that endpoint and the
    # retirement of the plain groups is #741.
    #
    # Readable is not the same as answered to anybody: the members of a role
    # group are the membership rows of that role, the payload which #727's Q3
    # and ``RoleMembershipAccessPermission`` put behind the organization - and
    # which this route used to answer to every session (#1807). The answer is
    # therefore the one those two answer, and the row itself - the name a
    # picker renders - stays reachable.
    users = SerializerMethodResourceRelatedField(
        label=_("users"),
        help_text=_("users who are members of this group"),
        model=Group.user_set.field.related_model,
        method_name="get_users",
        many=True,
        read_only=True,
    )

    class Meta:
        model = Group
        fields = "__all__"

    def get_users(self, group):
        request = self.context.get("request")
        if request is None:
            return group.user_set.all()
        # the scope of a whole answer is asked once per request: the renderer
        # builds a serializer per included row, and one statement per row of a
        # page is the read plan of #1448 giving that answer back
        readable_ids = member_readable_group_ids(request.user, request)
        if may_read_members_of(request.user, group, readable_ids):
            return group.user_set.all()
        return group.user_set.none()


class OrganizationSerializer(
        StringRepresentationSerializer,
        SystemInfoSerializerMixin,
        ModelSerializer):

    url = HyperlinkedIdentityField(
        view_name='accounts:organization-detail',
    )

    class Meta:
        model = Organization
        fields = "__all__"
