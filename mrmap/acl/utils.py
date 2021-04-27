from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.db.models import Q, QuerySet
from acl.models.acl import AccessControlList
from acl.settings import DEFAULT_MEMBER_PERMISSIONS, DEFAULT_ORGANIZATION_ADMIN_PERMISSIONS


def collect_default_permissions():
    # collect configured default permissions for admin acl and member acl
    admin_perms = Permission.objects.none
    member_perms = []
    for model in AccessControlList.get_ownable_models():
        admin_perms |= Permission.objects.filter(content_type=ContentType.objects.get_for_model(model))

        for default_perm in DEFAULT_MEMBER_PERMISSIONS:
            member_perms.append(f'{model._meta.app_label}.{default_perm}_{model.__name__.lower()}')

    for default_perm in DEFAULT_ORGANIZATION_ADMIN_PERMISSIONS:
        admin_perms.append(f'structure.{default_perm}_organization')

    for default_perm in DEFAULT_MEMBER_PERMISSIONS:
        member_perms.append(f'structure.{default_perm}_organization')
    return admin_perms, get_perms_for_perm_list(member_perms)


def get_perms_for_perm_list(perms) -> QuerySet:
    query = None
    for perm in perms:
        if not query:
            query = Q()
        app_label, codename = perm.split('.')
        query |= Q(content_type__app_label=app_label, codename=codename)
    if query:
        permissions = Permission.objects.filter(query)
    else:
        permissions = Permission.objects.none
    return permissions
