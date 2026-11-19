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


def anonymous_viewer_group():
    """The group which makes a resource public, or ``None`` when absent.

    A ``view_<model>`` object grant onto this group is the statement
    "anonymous may view this" (#739): guardian maps every anonymous request
    to its anonymous database user, that user is a member of this group, and
    the group's grants are therefore answered through the same object-grant
    axis of the #734 facade which decides the detail endpoint - list, detail
    and hint cannot disagree about what is public.

    Returns:
        Group or None: the group of the active ``anonymous_viewer`` role,
        ``None`` on a database which was not migrated to the role of #739
    """
    # late import like everywhere else in this module: app code asks this
    # question while the models are still importing themselves
    from accounts.models.roles import ANONYMOUS_VIEWER_ROLE, Role

    role = Role.objects.with_definition(ANONYMOUS_VIEWER_ROLE).first()
    return role.group if role is not None else None


def ensure_anonymous_viewer():
    """Create the anonymous viewer's role group and its member, idempotently.

    Migration 0009 seeds the role for every migrated database; this is the
    runtime guard for the rows the migration cannot make durable:

    * guardian 3.x *reads* its anonymous user row and never writes one - the
      row is created lazily by nothing else here, and a missing row makes
      every anonymous permission check raise ``User.DoesNotExist`` (the gap
      ``tests/AGENTS.md`` tells unit tests to paper over by hand);
    * a deployment which deleted the group of the role, or whose flush of a
      ``TransactionTestCase`` removed the rows the migration wrote, would
      silently answer "nothing is public" rather than say so.

    Creates: the ``Role`` and group of the catalogue's ``anonymous_viewer``
    definition (when absent), the guardian anonymous user row, and its
    membership in the group - which is all the membership this role ever
    has: nobody *becomes* the anonymous viewer by a decision.

    Returns:
        tuple: ``(user, group)`` of the anonymous viewer
    """
    from django.contrib.auth import get_user_model
    from django.contrib.auth.hashers import make_password
    from django.contrib.auth.models import Group
    from guardian.conf import settings as guardian_settings

    from accounts.models.roles import (ANONYMOUS_VIEWER_ROLE,
                                       RoleDefinition, free_role_group_name,
                                       role_group_name)

    definition = RoleDefinition.objects.filter(
        slug=ANONYMOUS_VIEWER_ROLE).first()
    if definition is None:
        raise RuntimeError(
            "The catalogue holds no 'anonymous_viewer' definition; run the "
            "migrations of #739 before asking for its role group.")

    role = definition.roles.filter(organization__isnull=True).first()
    if role is None:
        # the check-then-create shape of RoleQuerySet.create_for_organization:
        # a group written before a failed create would stay behind as an orphan
        # - and a group of exactly the base name which no role manages is
        # REUSED, the way migration 0009 does, so a truncate and re-seed round
        # does not stack a second group beside the first
        base = role_group_name(None, ANONYMOUS_VIEWER_ROLE)
        group = Group.objects.filter(
            name=base, role__isnull=True).first()
        if group is None:
            group = Group.objects.create(
                name=free_role_group_name(None, ANONYMOUS_VIEWER_ROLE))
        role = definition.roles.create(organization=None, group=group)

    user_model = get_user_model()
    anonymous, _ = user_model.objects.get_or_create(
        username=guardian_settings.ANONYMOUS_USER_NAME,
        defaults={"password": make_password(None)})
    # the membership is direct group membership, not a RoleMembership row:
    # that model is the human-readable record of a decision, and the
    # anonymous viewer is nobody's decision - it is the shape of the platform
    role.group.user_set.add(anonymous)
    return anonymous, role.group
