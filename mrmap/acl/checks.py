from django.core.checks import register, Tags, Error
from acl.models.acl import AccessControlList


@register(Tags.compatibility)
def check_settings(app_configs, **kwargs):
    """ Check that settings are implemented properly
        :param app_configs: a list of apps to be checks or None for all
        :param kwargs: keyword arguments
        :return: a list of errors
        """
    errors = []

    for model in AccessControlList.get_ownable_models():
        model_instance = model()
        if not hasattr(model_instance, 'owned_by_org'):
            msg = f"'{model}' need to implement 'owned_by_org' attribute."
            errors.append(Error(msg))
    return errors






