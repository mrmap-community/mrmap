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
        post_migrate.connect(create_default_user_and_org, sender=self)


def create_default_user_and_org(sender, **kwargs):
    from django.contrib.auth import get_user_model

    from .models import Organization

    User = get_user_model()

    # Default Superuser
    username = os.environ.get("MRMAP_USER")
    password = os.environ.get("MRMAP_PASSWORD")
    if username and password and not User.objects.filter(username=username).exists():
        User.objects.create_superuser(username=username, password=password)

    # Default Organization
    # the parsed flag from settings, not the raw env value: a deployment
    # exports MRMAP_PRODUCTION as a string and the development compose passes
    # "False", which os.environ.get answers truthy - so this hook created the
    # organization in development stacks and its groups collided on the next
    # migrate after a TransactionTestCase truncation (#1141)
    if settings.MRMAP_PRODUCTION:
        if not Organization.objects.filter(name="Testorganization").exists():
            Organization.objects.create(name="Testorganization")
