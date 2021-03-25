"""
Core models to implement the possibility of Roles

For more information on this file, see
# todo: link to the docs

"""
from uuid import uuid4

from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.conf import settings
from guardian_roles.conf import settings as guardina_roles_settings


class TemplateRole(models.Model):
    """`TemplateRole` model to handle of one or more permissions as a template.
    Use this model to construct your custom roles.
    """
    name = models.CharField(max_length=60,
                            primary_key=True,
                            help_text=_("The unique name of the role"))
    verbose_name = models.CharField(max_length=60,
                                    verbose_name=_("Verbose name"),
                                    help_text=_("The verbose name of the role"))
    description = models.TextField(verbose_name=_("Description"),
                                   help_text=_("Describe what permissions this role shall grant"))
    permissions = models.ManyToManyField(to=Permission,
                                         related_name='role_set',
                                         blank=True)

    def __str__(self) -> str:
        return str(self.verbose_name)


class ConcreteTemplateRole(models.Model):
    """
    An abstract model to
    """
    # do not change after generation of this instance, cause permission changing is not implemented for base_template
    # changing.
    based_template = models.ForeignKey(to=TemplateRole,
                                       on_delete=models.CASCADE,
                                       related_name="%(app_label)s_%(class)s_concrete_template",
                                       null=True,
                                       blank=True)
    description = models.TextField(verbose_name=_("Description"),
                                   help_text=_("Describe what permissions this role shall grant"))

    class Meta:
        abstract = True

    def __str__(self):
        return '{} | {}'.format(
            str(self.content_object),
            str(self.based_template.verbose_name))

    def save(self, *args, **kwargs):
        if self._state.adding:
            self.description = _('handle permissions based on the "').__str__() + self.based_template.__str__() + _(
                '" `TemplateRole` for owner "').__str__() + self.content_object.__str__() + '"'
        super().save(*args, **kwargs)


class ObjectBasedTemplateRole(ConcreteTemplateRole, Group):
    """ObjectBasedTemplateRole model to handle Role groups per object.

    Creation:
        On object creation, one `ObjectBasedTemplateRole` per defined `Role` is generated.
        NOTE !!: do not create or change instance of this model manual.
          This `Permission` `Group`s are generated by permission/signals.py

    Needed cause:
        This is necessary to configure which users, independent of owner membership, have permissions to a
        **specific** object.

    User membership:
        Is handled by `OwnerBasedTemplateRole` objects. If a user is added/removed to a
        `OwnerBasedTemplateRole` all users of this specific `OwnerBasedTemplateRole` will be added/removed
         to all `ObjectBasedTemplateRole` objects with the same related base_template filtered by objects of the given
        owner.
    """
    object_pk = models.CharField(_('object ID'), max_length=255)
    content_object = GenericForeignKey(fk_field='object_pk')
    content_type = models.ForeignKey(to=ContentType, on_delete=models.CASCADE)

    def __str__(self):
        if self.content_type == ContentType.objects.get_for_model(OwnerBasedTemplateRole):
            return '{} | {}'.format(
                'role admin group for',
                str(self.content_object))
        else:
            return super().__str__()

    def save(self, *args, **kwargs):
        if self._state.adding:
            self.name = uuid4()
        super(ObjectBasedTemplateRole, self).save(*args, **kwargs)


class OwnerBasedTemplateRole(ConcreteTemplateRole):
    """OwnerBasedTemplateRole model to handle Role groups per organization.

    Creation:
        On `guardina_roles_settings.OWNER_MODEL` creation, one `OwnerBasedTemplateRole` per selected `TemplateRole` is
        generated.

    Needed cause:
        This is necessary to configure which users of an `guardina_roles_settings.OWNER_MODEL` should basically have
        which role to manage objects of this organization. This makes it possible to treat users from different
        `guardina_roles_settings.OWNER_MODEL` have permissions to **all** objects of the specified
        `guardina_roles_settings.OWNER_MODEL`.

    User membership:
        Is handled by the user it self.
    """
    content_object = models.ForeignKey(to=guardina_roles_settings.OWNER_MODEL,
                                       on_delete=models.CASCADE,
                                       related_name='owner_based_template_roles')
    users = models.ManyToManyField(
        to=settings.AUTH_USER_MODEL,
        verbose_name=_('users'),
        blank=True,
        help_text=_(
            'The users this role belongs to. A user will get all permissions '
            'granted to each of their roles.'
        ),
        related_name="role_set",
        related_query_name="role",
    )
    object_based_template_roles = models.ManyToManyField(
        to=ObjectBasedTemplateRole,
        blank=True,
        related_name="owner_set",
        related_query_name="owner",
    )
