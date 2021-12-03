from django.core.checks import register

from auth.utils import get_secured_models


@register()
def check_secured_models_list(app_configs, **kwargs):
    """ Check that settings are implemented properly
    :param app_configs: a list of apps to be checks or None for all
    :param kwargs: keyword arguments
    :return: a list of errors
    """
    errors = []
    get_secured_models()
    return errors
