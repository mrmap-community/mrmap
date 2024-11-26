from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class MapBenderCompConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'mapbender_compatibility'
    label = 'mapbender compatibility'
    verbose_name = _('MapBender Compatibility')
