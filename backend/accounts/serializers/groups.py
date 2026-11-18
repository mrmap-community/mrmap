from accounts.models.groups import Organization
from django.contrib.auth.models import Group
from extras.serializers import (StringRepresentationSerializer,
                                SystemInfoSerializerMixin)
from rest_framework.relations import HyperlinkedIdentityField
from rest_framework_json_api.serializers import ModelSerializer
from rest_framework_json_api.relations import ResourceRelatedField
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
    # retirement of the plain groups is #741. A read-only relation carries no
    # `queryset` -- DRF refuses both together -- and needs none: the resource
    # type of the answer comes from the relation the `source` names.
    users = ResourceRelatedField(
        source='user_set',
        label=_("users"),
        help_text=_("users who are members of this group"),
        many=True,
        read_only=True,
    )

    class Meta:
        model = Group
        fields = "__all__"


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
