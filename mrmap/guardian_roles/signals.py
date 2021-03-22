from django.contrib.contenttypes.models import ContentType
from django.db.models.signals import post_save, m2m_changed, post_delete
from django.dispatch import receiver
from guardian.shortcuts import assign_perm, remove_perm
from guardian_roles.models.core import TemplateRole, ObjectBasedTemplateRole
from service.models import Metadata


def _generate_object_based_template_roles(instance):
    """generate one `ObjectBasedTemplateRole` per `TemplateRole` for given instance

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
        i = 0
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
