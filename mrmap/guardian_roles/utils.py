from django.apps import apps as django_apps
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


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
