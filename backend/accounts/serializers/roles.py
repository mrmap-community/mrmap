"""Serializers of the role API of #736.

The guard rails which are not authority checks live here, next to the
permission classes of :mod:`accounts.permissions`: who may assign what is
answered there, what a legal assignment *is* is answered here - an
ORGANIZATION role only for a member of that organization, retired roles to
nobody, ``is_assignable=False`` and PLATFORM roles only through a platform
act. A refused authority answers 403 with a JSON:API error, a payload which
names an impossible combination answers 400 naming the field a client can
fix.
"""
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import CharField, Q, Value
from django.db.models.functions import Coalesce, Concat
from django.utils.translation import gettext_lazy as _
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.relations import HyperlinkedIdentityField
from rest_framework.validators import UniqueTogetherValidator, qs_filter
from rest_framework_json_api.relations import ResourceRelatedField
from rest_framework_json_api.serializers import (ModelSerializer,
                                                 SerializerMethodField)

from accounts.models.groups import Organization
from accounts.models.roles import (PLATFORM_GROUP_PREFIX, Role,
                                   RoleDefinition, RoleMembership, RoleScope,
                                   free_role_group_name)
from accounts.permissions import (may_administer_organization,
                                  may_grant_platform_role)
from extras.serializers import (CheckConstraintSerializerMixin,
                                StringRepresentationSerializer,
                                SystemInfoSerializerMixin)

User = get_user_model()


def is_organization_member(user, organization) -> bool:
    """Whether ``user`` is a member of ``organization``.

    An ``Organization`` *is* a ``Group`` (``accounts/models/groups.py``), so
    "member of the organization" is exactly membership of that group - the
    same test the grants of #732 resolve through.
    """
    return organization is not None and user.groups.filter(
        pk=organization.pk).exists()


def as_serializer_error(error: DjangoValidationError) -> ValidationError:
    """Django's model ``ValidationError`` in DRF's shape.

    A model's ``clean()`` is the authority for what a legal row is, and a
    serializer must answer its message as a field error, not as the 500 an
    unhandled exception would be.
    """
    if isinstance(error, DjangoValidationError):
        return ValidationError(error.message_dict if hasattr(
            error, "message_dict") else {"non_field_errors": error.messages})
    return error


class UniqueActiveRoleValidator(UniqueTogetherValidator):
    """The one active role per definition and organization, asked the way
    #736's create payload is written.

    DRF derives this validator from the model's partial ``UniqueConstraint``
    itself and evaluates the ``is_active`` condition and ``nulls_distinct``
    correctly, but ``enforce_required_fields`` forces every field of the
    constraint into the payload - including the nullable ``organization``,
    which a payload creating a PLATFORM role legitimately leaves out; what
    an omitted organization *means* is ``Role.clean``'s rule, which
    :meth:`RoleCreateSerializer.validate` already asks before any write. A
    field declared ``allow_null`` is therefore optional here, and the unique
    answer is still enforced over the rows which do carry the pair.

    Declared in ``Meta.validators``, which is also what keeps DRF from
    injecting its own, stricter instance of the validator next to this one.
    """

    def enforce_required_fields(self, attrs, serializer):
        if serializer.instance is not None:
            return
        missing_items = {
            field_name: self.missing_message
            for field_name in (*self.fields, *self.condition_fields)
            if serializer.fields[field_name].source not in attrs
            and not serializer.fields[field_name].allow_null}
        if missing_items:
            raise ValidationError(missing_items, code="required")

    def filter_queryset(self, attrs, queryset, serializer):
        # the base reads ``attrs[source]`` for every field of the constraint,
        # which this validator lets stay absent; absent means the same as
        # null for the nullable side, so the duplicate check asks for the
        # NULL row exactly as it will be written
        sources = [
            serializer.fields[field_name].source for field_name in self.fields]
        if serializer.instance is not None:
            for source in sources:
                if source not in attrs:
                    attrs[source] = getattr(serializer.instance, source)
        filter_kwargs = {source: attrs.get(source) for source in sources}
        return qs_filter(queryset, **filter_kwargs)


#: mirrors ``Role.Meta.constraints``' one partial unique constraint for the
#: serializers; the arguments repeat the model's, which is the pattern DRF's
#: own derivation uses (``ModelSerializer.get_unique_together_constraints``)
ACTIVE_ROLE_VALIDATOR = UniqueActiveRoleValidator(
    queryset=Role.objects.all(),
    fields=("role_definition", "organization"),
    condition_fields=("is_active",),
    condition=Q(is_active=True),
    nulls_distinct=False,
)


class RoleDefinitionSerializer(
        StringRepresentationSerializer,
        SystemInfoSerializerMixin,
        ModelSerializer):
    """The catalogue of what a role means (#731), readable by everyone.

    A builtin definition is read-only in everything but ``label`` and
    ``description``: the slug is what #732's migrations and #736's API refer
    to, the scope is what the guard rails branch on, and the permission set
    is what the facade of #734 applies - an operator adjusting a builtin
    role adjusts how it reads, not what it is.
    """

    #: what a caller may not change on a builtin definition; the two editable
    #: fields are ``label`` and ``description``, see the class docstring
    BUILTIN_LOCKED_FIELDS = ("slug", "scope", "is_default", "is_assignable",
                             "permissions")

    url = HyperlinkedIdentityField(
        view_name='accounts:roledefinition-detail',
    )
    permissions = ResourceRelatedField(
        label=_("permissions"),
        help_text=_(
            "the global permissions which make up the role; object grants "
            "stay the work of django-guardian"),
        many=True,
        required=False,
        queryset=Permission.objects.all(),
    )

    class Meta:
        model = RoleDefinition
        fields = "__all__"

    def get_fields(self):
        fields = super().get_fields()
        if getattr(self.instance, "is_builtin", False):
            for name in self.BUILTIN_LOCKED_FIELDS:
                fields[name].read_only = True
        return fields


class RoleDefinitionListSerializer(RoleDefinitionSerializer):
    """List shape of the catalogue: identical fields, kept as its own class
    because the detail serializer inherits from the list serializer wherever
    a list exists (``backend/AGENTS.md``) - here both answers are the whole
    row, so the base carries it."""


class RoleSerializer(
        StringRepresentationSerializer,
        SystemInfoSerializerMixin,
        ModelSerializer):
    """One role of one organization - and the group it manages.

    This is the read and PATCH shape: the identity fields (``role_definition``,
    ``organization``) and the ``group`` are read-only here, the only writable
    field is ``is_active``. Writing the identity is the create serializer's
    job, because the group of a new role is written by the API under the name
    the bootstrap of #732 uses (``free_role_group_name``) - a caller which
    could name or hand in a group could attach a role to a group which
    already carries grants.
    """

    url = HyperlinkedIdentityField(
        view_name='accounts:role-detail',
    )
    role_definition = ResourceRelatedField(
        label=_("role definition"),
        help_text=_("what this role means, from the catalogue of #731"),
        read_only=True,
        model=RoleDefinition,
    )
    organization = ResourceRelatedField(
        label=_("organization"),
        help_text=_(
            "the organization this role belongs to; empty only for a role "
            "of PLATFORM scope"),
        read_only=True,
        model=Organization,
    )
    group = ResourceRelatedField(
        label=_("group"),
        help_text=_(
            "the group whose members hold this role; written by the API, "
            "never taken from the request"),
        read_only=True,
        model=Group,
    )
    created_by = ResourceRelatedField(
        label=_("created by"),
        help_text=_("who created this role"),
        read_only=True,
        model=User,
    )
    member_count = SerializerMethodField(
        label=_("member count"),
        help_text=_("how many users currently hold this role"),
    )

    related_serializers = {"role_definition": RoleDefinitionSerializer}

    class Meta:
        model = Role
        fields = "__all__"
        extra_kwargs = {
            "created_at": {"read_only": True},
        }
        validators = [ACTIVE_ROLE_VALIDATOR]

    def get_member_count(self, role) -> int:
        # the viewset's prefetch of "memberships" keeps this off the database
        return role.memberships.count()


class RoleCreateSerializer(CheckConstraintSerializerMixin, RoleSerializer):
    """The create shape: identity fields writable, authority checked.

    Creating the role of a definition for an organization extends that
    organization's catalogue beyond what its bootstrap wrote; over the API
    that is decided by the organization's own administrator - or by a
    platform holder for a PLATFORM role (``RoleScope``: assigning a platform
    role is itself a platform act). The partial unique constraint "one
    active role per definition and organization" is answered here as a 400
    through :class:`extras.serializers.CheckConstraintSerializerMixin`, so
    a duplicate create cannot reach the database and surface as a 500.
    """

    role_definition = ResourceRelatedField(
        label=_("role definition"),
        help_text=_("what this role means, from the catalogue of #731"),
        queryset=RoleDefinition.objects.all(),
    )
    organization = ResourceRelatedField(
        label=_("organization"),
        help_text=_(
            "the organization this role belongs to; empty only for a role "
            "of PLATFORM scope"),
        required=False,
        allow_null=True,
        queryset=Organization.objects.all(),
    )

    class Meta:
        model = Role
        fields = "__all__"
        extra_kwargs = {
            # the model's default, stated as the serializer's so the payload
            # may omit it and the condition of ACTIVE_ROLE_VALIDATOR still
            # sees which state is being created
            "is_active": {"required": False, "default": True},
            "created_at": {"read_only": True},
        }
        validators = [ACTIVE_ROLE_VALIDATOR]

    def run_validators(self, value):
        """The order #736 asks for: the authority to write such a row is
        answered 403 *before* the validators may answer 400 about the
        payload - an outsider is not told what would have been a legal
        create. ``Meta.validators`` run inside ``super().run_validators``,
        so the question is asked here, at the same point in the pipeline.

        An ORG-scoped create is only judged when the payload names an
        organization; which omission is which error is ``Role.clean``'s
        rule, kept in :meth:`validate` for the probe.
        """
        definition = value.get("role_definition")
        if definition is not None:
            actor = self.context["request"].user
            if definition.scope == RoleScope.PLATFORM:
                if not may_grant_platform_role(actor):
                    raise PermissionDenied(_(
                        "Assigning a role of PLATFORM scope is a platform "
                        "act which needs the permission to grant platform "
                        "roles."))
            elif ("organization" in value
                    and not may_administer_organization(
                        actor, value["organization"])):
                raise PermissionDenied(_(
                    "Only an administrator of the organization can create "
                    "the role of a definition for it."))
        super().run_validators(value)

    def validate(self, attrs):
        attrs = super().validate(attrs)
        definition = attrs.get("role_definition")
        organization = attrs.get("organization")
        if definition is None:
            return attrs
        # "organization is null iff the scope is PLATFORM" is Role.clean's
        # rule; asked of the definition the payload names, before any write
        probe = Role(role_definition=definition, organization=organization)
        try:
            probe.clean()
        except DjangoValidationError as error:
            raise as_serializer_error(error)
        return attrs

    def create(self, validated_data):
        definition = validated_data["role_definition"]
        organization = validated_data.get("organization")
        validated_data["created_by"] = self.context["request"].user
        validated_data["group"] = Group.objects.create(
            name=free_role_group_name(organization, definition.slug))
        return super().create(validated_data)


class RoleMembershipSerializer(
        StringRepresentationSerializer,
        SystemInfoSerializerMixin,
        ModelSerializer):
    """A person holds a role - the decision, not just the grant.

    The validation order is the one #736 asks for: first whether the caller
    may assign this role at all (403 - an outsider is not told what would
    have been valid), then whether the payload describes a legal assignment
    (400 naming the field). ``granted_by`` is the caller, never the payload:
    #741 wants every membership explainable down to a decision, and a
    decision attributed to somebody else is worse than none.
    """

    url = HyperlinkedIdentityField(
        view_name='accounts:rolemembership-detail',
    )
    role = ResourceRelatedField(
        label=_("role"),
        help_text=_("the role which is held"),
        queryset=Role.objects.all(),
    )
    user = ResourceRelatedField(
        label=_("user"),
        help_text=_("the user who holds the role"),
        queryset=User.objects.all(),
    )
    granted_by = ResourceRelatedField(
        label=_("granted by"),
        help_text=_("who added the user to the role"),
        read_only=True,
        model=User,
    )

    related_serializers = {"role": RoleSerializer}

    class Meta:
        model = RoleMembership
        fields = "__all__"
        extra_kwargs = {
            "granted_at": {"read_only": True},
        }

    def validate(self, attrs):
        attrs = super().validate(attrs)
        role = attrs.get("role")
        user = attrs.get("user")
        if role is None or user is None:
            # the create always carries both; a payload which cannot be
            # judged yet is left to the remaining validators
            return attrs
        actor = self.context["request"].user

        # the parent of a nested create and the role of the payload must be
        # one and the same role: /roles/{id}/memberships must not be used to
        # write a membership of a different role
        parent_role_id = self.context["view"].kwargs.get(
            "parent_lookup_role")
        if parent_role_id is not None and role.pk != int(parent_role_id):
            raise ValidationError({
                "role": _(
                    "The role of the membership is fixed by the role "
                    "collection it is posted to.")})

        # 403: the authority to assign this role at all
        definition = role.role_definition
        if (definition.scope == RoleScope.PLATFORM
                or not definition.is_assignable):
            if not may_grant_platform_role(actor):
                raise PermissionDenied(
                    _("%(role)s can only be assigned with the permission to "
                      "grant platform roles.") % {"role": str(role)})
        elif not may_administer_organization(actor, role.organization):
            raise PermissionDenied(
                _("Only an administrator of %(organization)s can assign its "
                  "roles.") % {"organization": str(role.organization)})

        # 400: what the model forbids - a retired role takes no member
        try:
            RoleMembership(role=role, user=user).clean()
        except DjangoValidationError as error:
            raise as_serializer_error(error)

        # 400: an ORGANIZATION role only for a member of that organization
        if role.organization_id is not None and not is_organization_member(
                user, role.organization):
            raise ValidationError({
                "user": _(
                    "%(user)s is not a member of %(organization)s; an "
                    "organization role can only be assigned to a member of "
                    "its own organization.") % {
                        "user": str(user),
                        "organization": str(role.organization)}})
        return attrs

    def create(self, validated_data):
        validated_data["granted_by"] = self.context["request"].user
        return super().create(validated_data)


def roles_queryset():
    """The base queryset every role answer of the API starts from.

    The annotation computes the display string of ``Role.__str__`` in the
    database, so ``sort=stringRepresentation`` orders exactly the rows the
    serializer answers (the pattern of #1035).
    """
    return Role.objects.select_related(
        "role_definition", "organization", "group").annotate(
            string_representation=Concat(
                Coalesce("organization__name",
                         Value(PLATFORM_GROUP_PREFIX)),
                Value(": "),
                "role_definition__slug",
                output_field=CharField()))
