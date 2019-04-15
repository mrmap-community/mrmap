from django.contrib import admin

# Register your models here.
from django.contrib.admin import site

from service.models import *


class CategoryAdmin(admin.ModelAdmin):
    pass


class ServiceTypeAdmin(admin.ModelAdmin):
    pass


class WMSAdmin(admin.ModelAdmin):
    pass


class WFSAdmin(admin.ModelAdmin):
    pass


class ModuleAdmin(admin.ModelAdmin):
    pass


class DatasetAdmin(admin.ModelAdmin):
    pass


class KeywordAdmin(admin.ModelAdmin):
    pass


class MetadataAdmin(admin.ModelAdmin):
    pass


class TermsOfUseAdmin(admin.ModelAdmin):
    pass


class ServiceMetadataAdmin(admin.ModelAdmin):
    pass


class ReferenceSystemAdmin(admin.ModelAdmin):
    pass


class ContentMetadataAdmin(admin.ModelAdmin):
    pass


admin.site.register(Category, CategoryAdmin)
admin.site.register(ServiceType, ServiceTypeAdmin)
admin.site.register(WMS, WMSAdmin)
admin.site.register(WFS, WFSAdmin)
admin.site.register(Module, ModuleAdmin)
admin.site.register(Dataset, DatasetAdmin)
admin.site.register(Keyword, KeywordAdmin)
admin.site.register(Metadata, MetadataAdmin)
admin.site.register(TermsOfUse, TermsOfUseAdmin)
admin.site.register(ServiceMetadata, ServiceMetadataAdmin)
admin.site.register(ReferenceSystem, ReferenceSystemAdmin)
admin.site.register(ContentMetadata, ContentMetadataAdmin)
