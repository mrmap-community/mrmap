from django.core.checks import register, Tags, Error

from acl.settings import OWNABLE_MODELS
from acl.utils import get_model_from_string


@register(Tags.compatibility)
def check_settings(app_configs, **kwargs):
    """ Check that settings are implemented properly
        :param app_configs: a list of apps to be checks or None for all
        :param kwargs: keyword arguments
        :return: a list of errors
        """
    errors = []
    if not OWNABLE_MODELS:
        msg = "You need to configure the GUARDIAN_ROLES_OWNER_MODEL setting."
        errors.append(Error(msg))

    for model in OWNABLE_MODELS:
        model_class = get_model_from_string(model)
        model_instance = model_class()
        if not hasattr(model_instance, 'owned_by_org'):
            msg = f"'{model}' need to implement 'owned_by_org' attribute."
            errors.append(Error(msg))
    return errors






