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
    list_display = ('id',  'servicetype')
    pass


class ReferenceSystemAdmin(admin.ModelAdmin):
    list_display = ('code', 'prefix', 'version')
    pass

class FeatureTypeAdmin(admin.ModelAdmin):
    list_display = ('title', 'name', 'abstract')

class FeatureTypeElementAdmin(admin.ModelAdmin):
    list_display = ('name', 'type')

class LayerAdmin(admin.ModelAdmin):
    pass

class MimeTypeAdmin(admin.ModelAdmin):
    pass

class NamespaceAdmin(admin.ModelAdmin):
    list_display = ('name', 'uri', 'version')

admin.site.register(Category, CategoryAdmin)
admin.site.register(ServiceType, ServiceTypeAdmin)
admin.site.register(Module, ModuleAdmin)
admin.site.register(Dataset, DatasetAdmin)
admin.site.register(Keyword, KeywordAdmin)
admin.site.register(Metadata, MetadataAdmin)
admin.site.register(TermsOfUse, TermsOfUseAdmin)
admin.site.register(ReferenceSystem, ReferenceSystemAdmin)
admin.site.register(Service, ServiceAdmin)
admin.site.register(MimeType, MimeTypeAdmin)
admin.site.register(Layer, LayerAdmin)
admin.site.register(FeatureType, FeatureTypeAdmin)
admin.site.register(FeatureTypeElement, FeatureTypeElementAdmin)
admin.site.register(Namespace, NamespaceAdmin)
