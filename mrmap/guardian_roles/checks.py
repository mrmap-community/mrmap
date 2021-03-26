from django.conf import settings
from django.core.checks import register, Tags, Error
from guardian_roles.utils import get_model_from_string


@register(Tags.compatibility)
def check_settings(app_configs, **kwargs):
    """ Check that settings are implemented properly
        :param app_configs: a list of apps to be checks or None for all
        :param kwargs: keyword arguments
        :return: a list of errors
        """
    checks = []
    if not settings.GUARDIAN_ROLES_OLD_OWNER_FIELD_ATTRIBUTE:
        msg = "You need to configure the GUARDIAN_ROLES_OLD_OWNER_FIELD_ATTRIBUTE setting."
        checks.append(Error(msg))

    if not settings.GUARDIAN_ROLES_OWNER_FIELD_ATTRIBUTE:
        msg = "You need to configure the GUARDIAN_ROLES_OWNER_FIELD_ATTRIBUTE setting."
        checks.append(Error(msg))
    if not settings.GUARDIAN_ROLES_OWNER_MODEL:
        msg = "You need to configure the GUARDIAN_ROLES_OWNER_MODEL setting."
        checks.append(Error(msg))

    for model in settings.GUARDIAN_ROLES_OWNABLE_MODELS:
        model_class = get_model_from_string(model)
        model_instance = model_class()
        if not hasattr(model_instance, settings.GUARDIAN_ROLES_OWNER_FIELD_ATTRIBUTE):
            msg = f"'{model}' need to implement '{settings.GUARDIAN_ROLES_OWNER_FIELD_ATTRIBUTE}' attribute."
            checks.append(Error(msg))
        if not hasattr(model_instance, settings.GUARDIAN_ROLES_OLD_OWNER_FIELD_ATTRIBUTE):
            msg = f"'{model}' need to implement '{settings.GUARDIAN_ROLES_OLD_OWNER_FIELD_ATTRIBUTE}' attribute."
            checks.append(Error(msg))

    return checks






