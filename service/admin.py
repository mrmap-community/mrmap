from django.contrib import admin

# Register your models here.
from django.contrib.admin import site

from service.models import *


class CategoryAdmin(admin.ModelAdmin):
    list_display = ('type', 'title_EN', 'online_link', 'origin')


class CategoryOriginAdmin(admin.ModelAdmin):
    pass


class ServiceTypeAdmin(admin.ModelAdmin):
    list_display = ('name', 'version')


class ModuleAdmin(admin.ModelAdmin):
    pass


class DatasetAdmin(admin.ModelAdmin):
    pass


class KeywordAdmin(admin.ModelAdmin):
    pass


class CapabilityDocumentAdmin(admin.ModelAdmin):
    list_display = ('related_metadata', 'created')


class MetadataOriginAdmin(admin.ModelAdmin):
    list_display = ('name',)


class MetadataAdmin(admin.ModelAdmin):
    list_display = ('title', 'identifier', 'is_broken', 'contact', 'uuid')


class MetadataRelationAdmin(admin.ModelAdmin):
    list_display = ('metadata_1', 'metadata_2', 'origin')


class TermsOfUseAdmin(admin.ModelAdmin):
    pass


class ServiceAdmin(admin.ModelAdmin):
    list_display = ('id', 'is_active', 'is_deleted',  'servicetype', 'metadata', 'parent_service', 'published_for')
    pass


class ReferenceSystemAdmin(admin.ModelAdmin):
    list_display = ('code', 'prefix', 'version')
    pass

class FeatureTypeAdmin(admin.ModelAdmin):
    list_display = ('title', 'service', 'identifier', 'abstract')

class FeatureTypeElementAdmin(admin.ModelAdmin):
    list_display = ('name', 'type')

class LayerAdmin(admin.ModelAdmin):
    list_display = ('identifier', 'parent_service', 'parent_layer', 'last_modified')

class MimeTypeAdmin(admin.ModelAdmin):
    pass

class NamespaceAdmin(admin.ModelAdmin):
    list_display = ('name', 'uri', 'version')


admin.site.register(CapabilityDocument, CapabilityDocumentAdmin)
admin.site.register(Category, CategoryAdmin)
admin.site.register(CategoryOrigin, CategoryOriginAdmin)
admin.site.register(ServiceType, ServiceTypeAdmin)
admin.site.register(Module, ModuleAdmin)
admin.site.register(Dataset, DatasetAdmin)
admin.site.register(Keyword, KeywordAdmin)
admin.site.register(MetadataOrigin, MetadataOriginAdmin)
admin.site.register(Metadata, MetadataAdmin)
admin.site.register(MetadataRelation, MetadataRelationAdmin)
admin.site.register(TermsOfUse, TermsOfUseAdmin)
admin.site.register(ReferenceSystem, ReferenceSystemAdmin)
admin.site.register(Service, ServiceAdmin)
admin.site.register(MimeType, MimeTypeAdmin)
admin.site.register(Layer, LayerAdmin)
admin.site.register(FeatureType, FeatureTypeAdmin)
admin.site.register(FeatureTypeElement, FeatureTypeElementAdmin)
admin.site.register(Namespace, NamespaceAdmin)
