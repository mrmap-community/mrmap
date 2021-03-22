from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.db.models.signals import post_save, m2m_changed, post_delete
from django.dispatch import receiver
from guardian.shortcuts import assign_perm, remove_perm
from guardian_roles.models.core import TemplateRole, ObjectBasedTemplateRole, OrganizationBasedTemplateRole
from guardian_roles.utils import get_owner_model
from service.models import Metadata


def _generate_object_based_template_roles(instance):
    """generate one `ObjectBasedTemplateRole` per `TemplateRole` for given instance

    Args:
        instance: the instance for that the `ObjectBasedTemplateRole` instances shall be generated.

    Returns:
        object_based_template_roles (list): a list of all generated `ObjectBasedTemplateRole` objects
    """
    content_type = ContentType.objects.get_for_model(instance)
    object_based_template_roles = []
    for role in TemplateRole.objects.filter(permissions__content_type=content_type):
        object_based_template_roles.append(ObjectBasedTemplateRole.objects.get_or_create(object_pk=instance.pk,
                                           content_type=content_type,
                                           based_template=role)[0])
    return object_based_template_roles


@receiver(post_save, sender=Metadata)
def assign_perm_to_object(sender, instance, created, **kwargs):
    """assign guardian user and group permissions on created instance"""
    if created:
        content_type = ContentType.objects.get_for_model(instance)
        for obj in _generate_object_based_template_roles(instance):
            users = get_user_model().objects.filter(role__based_template=obj.based_template)
            obj.user_set.add(*users)
            for perm in obj.based_template.permissions.filter(content_type=content_type):
                object_based_perm = assign_perm(perm=perm, user_or_group=obj, obj=instance)
                object_based_perm.object_based_template_role = obj
                # todo: bulk_update() for multi-table inheritance models is not supported for now.
                #  see: https://code.djangoproject.com/ticket/28821#no1
                object_based_perm.save()


@receiver(post_save, sender=Metadata)
def handle_owner_change(sender, instance, created, **kwargs):
    if not created:
        if instance.owned_by_org != instance._owned_by_org:
            # todo: implement owner change handling
            # MetadataGroupObjectPermission.objects.filter(group=instance._created_by, content_object=instance).bulk_update(group=instance.created_by)
            pass


@receiver(post_delete, sender=Metadata)
def handle_instance_delete(sender, instance, **kwargs):
    # delete all `ObjectBasedTemplateRole` objects. This is needed cause the `GenericForeignKey` does not support
    # on_delete=models.CASCADE method.
    ObjectBasedTemplateRole.objects.filter(object_pk=instance.pk).delete()


@receiver(m2m_changed, sender=TemplateRole.permissions.through)
def handle_template_role_permission_change(sender, instance, action, reverse, model, pk_set, **kwargs):
    if reverse:
        # instance ==> object of `Permission`
        # model ==> model of `TemplateRole`
        # pk_set ==> list of `TemplateRole`
        # todo: not implemented now
        #  this will only be relevant if Permission.role_set.add(), .remove() or clear() is called
        pass
    else:
        # instance ==> object of `TemplateRole`
        # model ==> model of `Permission`
        # pk_set ==> list of `Permission`
        permissions = model.objects.filter(pk__in=pk_set)
        object_based_template_roles = ObjectBasedTemplateRole.objects.filter(based_template=instance)
        if action == 'post_add':
            # we need to create new `GroupObjectPermission` objects per related `ObjectBasedTemplateRole` and
            # added `Permission` object.
            for object_based_template_role in object_based_template_roles:
                for perm in permissions:
                    object_based_perm = assign_perm(perm=perm,
                                                    user_or_group=object_based_template_role,
                                                    obj=object_based_template_role.content_object)
                    # object_based_perm.object_based_template_role = object_based_template_role
                    # todo: bulk_update() for multi-table inheritance models is not supported for now.
                    #  see: https://code.djangoproject.com/ticket/28821#no1
                    # object_based_perm.save()
        if action == 'post_remove':
            # we need to remove all `GroupObjectPermission` objects per related `ObjectBasedTemplateRole` and
            # `Permission`
            for object_based_template_role in object_based_template_roles:
                for perm in permissions:
                    remove_perm(perm=perm,
                                user_or_group=object_based_template_role,
                                obj=object_based_template_role.content_object)


@receiver(post_save, sender=get_owner_model())
def handle_organization_creation(sender, instance, created, **kwargs):
    """creates `OrganizationBasedTemplateRole` objects based on the configured `TemplateRole` objects

    Args:
        sender: `settings.OWNER_MODEL`
        instance: the instance of `settings.OWNER_MODEL` which is changed
        created: boolean flag which is True if the instance is new

    Returns:
        None

    """
    if instance.is_auto_generated:
        # we handle only real organizations for permission/role handling
        return
    if created:
        for template_role in TemplateRole.objects.all():
            OrganizationBasedTemplateRole.objects.create(content_object=instance,
                                                         based_template=template_role)


@receiver(m2m_changed, sender=OrganizationBasedTemplateRole.users.through)
def handle_users_changed(sender, instance, action, reverse, model, pk_set, **kwargs):
    """handle the change of user membership on `OrganizationBasedTemplateRole` instances.
    If a user is added or removed the user_set must be mirrored to all related `ObjectBasedTemplateRole` instances.

    Args:
        sender: the users field of `OrganizationBasedTemplateRole`
        instance: instance of model `settings.AUTH_USER_MODEL` (reverse) | `OrganizationBasedTemplateRole` (! reverse)
        action (str): pre_add | post_add | pre_remove | post_remove | pre_clear | post_clear
        reverse: boolean flag which is True if reverse relation was used
        model: `OrganizationBasedTemplateRole` (reverse) | `settings.AUTH_USER_MODEL` (! reverse)
        pk_set: list of `OrganizationBasedTemplateRole` (reverse) | list of `settings.AUTH_USER_MODEL` (! reverse)
        **kwargs:

    Returns:
        None
    """
    if reverse:
        users = [instance, ]
        used_template_roles = TemplateRole.objects.filter(guardian_roles_organizationbasedtemplaterole_concrete_template__in=pk_set)
        object_based_template_roles = ObjectBasedTemplateRole.objects.filter(based_template__in=used_template_roles)
    else:
        users = get_user_model().objects.filter(pk__in=pk_set)
        object_based_template_roles = ObjectBasedTemplateRole.objects.filter(based_template=instance.based_template)

    for object_based_template_role in object_based_template_roles:
        if action == 'post_add':
            object_based_template_role.user_set.add(*users)
        elif action == 'post_remove':
            object_based_template_role.user_set.remove(*users)
        elif action == 'post_clear':
            object_based_template_role.user_set.clear()
