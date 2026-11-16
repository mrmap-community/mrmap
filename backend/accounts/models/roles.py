from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.db.models.deletion import ProtectedError
from django.db.models.query import QuerySet
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

#: the slug of the builtin definition which administers one organization; the
#: catalogue of #731 seeds it and the grants of a new organization are written
#: onto the role of this definition (see ``accounts.signals``)
ORGANIZATION_ADMIN_ROLE = "organization_admin"

#: the prefix of the group name of a role without an organization; every other
#: role group is named after its organization, see ``role_group_name``
PLATFORM_GROUP_PREFIX = "platform"


def role_group_name(organization, slug, marker=""):
    """The name of the ``auth.Group`` which a role manages.

    The name is **for reading**: it shows up in the Django admin, where a
    ``Group`` has nothing else that says what it is for. Nothing may look a
    role up by it - that indirection is exactly the bug #732 removes, because
    a rename of the organization renames the key. Ask
    ``Role.objects.for_org(organization).with_definition(slug)`` instead.

    The organization name is cut off, not the suffix, so that a name which
    reaches the ``auth_group`` limit still says what the role *is* and the roles
    of one organization stay distinct. ``marker`` is what
    ``free_role_group_name`` numbers a name with when an organization so long
    that its truncation collides with another one's already holds it.

    Args:
        organization: the organization of the role, None for a platform role
        slug (str): the slug of the role definition
        marker (str): a suffix to keep the name unique, empty by default

    Returns:
        str: a group name of at most ``auth_group.name`` characters
    """
    suffix = f": {slug}{marker}"
    prefix = organization.name if organization else PLATFORM_GROUP_PREFIX
    limit = Group._meta.get_field("name").max_length
    return f"{prefix[:limit - len(suffix)]}{suffix}"


def free_role_group_name(organization, slug) -> str:
    """``role_group_name`` answered with a name no group holds yet.

    A truncated organization name is not unique - two organizations which agree
    in their first ~140 characters would both name their groups the same way -
    and ``auth_group.name`` is unique, so writing it raises in the middle of
    creating an organization. The numbering is invisible to any code path: the
    name is decoration, only the role is a key.
    """
    name = role_group_name(organization, slug)
    counter = 1
    while Group.objects.filter(name=name).exists():
        counter += 1
        name = role_group_name(organization, slug, marker=f" ({counter})")
    return name


class RoleScope(models.TextChoices):
    """The level at which a role definition is meant to be assigned (#731).

    An ORGANIZATION role is what a member of one organization gets - what an
    editor of *this* organization may do. A PLATFORM role reaches over all
    organizations; assigning one is itself a platform-level act, which is what
    the ``accounts.grant_platform_role`` permission of this app guards.
    """

    PLATFORM = "PLATFORM", _("Platform")
    ORGANIZATION = "ORGANIZATION", _("Organization")


class RoleDefinition(models.Model):
    """What a role means, as data rather than as Python.

    A role definition is the named, listable set of **global** permissions
    which answers "what may an editor do" without reading code. It describes a
    role; it grants nothing by itself. django-guardian and Django's groups stay
    the enforcement engine (#52 removed a permission model of our own and this
    does not bring it back); issue #732 turns a definition into the managed
    ``Role`` group of an organization.

    The builtin definitions ship with MrMap (the catalogue of #731, seeded by
    migration and kept by ``manage.py sync_role_definitions``). An operator may
    adjust ``label`` and ``description`` of a builtin role, but the row itself
    cannot be deleted: the catalogue names roles which the application, its
    later migrations and its API (#736) refer to by slug.

    ``is_default`` marks the role which membership in an organization grants
    automatically, ``is_assignable`` which roles the member picker offers -
    both are read by #732 and #736 and change nothing before that. Neither
    flag, and no permission set of any role, replaces ``User.is_superuser``:
    the superuser stays the auditable break-glass infrastructure privilege,
    not an organizational role (decision Q6 = A of #727). ``platform_admin``
    is the closest a role may come to it and is deliberately not offered in
    the member picker.
    """

    slug = models.SlugField(
        max_length=100,
        unique=True,
        verbose_name=_("slug"),
        help_text=_(
            "the machine name of the role, such as 'resource_editor'; "
            "code and later issues refer to a role by this name"),
    )
    label = models.CharField(
        max_length=200,
        verbose_name=_("label"),
        help_text=_("the display name of the role"),
    )
    description = models.TextField(
        blank=True,
        default="",
        verbose_name=_("description"),
        help_text=_(
            "what the role is for, for the operator reading the role list"),
    )
    scope = models.CharField(
        max_length=20,
        choices=RoleScope.choices,
        default=RoleScope.ORGANIZATION,
        verbose_name=_("scope"),
        help_text=_(
            "PLATFORM for roles which reach over all organizations, "
            "ORGANIZATION for the roles a member of one organization gets"),
    )
    is_builtin = models.BooleanField(
        default=False,
        editable=False,
        verbose_name=_("is builtin"),
        help_text=_(
            "shipped with MrMap: the row is seeded by migration, kept by "
            "manage.py sync_role_definitions and cannot be deleted"),
    )
    is_default = models.BooleanField(
        default=False,
        verbose_name=_("is default"),
        help_text=_(
            "membership grants this role automatically, once #732 applies "
            "roles to memberships"),
    )
    is_assignable = models.BooleanField(
        default=True,
        verbose_name=_("is assignable"),
        help_text=_(
            "the role is offered in the member picker; platform_admin is "
            "not, because holding it is not an ordinary membership"),
    )
    permissions = models.ManyToManyField(
        to=Permission,
        blank=True,
        related_name="role_definitions",
        verbose_name=_("permissions"),
        help_text=_(
            "the global permissions which make up the role; object grants "
            "stay the work of django-guardian"),
    )

    class Meta:
        ordering = ["slug"]
        verbose_name = _("role definition")
        verbose_name_plural = _("role definitions")
        permissions = [
            ('grant_platform_role', 'Can grant a platform scoped role')]

    def __str__(self):
        return self.label

    def delete(self, *args, **kwargs):
        """A builtin definition is part of the shipped catalogue.

        Deleting it would leave the migrations of #732 and the API of #736
        referring to a slug with no row, and would take its permission set
        with it. An operator edits a builtin role through ``label``,
        ``description`` and the flags; the row stays.
        """
        if self.is_builtin:
            raise ProtectedError(
                f"The builtin role definition '{self.slug}' cannot be "
                f"deleted. Its label and description may be edited.",
                [self])
        return super().delete(*args, **kwargs)


class RoleQuerySet(models.QuerySet):
    """The only way which finds a role without naming its group.

    Until #732 the answer to "who administers this organization" was a name
    built from the name of the organization, so renaming it detached every
    role. Every lookup of a role therefore goes through this queryset: by key,
    by definition slug, never by the string in ``auth_group.name``.
    """

    def active(self) -> QuerySet:
        """The roles which are not waiting for their retirement (#741)."""
        return self.filter(is_active=True)

    def retired(self) -> QuerySet:
        """The role groups which are retired: the work list of #741.

        These are the per-model ``<Org> <model> Admins`` groups a deployment
        already had, which #732 reuses as inactive roles instead of deleting
        them: guardian's rows point at the group, so the group has to outlive
        the bootstrap which created it.
        """
        return self.filter(is_active=False)

    def for_org(self, organization) -> QuerySet:
        """The roles of one organization.

        A platform role belongs to no organization and is never an answer here,
        whatever organization is asked for (#727 decision Q3: membership in one
        organization says nothing about another).
        """
        return self.filter(organization=organization)

    def with_definition(self, slug) -> QuerySet:
        """The role of one definition.

        Active roles only: while the retired groups of #741 are still there,
        the retired duplicates of a definition must not be an answer to "the
        resource editor of this organization"; they are reached through
        ``retired()``.
        """
        return self.active().filter(role_definition__slug=slug)

    def managing(self, model) -> QuerySet:
        """The roles whose definition may change instances of ``model``.

        The question the permission bootstrap asks for a newly registered
        resource: which role of the owning organization is the one which edits
        this kind of thing? The answer is read from the catalogue - the role
        definition which holds ``change_<model>`` - rather than from a group
        named after the model, which is why adding a role-managed model needs
        no new group and no migration for the existing organizations (#727).

        Args:
            model: the model class whose instances the role manages

        Returns:
            QuerySet: the active roles of this queryset's organizations
        """
        return self.active().filter(
            role_definition__permissions__codename=(
                f'change_{model._meta.model_name}'),
            role_definition__permissions__content_type__app_label=(
                model._meta.app_label),
            role_definition__permissions__content_type__model=(
                model._meta.model_name),
        ).distinct()

    def create_for_organization(self, organization, created_by=None) -> list:
        """Create every role of the catalogue for one organization.

        Idempotent: an organization which already holds the role of a
        definition keeps it, so a half-finished bootstrap - or an organization
        created before a definition was added to the catalogue - is completed
        rather than doubled. A new role gets a new group, and only the roles
        which are missing create one: the name of a ``Group`` is unique, so a
        group written before the check would stay behind as an orphan.

        Args:
            organization: the organization to give roles to
            created_by: the user the role instances are credited to, if any

        Returns:
            list: every role of the organization, in the order of the catalogue
        """
        manager = self.model._default_manager
        roles = []
        for definition in RoleDefinition.objects.filter(
                scope=RoleScope.ORGANIZATION):
            role = manager.filter(
                role_definition=definition,
                organization=organization).first()
            if role is None:
                role = manager.create(
                    role_definition=definition,
                    organization=organization,
                    group=Group.objects.create(
                        name=free_role_group_name(organization,
                                                  definition.slug)),
                    created_by=created_by)
            roles.append(role)
        return roles


class Role(models.Model):
    """One role of one organization, which **is** the group that enforces it.

    ``RoleDefinition`` says what a role means; a ``Role`` is that definition
    applied to a concrete organization, and the ``Group`` it manages is what
    Django and django-guardian actually resolve when somebody asks whether a
    user may change a service. Nothing here adds a second place to ask: a
    member of the role is a member of the group, so an object grant of the
    group and a global permission of the group reach the person through the
    mechanisms which already existed before #727.

    The group is named ``"<organization>: <slug>"`` for the person reading the
    Django admin; the name carries no meaning and nothing may look it up
    (#732's ``# FIXME: name max_length is 150 chars``, which an organization
    name near that limit would have hit, is gone with the lookup).

    Two things this deliberately does not do:

    * it does not copy ``RoleDefinition.permissions`` onto the group. The
      permissions of a definition become effective where the one facade of
      #734 decides them; writing them onto every role group here would put the
      *global* ``accounts.change_organization`` of ``organization_admin`` on
      the administrators of every organization, which is the cross-organization
      privilege escalation #727 rules out. The object grants of a new
      organization are the ones its predecessor's bootstrap wrote, and they are
      written in ``accounts.signals``;
    * it does not replace ``User.is_superuser``: the break-glass of decision
      Q6 of #727 stays outside the role system.

    An inactive role is one which is waiting for #741 to retire its group, not
    a role an operator switches off: membership of an inactive role is refused
    in ``RoleMembership.clean()`` so the retired groups cannot gather members
    while they wait.
    """

    role_definition = models.ForeignKey(
        to=RoleDefinition,
        on_delete=models.PROTECT,
        related_name="roles",
        verbose_name=_("role definition"),
        help_text=_(
            "what this role means, from the catalogue of #731"),
    )
    organization = models.ForeignKey(
        to="accounts.Organization",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="roles",
        verbose_name=_("organization"),
        help_text=_(
            "the organization this role belongs to; empty only for a role of "
            "PLATFORM scope, which reaches over all organizations"),
    )
    group = models.OneToOneField(
        to=Group,
        on_delete=models.PROTECT,
        related_name="role",
        verbose_name=_("group"),
        help_text=_(
            "the group whose members hold this role; django-guardian and "
            "Django resolve its permissions, so nothing else enforces a role"),
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name=_("is active"),
        help_text=_(
            "false for a legacy group which is retired by #741; a retired "
            "role grants through its group until it is gone, but takes no new "
            "membership"),
    )
    created_by = models.ForeignKey(
        to=settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_roles",
        verbose_name=_("created by"),
        help_text=_(
            "who created this role; empty when a migration or the bootstrap "
            "of a new organization created it"),
    )
    created_at = models.DateTimeField(
        default=timezone.now,
        editable=False,
        verbose_name=_("created at"),
    )

    objects = RoleQuerySet.as_manager()

    class Meta:
        ordering = ["organization__name", "role_definition__slug"]
        verbose_name = _("role")
        verbose_name_plural = _("roles")
        constraints = [
            # one active role per definition and organization - the role of a
            # definition is asked as a single answer, so a second active row of
            # the same pair would make ``with_definition`` ambiguous. The
            # constraint is partial because #732's migration marks the per-model
            # groups a deployment already had inactive *as roles*, and several
            # retired rows of one definition and organization are exactly the
            # work list #741 deletes; NULL is compared as a value so the one
            # platform role of a definition is unique as well
            models.UniqueConstraint(
                fields=["role_definition", "organization"],
                condition=Q(is_active=True),
                nulls_distinct=False,
                name="unique_active_role_per_definition_and_org",
            ),
        ]

    def __str__(self):
        scope = self.organization or PLATFORM_GROUP_PREFIX
        return f"{scope}: {self.role_definition.slug}"

    def clean(self):
        """"organization is null iff the scope is PLATFORM", as #732 asks.

        A ``CheckConstraint`` cannot answer this: the scope is a column of the
        definition, and a SQL check may only read the table of the constrained
        row. So the rule is enforced where a row is validated - the admin and
        the API of #736 - and not by the database.
        """
        super().clean()
        if self.role_definition_id is None:
            return
        if self.role_definition.scope == RoleScope.PLATFORM:
            if self.organization_id is not None:
                raise ValidationError({
                    "organization": _(
                        "A role of PLATFORM scope belongs to no "
                        "organization; it reaches over all of them.")})
        elif self.organization_id is None:
            raise ValidationError({
                "organization": _(
                    "A role of ORGANIZATION scope needs the organization it "
                    "belongs to.")})

    @property
    def members(self) -> QuerySet:
        """The users who hold this role, through their membership."""
        return get_user_model().objects.filter(
            role_memberships__role=self).distinct()

    def add_member(self, user, granted_by=None, valid_until=None):
        """Give this role to a user, which adds them to the role's group.

        Args:
            user: the user to grant the role to
            granted_by: the user the grant is credited to
            valid_until: when the membership stops being valid, see #741

        Returns:
            RoleMembership: the membership of the user in this role
        """
        return RoleMembership.objects.create(
            role=self, user=user, granted_by=granted_by,
            valid_until=valid_until)

    def remove_member(self, user) -> int:
        """Take this role from a user, revoking what the role granted.

        Deleting the membership takes the user out of the group of the role,
        which is what revokes every object grant the group gave them.

        Args:
            user: the user to remove from the role

        Returns:
            int: the number of memberships which were removed, 0 or 1
        """
        return RoleMembership.objects.filter(role=self, user=user).delete()[0]


class RoleMembershipQuerySet(models.QuerySet):
    """The memberships, deleting one by one so the group follows."""

    def delete(self):
        """Delete the memberships instance by instance.

        ``QuerySet.delete()`` is a single ``DELETE`` and would leave the users
        in the groups of the roles it removes the memberships of - a grant
        which no membership explains. Memberships are few, so the rows are
        deleted through the model, whose ``delete()`` maintains the group.
        """
        removed = 0
        for membership in self:
            membership.delete()
            removed += 1
        return (removed, {})


class RoleMembership(models.Model):
    """A person holds a role, with a record of who decided it.

    Adding a membership adds the user to the group of the role, removing it
    takes them out again: the group is the enforcement, the membership row is
    the person-readable statement of why they are in it, with the grantor
    (#741 asks every answer to be explainable down to a decision).

    ``valid_until`` is stored here and enforced by #741: the periodic task
    which revokes an expired membership is its work, not this issue's, and a
    deployment which has not run it yet keeps granting what an expired
    membership granted. That is stated rather than hidden because the field
    reads as a revocation which has not happened.
    """

    role = models.ForeignKey(
        to=Role,
        on_delete=models.CASCADE,
        related_name="memberships",
        verbose_name=_("role"),
    )
    user = models.ForeignKey(
        to=settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="role_memberships",
        verbose_name=_("user"),
    )
    granted_by = models.ForeignKey(
        to=settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="granted_role_memberships",
        verbose_name=_("granted by"),
        help_text=_(
            "who added the user to the role; empty for a membership a "
            "migration or a bootstrap took over, where no decision is known"),
    )
    granted_at = models.DateTimeField(
        default=timezone.now,
        editable=False,
        verbose_name=_("granted at"),
    )
    valid_until = models.DateTimeField(
        null=True,
        blank=True,
        default=None,
        verbose_name=_("valid until"),
        help_text=_(
            "when the membership stops being valid; revoked by the periodic "
            "task of #741"),
    )

    objects = RoleMembershipQuerySet.as_manager()

    class Meta:
        ordering = ["role", "user"]
        verbose_name = _("role membership")
        verbose_name_plural = _("role memberships")
        constraints = [
            models.UniqueConstraint(
                fields=["role", "user"],
                name="unique_membership_per_role_and_user",
            ),
        ]

    def __str__(self):
        return f"{self.user} @ {self.role}"

    def clean(self):
        """A retired role takes no member.

        The group of a retired role waits for #741 to be deleted; a membership
        of it would look like a decision while it is only the residue of a
        migration.
        """
        super().clean()
        if self.role_id is not None and not self.role.is_active:
            raise ValidationError(_(
                "The role %(role)s is retired and cannot be granted to "
                "anybody.",
                {"role": str(self.role)}))

    def save(self, *args, **kwargs):
        """Keep the group of the role in step with the membership.

        The write is in the model rather than in a receiver on purpose: a
        ``loaddata`` does emit ``post_save`` with ``created=True`` (#864), and a
        loaded membership would add its user to a group as a side effect of
        reading a dump. A deserializer calls ``save_base``, never ``save()``, so
        this path cannot do that.
        """
        super().save(*args, **kwargs)
        self.role.group.user_set.add(self.user)

    def delete(self, *args, **kwargs):
        """Leave the group, which revokes everything the role granted."""
        group = self.role.group
        deleted = super().delete(*args, **kwargs)
        group.user_set.remove(self.user)
        return deleted
