from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from guardian_roles.utils import get_model_from_string

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

    for model in OWNABLE_MODELS:
        model_class = get_model_from_string(model)
        model_instance = model_class()
        if not hasattr(model_instance, OWNER_FIELD_ATTRIBUTE):
            raise ImproperlyConfigured(f"'{model}' need to implement "
                                       f"'{OWNER_FIELD_ATTRIBUTE}' attribute.")
        if not hasattr(model_instance, OLD_OWNER_FIELD_ATTRIBUTE):
            raise ImproperlyConfigured(f"'{model}' need to implement "
                                       f"'{OLD_OWNER_FIELD_ATTRIBUTE}' attribute.")


check_configuration()
