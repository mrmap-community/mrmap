from accounts.models.roles import Role
from accounts.models.users import User
from accounts.serializers.groups import GroupSerializer
from accounts.serializers.roles import RoleSerializer
from django.contrib.auth.models import Group
from django.utils.translation import gettext_lazy as _
from extras.serializers import (StringRepresentationSerializer,
                                SystemInfoSerializerMixin)
from rest_framework.relations import HyperlinkedIdentityField, PrimaryKeyRelatedField
from rest_framework_json_api.relations import (ResourceRelatedField,
                                               SerializerMethodResourceRelatedField)
from rest_framework_json_api.serializers import (ModelSerializer, Serializer)


class UserSerializer(
        StringRepresentationSerializer,
        SystemInfoSerializerMixin,
        ModelSerializer):

    url = HyperlinkedIdentityField(
        view_name='accounts:user-detail',
    )

    groups = ResourceRelatedField(
        label=_("groups"),
        help_text=_("groups where this user is member of"),
        many=True,
        related_link_view_name='accounts:user-groups-list',
        related_link_url_kwarg='parent_lookup_user',
        queryset=Group.objects
    )

    # the roles this user holds (#736): who-am-i answers them, so a client
    # learns its own authority from one request, and the nested
    # ``/users/{id}/roles`` route is the related link of this field for
    # every other user
    roles = SerializerMethodResourceRelatedField(
        label=_("roles"),
        help_text=_("the roles this user holds"),
        model=Role,
        method_name="get_roles",
        many=True,
        read_only=True,
        related_link_view_name='accounts:user-roles-list',
        related_link_url_kwarg='parent_lookup_memberships__user',
    )

    related_serializers = {
        "groups": GroupSerializer,
        "roles": RoleSerializer,
    }

    class Meta:
        resource_name = 'User'
        model = User
        exclude = ("password", )

    def get_roles(self, user):
        return Role.objects.filter(memberships__user=user).distinct()


class OrganizationMemberAddSerializer(Serializer):
    """The payload of ``POST /organizations/{id}/members``.

    Adding a person to an organization is a link between two existing
    users - there is no row of its own to create - so the request document
    is not a full resource but its resource identifier: the ``id`` member
    names the user to add. The answer is that user as the members answer
    answers them, with their roles in this organization.
    """

    #: after the JSON:API parser has formed the document up, the resource
    #: identifier's ``id`` is a plain member - the user's pk
    id = PrimaryKeyRelatedField(
        label=_("user"),
        help_text=_("the id of the user to add to the organization"),
        queryset=User.objects.all(),
    )

    def validate(self, attrs):
        attrs = super().validate(attrs)
        if "id" in attrs:
            attrs["user"] = attrs.pop("id")
        return attrs


class OrganizationMemberSerializer(UserSerializer):
    """A user as the member of one organization: roles scoped to it.

    ``/organizations/{id}/members`` answers the users with their roles *in
    that organization*: a member of two organizations is listed with the
    role they hold where they are being listed, and their memberships of
    any other organization stay invisible (#727's Q3: membership in one
    organization says nothing about another). The view which uses this
    serializer remembers the organization on itself as ``organization``.
    """

    def get_roles(self, user):
        organization = getattr(self.context.get("view"), "organization",
                               None)
        roles = super().get_roles(user)
        if organization is not None:
            roles = roles.filter(organization=organization)
        return roles


class UserCreateSerializer(SystemInfoSerializerMixin, ModelSerializer):

    url = HyperlinkedIdentityField(
        view_name='accounts:user-detail',
    )

    groups = ResourceRelatedField(
        label=_("groups"),
        help_text=_("groups where this user shall be member of"),
        queryset=Group.objects.all(),
        many=True,
        related_link_view_name='accounts:user-groups-list',
        related_link_url_kwarg='parent_lookup_user',)

    related_serializers = {
        "groups": GroupSerializer
    }

    class Meta:
        resource_name = 'User'
        model = User
        fields = ("username", "password", "url", "groups")

    def save(self, **kwargs):
        user = super().save(**kwargs)
        # set the correct password
        user.set_password(self.validated_data['password'])
        return user
