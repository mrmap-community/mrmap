from django.apps import apps as django_apps
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


def get_owner_model():
    """
    Return the User model that is active in this project.
    """
    try:
        return django_apps.get_model(settings.OWNER_MODEL, require_ready=False)
    except ValueError:
        raise ImproperlyConfigured("OWNER_MODEL must be of the form 'app_label.model_name'")
    except LookupError:
        raise ImproperlyConfigured(
            "OWNER_MODEL refers to model '%s' that has not been installed" % settings.OWNER_MODEL
        )
