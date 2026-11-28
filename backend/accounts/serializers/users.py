from accounts.models.roles import Role
from accounts.models.users import User
from accounts.permissions import (account_fields, may_see_groups_of,
                                  may_see_roles_of)
from accounts.serializers.groups import GroupSerializer
from accounts.serializers.roles import RoleSerializer
from django.contrib.auth import password_validation
from django.contrib.auth.models import Group
from django.utils.translation import gettext_lazy as _
from extras.serializers import (StringRepresentationSerializer,
                                SystemInfoSerializerMixin)
from rest_framework.relations import (HyperlinkedIdentityField,
                                      PrimaryKeyRelatedField)
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

    # which groups a person is in states which roles they hold, so the
    # relation is answered with the same authorities as the roles below and
    # not with the reach of the session (#1807)
    groups = SerializerMethodResourceRelatedField(
        label=_("groups"),
        help_text=_("groups where this user is member of"),
        model=Group,
        method_name="get_groups",
        many=True,
        read_only=True,
        related_link_view_name='accounts:user-groups-list',
        related_link_url_kwarg='parent_lookup_user',
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

    def _request(self):
        return self.context.get("request")

    def get_groups(self, user):
        request = self._request()
        if request is not None and not may_see_groups_of(request.user, user):
            return Group.objects.none()
        return user.groups.all()

    def get_roles(self, user):
        # which roles a person holds is the statement of #727's Q3, which
        # ``/users/{id}/roles`` answers with these very authorities (#1807)
        request = self._request()
        if request is not None and not may_see_roles_of(request.user, user):
            return Role.objects.none()
        return Role.objects.filter(memberships__user=user).distinct()

    #: the keys which survive the field filter because their own answer is
    #: guarded: ``url`` and ``id`` are the resource identifier a relation needs,
    #: ``groups`` and ``roles`` are answered by :meth:`get_groups` and
    #: :meth:`get_roles`. Everything else - above all ``userPermissions``, the
    #: direct grants #741 moved to ``/api/accounts/effective-permissions`` -
    #: belongs to the field surface below.
    RELATIONSHIP_FIELDS = ("url", "id", "groups", "roles")

    def to_representation(self, instance):
        """Answer of a person only what the caller may read (#1807).

        The guard of the viewset decides *whether* a row is answered; this is
        the half which decides *what of it*, so the address of a person, the
        fact that they are a superuser and the time of their last login cannot
        travel with a session: they are answered to the reader named by
        :func:`accounts.permissions.account_fields` and to nobody else. The
        guard alone would be enough for the two routes of the users endpoint -
        this is what holds the same line on the answers of every *other*
        resource which embeds a person: ``createdBy`` and ``lastModifiedBy``
        of #738, ``historyUser`` of the changelogs of #741, the members of an
        organization.
        """
        request = self._request()
        if request is None:
            # no caller to judge: the answer is produced by a process which is
            # trusted to be able to read the model in the first place - a
            # management command, a mail template, the schema run. The guard
            # protects an *answer to a request*, and it fails closed for the
            # anonymous user of one, not by accident for a caller-less call
            return super().to_representation(instance)
        answered = super().to_representation(instance)
        allowed = account_fields(
            getattr(request, "user", None), instance, request)
        if allowed is None:
            return answered
        # the keys of this answer are still the names of python; the renderer
        # is what turns them into the names of the api
        allowed = set(allowed) | set(self.RELATIONSHIP_FIELDS)
        return {name: value for name, value in answered.items()
                if name in allowed}


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

    def validate_password(self, password):
        # ``create`` hands this value to ``set_password`` and the save after
        # it runs Django's AUTH_PASSWORD_VALIDATORS over the stored raw
        # value; a password which breaks that policy is refused here, with
        # the 400 of a rejected field, and never reaches the write (#1451)
        password_validation.validate_password(password)
        return password

    def create(self, validated_data):
        """Hashes the password before the row is ever written (#1451).

        The plain ``ModelSerializer.save`` INSERTs the raw password as a
        normal model value; hashing after that save only ever fixed the
        in-memory instance, so the database kept the credential in
        plaintext and ``check_password`` never matched - an API-created
        user could never log in. Neither may happen: pop the password,
        build the instance, hash it onto the one save.
        """
        password = validated_data.pop('password')
        # the m2m of this payload has no column to create the row with;
        # ModelSerializer.create would have applied it after the save too
        groups = validated_data.pop('groups', [])
        user = User(**validated_data)
        user.set_password(password)
        user.save()
        if groups:
            user.groups.set(groups)
        return user
