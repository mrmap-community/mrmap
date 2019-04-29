from django.contrib import admin

# Register your models here.
from django.contrib.admin import site

from service.models import *


class CategoryAdmin(admin.ModelAdmin):
    pass


class ServiceTypeAdmin(admin.ModelAdmin):
    list_display = ('name', 'version')


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


class ServiceAdmin(admin.ModelAdmin):
    list_display = ('id', 'created_by', 'servicetype')
    pass


class ReferenceSystemAdmin(admin.ModelAdmin):
    pass


class LayerAdmin(admin.ModelAdmin):
    pass


class ServiceToFormatAdmin(admin.ModelAdmin):
    pass

admin.site.register(Category, CategoryAdmin)
admin.site.register(ServiceType, ServiceTypeAdmin)
admin.site.register(Module, ModuleAdmin)
admin.site.register(Dataset, DatasetAdmin)
admin.site.register(Keyword, KeywordAdmin)
admin.site.register(Metadata, MetadataAdmin)
admin.site.register(TermsOfUse, TermsOfUseAdmin)
admin.site.register(ReferenceSystem, ReferenceSystemAdmin)
admin.site.register(Service, ServiceAdmin)
admin.site.register(ServiceToFormat, ServiceToFormatAdmin)
admin.site.register(Layer, LayerAdmin)
