from django.apps import apps as django_apps
from guardian_roles.conf import settings as guardina_roles_settings
from django.core.exceptions import ImproperlyConfigured


def get_owner_model():
    """
    Return the User model that is active in this project.
    """
    try:
        return django_apps.get_model(guardina_roles_settings.OWNER_MODEL, require_ready=False)
    except ValueError:
        raise ImproperlyConfigured("OWNER_MODEL must be of the form 'app_label.model_name'")
    except LookupError:
        raise ImproperlyConfigured(
            "OWNER_MODEL refers to model '%s' that has not been installed" % guardina_roles_settings.OWNER_MODEL
        )
