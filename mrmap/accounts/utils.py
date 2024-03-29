from django.apps import apps

from accounts import settings


def get_secured_models():
    model_list = []
    for secured_model in settings.SECURED_MODELS:
        app_label, model_name = secured_model.split('.')
        model_list.append(apps.get_model(
            app_label=app_label, model_name=model_name))
    return model_list
