from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class CswConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'csw'
    label = 'csw'
    verbose_name = _('csw')
