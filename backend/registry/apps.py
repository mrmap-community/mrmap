from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class RegistryConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'registry'
    label = 'registry'
    verbose_name = _('Registry')
