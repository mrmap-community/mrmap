from django.contrib.auth import get_user_model
from django.db.models import Q
from django.db.models.signals import post_save, m2m_changed
from django.dispatch import receiver
from guardian.shortcuts import assign_perm, remove_perm
from guardian_roles.models.core import TemplateRole, ObjectBasedTemplateRole, OwnerBasedTemplateRole
from guardian_roles.utils import get_owner_model


@receiver(m2m_changed, sender=TemplateRole.permissions.through)
def handle_template_role_permission_change(sender, instance, action, reverse, model, pk_set, **kwargs):
    """handle the change of permissions on `TemplateRole` instances.
    If a permission is added or removed, all `GroupObjectPermission` that related to all given `ObjectBasedTemplateRole`
    instance need to become edited.

    Args:
        sender: the permissions field of `TemplateRole`
        instance: instance of model `Permission` (reverse) | `TemplateRole` (! reverse)
        action (str): pre_add | post_add | pre_remove | post_remove | pre_clear | post_clear
        reverse: boolean flag which is True if reverse relation was used
        model: `TemplateRole` (reverse) | `Permission` (! reverse)
        pk_set: list of `TemplateRole` (reverse) | list of `Permission` (! reverse)
        **kwargs:

    Returns:
        None
    """
    if reverse:
        permissions = [instance, ]
        object_based_template_roles = ObjectBasedTemplateRole.objects.filter(based_template__pk__in=pk_set)
    else:
        permissions = model.objects.filter(pk__in=pk_set)
        object_based_template_roles = ObjectBasedTemplateRole.objects.filter(based_template=instance)

    for object_based_template_role in object_based_template_roles:
        for perm in permissions:
            if action == 'post_add':
                assign_perm(perm=perm,
                            user_or_group=object_based_template_role,
                            obj=object_based_template_role.content_object)

            elif action == 'post_remove' or action == 'post_clear':
                remove_perm(perm=perm,
                            user_or_group=object_based_template_role,
                            obj=object_based_template_role.content_object)


@receiver(post_save, sender=get_owner_model())
def handle_owner_creation(sender, instance, created, **kwargs):
    """creates `OwnerBasedTemplateRole` objects based on the configured `TemplateRole` objects

    Args:
        sender: `settings.OWNER_MODEL`
        instance: the instance of `settings.OWNER_MODEL` which is changed
        created: boolean flag which is True if the instance is new

    Returns:
        None

    """
    # todo: find a generic way to hook in here
    if instance.is_auto_generated:
        # we handle only real organizations for permission/role handling
        return
    if created:
        for template_role in TemplateRole.objects.all():
            OwnerBasedTemplateRole.objects.create(content_object=instance,
                                                  based_template=template_role)


@receiver(m2m_changed, sender=OwnerBasedTemplateRole.users.through)
def handle_users_changed(sender, instance, action, reverse, model, pk_set, **kwargs):
    """handle the change of user membership on `OwnerBasedTemplateRole` instances.
    If a user is added or removed the user_set must be mirrored to all related `ObjectBasedTemplateRole` instances.

    Args:
        sender: the users field of `OwnerBasedTemplateRole`
        instance: instance of model `settings.AUTH_USER_MODEL` (reverse) | `OwnerBasedTemplateRole` (! reverse)
        action (str): pre_add | post_add | pre_remove | post_remove | pre_clear | post_clear
        reverse: boolean flag which is True if reverse relation was used
        model: `OwnerBasedTemplateRole` (reverse) | `settings.AUTH_USER_MODEL` (! reverse)
        pk_set: list of `OwnerBasedTemplateRole` (reverse) | list of `settings.AUTH_USER_MODEL` (! reverse)
        **kwargs:

    Returns:
        None
    """
    if reverse:
        users = [instance, ]
        query = Q(guardian_roles_ownerbasedtemplaterole_concrete_template__in=pk_set)
        used_template_roles = TemplateRole.objects.filter(query)
        object_based_template_roles = ObjectBasedTemplateRole.objects.filter(based_template__in=used_template_roles)
    else:
        users = get_user_model().objects.filter(pk__in=pk_set)
        object_based_template_roles = ObjectBasedTemplateRole.objects.filter(based_template=instance.based_template)

    for object_based_template_role in object_based_template_roles:
        if action == 'post_add':
            object_based_template_role.user_set.add(*users)
        elif action == 'post_remove' or action == 'post_clear':
            object_based_template_role.user_set.remove(*users)
