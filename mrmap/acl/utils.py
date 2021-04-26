from django.apps import apps as django_apps
from django.conf import settings
from django.contrib.auth.models import Permission
from django.core.exceptions import ImproperlyConfigured
from django.db.models import Q, QuerySet

from acl.settings import OWNABLE_MODELS, DEFAULT_ADMIN_PERMISSIONS, DEFAULT_MEMBER_PERMISSIONS, \
    DEFAULT_ORGANIZATION_ADMIN_PERMISSIONS


def collect_default_permissions():
    # collect configured default permissions for admin acl and member acl
    admin_perms = []
    member_perms = []
    for model in OWNABLE_MODELS:
        app_label, model_name = model.split('.')
        for default_perm in DEFAULT_ADMIN_PERMISSIONS:
            admin_perms.append(f'{app_label}.{default_perm}_{model_name.lower()}')
        for default_perm in DEFAULT_MEMBER_PERMISSIONS:
            member_perms.append(f'{app_label}.{default_perm}_{model_name.lower()}')

    for default_perm in DEFAULT_ORGANIZATION_ADMIN_PERMISSIONS:
        admin_perms.append(f'structure.{default_perm}_organization')
    for default_perm in DEFAULT_MEMBER_PERMISSIONS:
        member_perms.append(f'structure.{default_perm}_organization')

    return admin_perms, member_perms


def construct_permission_query(perms) -> QuerySet:
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


def get_model_from_string(model: str):
    """
    Return the model class from given string.

    Args:
        model (str): model name in format 'app_label.model_name'

    Returns:
        the model class
    """
    try:
        return django_apps.get_model(model, require_ready=False)
    except ValueError:
        raise ImproperlyConfigured(f"{model} must be of the form 'app_label.model_name'")
    except LookupError:
        raise ImproperlyConfigured(
            "refers to model '%s' that has not been installed" % model
        )


def get_owner_model():
    """
    Return the owner model.
    """
    return get_model_from_string(settings.GUARDIAN_ROLES_OWNER_MODEL)
