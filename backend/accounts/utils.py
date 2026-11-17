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


def models_of(names):
    """The model classes behind the ``"<app_label>.<ModelName>"`` names.

    Args:
        names: iterable of dotted model names as the settings hold them

    Returns:
        list: the model classes, in the order of ``names``

    Raises:
        LookupError: a name is not a model of this project - which is what
            ``accounts.checks`` reports instead of letting a command fail
    """
    model_list = []
    for model_name in names:
        app_label, model_name = model_name.split('.')
        model_list.append(apps.get_model(
            app_label=app_label, model_name=model_name))
    return model_list


def get_role_managed_models():
    """The model classes of ``accounts.settings.ROLE_MANAGED_MODELS``.

    The bootstrap of ``accounts.signals`` connects its creation receiver to
    exactly these models; the equipment a listed model must bring is told by
    the setting itself and guarded by ``accounts.checks`` (#735).

    Returns:
        list: the role-managed model classes, in the order of the setting
    """
    return models_of(settings.ROLE_MANAGED_MODELS)


def get_guardian_perf_models():
    """The model classes of ``accounts.settings.GUARDIAN_PERF_MODELS``.

    These are the models which answer their object permissions from a pair of
    dedicated tables instead of guardian's generic ones (#735). The list
    itself explains why each model has them; the declarations live in
    ``accounts/models/guardian.py`` and ``registry/models/guardian.py``.

    Returns:
        list: the model classes with dedicated object permission tables
    """
    return models_of(settings.GUARDIAN_PERF_MODELS)
