from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
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
    unsuported_actions = ['pre_add', 'pre_remove', 'pre_clear']
    if action in unsuported_actions:
        return

    if reverse:
        object_based_template_roles = ObjectBasedTemplateRole.objects.filter(based_template__pk__in=pk_set,
                                                                             content_type=instance.content_type)
        for object_based_template_role in object_based_template_roles:
            if action == 'post_add':
                assign_perm(perm=instance,
                            user_or_group=object_based_template_role,
                            obj=object_based_template_role.content_object)

            elif action == 'post_remove' or action == 'post_clear':
                remove_perm(perm=instance,
                            user_or_group=object_based_template_role,
                            obj=object_based_template_role.content_object)
    else:
        permissions = model.objects.filter(pk__in=pk_set)
        for perm in permissions:
            object_based_template_roles = ObjectBasedTemplateRole.objects.filter(based_template=instance,
                                                                                 content_type=perm.content_type)
            for object_based_template_role in object_based_template_roles:
                if action == 'post_add':
                    assign_perm(perm=perm,
                                user_or_group=object_based_template_role,
                                obj=object_based_template_role.content_object)

                elif action == 'post_remove' or action == 'post_clear':
                    remove_perm(perm=perm,
                                user_or_group=object_based_template_role,
                                obj=object_based_template_role.content_object)


@receiver(post_save, sender=get_owner_model())
def handle_owner_based_template_role_creation(sender, instance, created, **kwargs):
    """creates `OwnerBasedTemplateRole` objects based on the configured `TemplateRole` objects if new instance of
    settings.OWNER_MODEL is created.

    Args:
        sender: `settings.OWNER_MODEL`
        instance: the instance of `settings.OWNER_MODEL` which is changed
        created: boolean flag which is True if the instance is new

    Returns:
        None

    """
    if created:
        default_roles = []
        content_type = ContentType.objects.get_for_model(OwnerBasedTemplateRole)
        for template_role in TemplateRole.objects.all():
            owner_based_role = OwnerBasedTemplateRole.objects.create(
                content_object=instance,
                based_template=template_role)
            object_based_role = ObjectBasedTemplateRole.objects.create(
                object_pk=owner_based_role.pk,
                content_type=content_type)

            default_roles.append((owner_based_role, object_based_role))

        admin_role = OwnerBasedTemplateRole.objects.get(
            content_object=instance,
            based_template__name=settings.GUARDIAN_ROLES_ADMIN_ROLE_FOR_ROLE_ADMIN_ROLE
        )

        for owner_based_role, object_based_role in default_roles:
            admin_role.object_based_template_roles.add(object_based_role)
            assign_perm(perm='guardian_roles.view_ownerbasedtemplaterole',
                        user_or_group=object_based_role,
                        obj=owner_based_role)
            assign_perm(perm='guardian_roles.change_ownerbasedtemplaterole',
                        user_or_group=object_based_role,
                        obj=owner_based_role)


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
    unsuported_actions = ['pre_add', 'pre_remove', 'pre_clear']
    if action in unsuported_actions:
        return

    content_type = ContentType.objects.get_for_model(OwnerBasedTemplateRole)

    if reverse:
        users = [instance, ]
        owner_based_template_roles = model.objects.filter(pk__in=pk_set).prefetch_related('object_based_template_roles')

        obj_based_template_roles = ObjectBasedTemplateRole.objects.none()
        for owner_role in owner_based_template_roles:
            obj_based_template_roles |= owner_role.object_based_template_roles.all()
        admin_roles = owner_based_template_roles.filter(
            based_template__name=settings.GUARDIAN_ROLES_ADMIN_ROLE_FOR_ROLE_ADMIN_ROLE)
        if admin_roles.exists():
            for admin_role in admin_roles:
                # get the `hidden` object based template roles which handles permissions for role viewing and changing
                obj_based_template_roles |= ObjectBasedTemplateRole.objects.filter(
                    object_pk=admin_role.pk,
                    content_type=content_type,
                    based_template=None)
    else:
        users = get_user_model().objects.filter(pk__in=pk_set)
        obj_based_template_roles = instance.object_based_template_roles.all()
        if instance.based_template.name == settings.GUARDIAN_ROLES_ADMIN_ROLE_FOR_ROLE_ADMIN_ROLE:
            # get the `hidden` object based template roles which handles permissions for role viewing and changing
            obj_based_template_roles |= ObjectBasedTemplateRole.objects.filter(
                object_pk=instance.pk,
                content_type=content_type,
                based_template=None)

    if action == 'post_add':
        for object_based_template_role in obj_based_template_roles:
            object_based_template_role.user_set.add(*users)

    elif action == 'post_remove' or action == 'post_clear':
        for object_based_template_role in obj_based_template_roles:
            object_based_template_role.user_set.remove(*users)
