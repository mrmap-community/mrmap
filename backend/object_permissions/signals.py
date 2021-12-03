from auth.models.groups import Organization
from django.contrib.auth.models import Group, Permission
from django.db.models.signals import post_save
from django.db.transaction import atomic
from django.dispatch import receiver
from django.utils.translation import gettext_lazy as _
from guardian.shortcuts import assign_perm

from object_permissions.utils import get_secured_models


@receiver(post_save, sender=Organization)
def handle_organization_creation(instance, created, **kwargs):
    if created:
        with atomic():
            organization = instance  # only for better reading

            # create organization administrator and member group
            orga_admins = Group.objects.create(
                name=f"{organization.name} Administrators")
            assign_perm(perm='registry.view_organization',
                        user_or_group=orga_admins, obj=organization)
            assign_perm(perm='registry.change_organization',
                        user_or_group=orga_admins, obj=organization)

            orga_members = Group.objects.create(
                name=f"{organization.name} Members")
            assign_perm(perm='registry.view_organization',
                        user_or_group=orga_members, obj=organization)
            assign_perm(perm='registry.can_publish_for_organization',
                        user_or_group=orga_members, obj=organization)

            # create groups for any configured secured model
            for secured_model in get_secured_models():
                # FIXME: name max_length is 150 chars. Maybe this could be not enough
                secured_model_admins = Group.objects.create(
                    name=f"{organization.name} {secured_model._meta.model_name} Admins")

                assign_perm(perm='registry.view_group',
                            user_or_group=orga_admins,
                            obj=secured_model_admins)
                assign_perm(perm='registry.change_group',
                            user_or_group=orga_admins,
                            obj=secured_model_admins)


def handle_secured_model_creation(instance, created, **kwargs):
    if created:
        with atomic():
            instance_admins = Group.objects.get(
                name=f'{instance.owner.name} {instance._meta.model_name} Admins')
            global_add_perm = Permission.objects.get(
                codename=f'add_{instance._meta.model_name}', content_type__app_label=instance._meta.app_label, content_type__model=instance._meta.model_name)
            instance_admins.permissions.add(global_add_perm)
            assign_perm(perm=f'{instance._meta.app_label}.view_{instance._meta.model_name}',
                        user_or_group=instance_admins,
                        obj=instance)
            assign_perm(perm=f'{instance._meta.app_label}.change_{instance._meta.model_name}',
                        user_or_group=instance_admins,
                        obj=instance)
            assign_perm(perm=f'{instance._meta.app_label}.delete_{instance._meta.model_name}',
                        user_or_group=instance_admins,
                        obj=instance)


for model in get_secured_models():
    post_save.connect(receiver=handle_secured_model_creation,
                      sender=model,
                      dispatch_uid=f"handle_secured_model_creation_for_{model}")
