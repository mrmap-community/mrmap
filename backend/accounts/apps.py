import os

from django.apps import AppConfig
from django.conf import settings
from django.db.models.signals import post_migrate
from django.utils.translation import gettext_lazy as _


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
    """
    from accounts.utils import ensure_anonymous_viewer

    ensure_anonymous_viewer()
