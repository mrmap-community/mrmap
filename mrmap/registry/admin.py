from django.contrib import admin

from registry.models import FeatureTypeElement, MetadataContact, Service, ServiceType, Layer
from registry.models.mapcontext import MapContext
from registry.models.security import OGCOperation, AllowedOperation, ProxySetting


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
