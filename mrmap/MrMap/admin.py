from django.apps import apps
from django.contrib import admin
from mptt2.admin import MPTTModelAdmin
from registry.admin.harvest import TemporaryMdMetadataFileAdmin
from registry.models.mapcontext import MapContextLayer
from registry.models.service import Layer

# all other models
models = apps.get_models()

for model in models:
    try:
        if model.__name__ == 'TemporaryMdMetadataFile':
            admin.site.register(model, TemporaryMdMetadataFileAdmin)
        if model.__name__ not in ['MapContextLayer', 'Layer']:
            admin.site.register(model)
    except admin.sites.AlreadyRegistered:
        pass

admin.site.register(MapContextLayer, MPTTModelAdmin)
admin.site.register(Layer, MPTTModelAdmin)
