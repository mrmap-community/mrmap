from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.db.models import Q
from django.db.models.signals import post_save
from django.dispatch import receiver

from guardian_roles.models.acl import AccessControlList
from guardian_roles.settings import DEFAULT_PERMISSIONS
from structure.models import Organization


@receiver(post_save, sender=Organization)
def handle_organization_creation(instance, created, **kwargs):
    """On organization creation, we create also one AccessControlList to allow administration of this Organization"""
    if created:
        Permission.objects.filter()
        query = Q()
        for perm in DEFAULT_PERMISSIONS:
            app_label, codename = perm.split('.')
            query |= Q(content_type__app_label=app_label, codename=codename)

        all_permissions = Permission.objects.filter(query)
        acl = AccessControlList.objects.create(name=f"{instance.organization_name} administrator",
                                               description='')
        acl.permissions.add(*all_permissions)
        acl.add_secured_object(instance)
