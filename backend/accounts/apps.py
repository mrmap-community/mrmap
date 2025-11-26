import os

from django.apps import AppConfig
from django.db.models.signals import post_migrate
from django.utils.translation import gettext_lazy as _


class AccountsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'accounts'
    verbose_name = _('Accounts')

    def ready(self):
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
    if os.environ.get('MRMAP_PRODUCTION', False):
        if not Organization.objects.filter(name="Testorganization").exists():
            Organization.objects.create(name="Testorganization")
