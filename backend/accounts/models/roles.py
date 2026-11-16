from django.contrib.auth.models import Permission
from django.db import models
from django.db.models.deletion import ProtectedError
from django.utils.translation import gettext_lazy as _


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
