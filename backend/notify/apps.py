from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class NotifyConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'notify'
    label = 'notify'
    verbose_name = _('Notify')

    def ready(self):
        import notify.signals  # noqa
