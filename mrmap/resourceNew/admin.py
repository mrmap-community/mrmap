from django.contrib import admin

from resourceNew.models import FeatureTypeElement, MetadataContact, Service, ServiceType, Layer
from resourceNew.models.mapcontext import MapContext
from resourceNew.models.security import OGCOperation, AllowedOperation, ProxySetting
from service.models import MapContextLayer


@admin.register(FeatureTypeElement)
class FeatureTypeElementAdmin(admin.ModelAdmin):
    list_display = ["name", "data_type"]
    search_fields = ["name", "data_type"]
    readonly_fields = ["feature_type"]


admin.site.register(MetadataContact)
admin.site.register(Service)
admin.site.register(ServiceType)
admin.site.register(OGCOperation)
admin.site.register(AllowedOperation)
admin.site.register(ProxySetting)
admin.site.register(Layer)
admin.site.register(MapContext)
admin.site.register(MapContextLayer)
