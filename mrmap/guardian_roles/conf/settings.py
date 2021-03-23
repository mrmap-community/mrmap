from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


DEFAULT_ROLES = getattr(settings, 'DEFAULT_ROLES', [])

OWNABLE_MODELS = getattr(settings, 'OWNABLE_MODELS', [])

OWNER_MODEL = getattr(settings, 'OWNER_MODEL', None)

OLD_OWNER_FIELD_ATTRIBUTE = getattr(settings, 'OLD_OWNER_FIELD_ATTRIBUTE', None)

OWNER_FIELD_ATTRIBUTE = getattr(settings, 'OWNER_FIELD_ATTRIBUTE', None)


def check_configuration():
    if not OLD_OWNER_FIELD_ATTRIBUTE:
        raise ImproperlyConfigured("You need to configure the OLD_OWNER_FIELD_ATTRIBUTE settings.")
    if not OWNER_FIELD_ATTRIBUTE:
        raise ImproperlyConfigured("You need to configure the OWNER_FIELD_ATTRIBUTE settings.")
    if not OWNER_MODEL:
        raise ImproperlyConfigured("You need to configure the OWNER_MODEL settings.")


check_configuration()
