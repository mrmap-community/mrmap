from django.db.models.signals import post_save
from django.dispatch import receiver
from acls.models.acls import AccessControlList
from acls.utils import collect_default_permissions
from registry.models.service import CatalougeService, WebFeatureService, WebMapService
from users.models.groups import Organization
from django.utils.translation import gettext_lazy as _
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType


def create_acl(name: str, owned_by_org: Organization, permissions, description: str = '', organization_admin: bool = False):
    acl = AccessControlList.objects.create(name=name,
                                           description=description,
                                           owned_by_org=owned_by_org,
                                           default_acl=True,
                                           organization_admin=True)
    acl.permissions.add(*permissions)
    acl.accessible_organizations.add(owned_by_org)


#@receiver(post_save, sender=Organization)
def handle_organization_creation(instance, created, **kwargs):
    """On organization creation, we create also one AccessControlList to allow administration of this Organization"""
    if created:
        organization = instance  # only for better reading

        if organization.is_autogenerated:
            return

        admin_permissions, member_permissions = collect_default_permissions()

        create_acl(name=f"{organization.name} administrators",
                   description=_('Organization administrators can administrate all objects which are owned by the organization it self'),
                   owned_by_org=organization,
                   permissions=admin_permissions,
                   organization_admin=True)
        create_acl(name=f"{organization.name} members",
                   description=_('Organization members can view all objects which are owned by the organization it self'),
                   owned_by_org=organization,
                   permissions=member_permissions)
        create_acl(name=f"{organization.name} service administrators",
                   description=_('Service administrators can perform all actions for all resources which are owned by the organization it self'),
                   owned_by_org=organization,
                   permissions=Permission.objects.filter(content_type=ContentType.objects.get_for_model(WebMapService)))
        create_acl(name=f"{organization.name} service administrators",
                   description=_('Service administrators can perform all actions for all resources which are owned by the organization it self'),
                   owned_by_org=organization,
                   permissions=Permission.objects.filter(content_type=ContentType.objects.get_for_model(WebFeatureService)))
        create_acl(name=f"{organization.name} service administrators",
                   description=_('Service administrators can perform all actions for all resources which are owned by the organization it self'),
                   owned_by_org=organization,
                   permissions=Permission.objects.filter(content_type=ContentType.objects.get_for_model(CatalougeService)))
