from django.apps import apps

from accounts import settings


def organizations_of(user):
    """The organizations the given user is a member of.

    An ``Organization`` IS a group - membership is membership in the group
    the organization extends - and a user can belong to several of them
    (#727 Q3). This is the one answer to "which organizations may own a
    resource created by this user?"; a caller deciding ownership must not
    read ``user.groups`` by a name pattern besides it.

    Args:
        user: the user to ask, may be None or anonymous

    Returns:
        QuerySet: the organizations the user is member of
    """
    # late import: this module answers questions about the app registry for
    # app code; pulling a model at import time would make it unusable from
    # anywhere the models are still importing themselves
    from accounts.models.groups import Organization

    if user is None or not user.is_authenticated:
        return Organization.objects.none()
    return Organization.objects.filter(pk__in=user.groups.all())


def get_secured_models():
    model_list = []
    for secured_model in settings.SECURED_MODELS:
        app_label, model_name = secured_model.split('.')
        model_list.append(apps.get_model(
            app_label=app_label, model_name=model_name))
    return model_list
