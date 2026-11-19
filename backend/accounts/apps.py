import os

from django.apps import AppConfig
from django.conf import settings
from django.db.models.signals import post_migrate
from django.utils.translation import gettext_lazy as _

#: the name the sweep of expired role memberships has in the schedule of beat
#: (#741); the tests look the row up by it
MEMBERSHIP_EXPIRY_TASK_NAME = "revoke expired role memberships"


def create_membership_expiry_task(sender, **kwargs):
    """Creates the periodic task which revokes expired role memberships.

    ``valid_until`` of #732 says when a grant ends, and the facade of #734
    refuses an expired membership on the role axes; what it cannot refuse is a
    guardian grant of the role's *group*, which reaches the person until the
    membership row is gone. Only this sweep closes that (#741's AC4), so the
    row of ``PeriodicTask`` is what makes the field mean what it says.

    Keyed by its name and asked by the whole shape of its crontab, like every
    other row of beat: a deployment which re-scheduled the sweep over the api
    keeps what it chose, and a bare minute lookup would answer the rows of the
    other sweeps and die on ``MultipleObjectsReturned`` (#1273).
    """
    from django_celery_beat.models import CrontabSchedule, PeriodicTask

    # at fifty past the hour: the housekeeping of the deployment is spread
    # over the hour (import every five minutes, dump at :05, probe artifacts
    # at :20, job history at :30, incidents at :40) and this sweep takes the
    # next free slot
    schedule, _ = CrontabSchedule.objects.get_or_create(
        minute="50", hour="*", day_of_week="*",
        day_of_month="*", month_of_year="*")

    PeriodicTask.objects.get_or_create(
        name=MEMBERSHIP_EXPIRY_TASK_NAME,
        defaults={
            "crontab": schedule,
            "task": "accounts.tasks.revoke_expired_role_memberships",
        }
    )


class AccountsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'accounts'
    verbose_name = _('Accounts')

    def ready(self):
        # connects the permission bootstrap of this app to post_save, the
        # module has to be imported for any of its receivers to run
        import accounts.signals  # noqa
        # registers the system checks of #735 on the check registry: a check
        # has to be registered before the framework runs, and the app being
        # ready is the documented moment an app may do that
        import accounts.checks  # noqa
        post_migrate.connect(create_default_user_and_org, sender=self)
        post_migrate.connect(ensure_anonymous_viewer_hook, sender=self)
        post_migrate.connect(create_membership_expiry_task, sender=self)


def create_default_user_and_org(sender, **kwargs):
    from django.contrib.auth import get_user_model

    from .models import Organization

    user_model = get_user_model()

    # Default Superuser
    # the setting, not the raw env value: the setting is where MRMAP_USER is
    # named, so the account and the internal contexts falling back to it read
    # the same deployment value (#1278)
    username = settings.MRMAP_USER
    password = os.environ.get("MRMAP_PASSWORD")
    if username and password and not user_model.objects.filter(username=username).exists():
        user_model.objects.create_superuser(username=username, password=password)

    # Default Organization
    # the parsed flag from settings, not the raw env value: a deployment
    # exports MRMAP_PRODUCTION as a string and the development compose passes
    # "False", which os.environ.get answers truthy - so this hook created the
    # organization in development stacks and its groups collided on the next
    # migrate after a TransactionTestCase truncation (#1141)
    if settings.MRMAP_PRODUCTION:
        if not Organization.objects.filter(name="Testorganization").exists():
            Organization.objects.create(name="Testorganization")


def ensure_anonymous_viewer_hook(sender, **kwargs):
    """Guards the rows which make anonymous view grants possible (#739).

    A ``post_migrate`` receiver, so - like ``create_default_user_and_org`` -
    it never sees the ``raw`` signal of a ``loaddata`` and takes no part in
    the rule of ``accounts/signals.py``. It creates what migration 0009
    cannot make durable: guardian's anonymous user row (guardian 3.x only
    reads it) and its membership in the role group the migration seeded. The
    work is idempotent and small; a database which was migrated normally
    spends three selects on it.

    It answers nothing when the catalogue holds no definition to build on.
    The ``flush`` of a ``TransactionTestCase`` emits ``post_migrate`` over the
    tables it has just truncated, so the rows 0009 seeded are gone with the
    rest and the next ``migrate`` or ``sync_role_definitions`` writes them
    again: a hook which raised here would take the teardown of every flushing
    test down with it, which is the trap #1141 tells for the default
    organization. ``ensure_anonymous_viewer`` keeps its strict answer for the
    callers which ask for the group deliberately.
    """
    from accounts.models.roles import ANONYMOUS_VIEWER_ROLE, RoleDefinition
    from accounts.utils import ensure_anonymous_viewer

    if not RoleDefinition.objects.filter(
            slug=ANONYMOUS_VIEWER_ROLE).exists():
        return

    ensure_anonymous_viewer()
