from django.apps import apps
from django.contrib import admin
from mptt.admin import MPTTModelAdmin
from registry.models.mapcontext import MapContextLayer

# all other models
models = apps.get_models()

for model in models:
    try:
        if not model.__name__ == 'MapContextLayer':
            admin.site.register(model)
    except admin.sites.AlreadyRegistered:
        pass

admin.site.register(MapContextLayer, MPTTModelAdmin)
