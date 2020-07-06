from django.contrib import admin
from django.utils.safestring import mark_safe

from service.models import *
from django.urls import reverse
from django.template.defaultfilters import escape


class CategoryAdmin(admin.ModelAdmin):
    list_display = ('id', 'type', 'title_EN', 'online_link', 'origin')


class DatasetAdmin(admin.ModelAdmin):
    list_display = ('id', 'metadata', 'md_identifier_code')


class CategoryOriginAdmin(admin.ModelAdmin):
    pass


class DimensionAdmin(admin.ModelAdmin):
    list_display = ("id", "type", "extent")


class RequestOperationAdmin(admin.ModelAdmin):
    list_display = ('id', 'operation_name',)


class SecuredOperationAdmin(admin.ModelAdmin):
    list_display = ("id", 'secured_metadata', 'allowed_group', "operation")


class ServiceTypeAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'version')


class ModuleAdmin(admin.ModelAdmin):
    pass


class KeywordAdmin(admin.ModelAdmin):
    list_display = ('id', "keyword")


class DocumentAdmin(admin.ModelAdmin):
    list_display = ('id', 'metadata', 'document_type', 'is_original', 'is_active', 'created')
    list_filter = ('is_active',)
    search_fields = ['id', 'metadata__id', ]


class MetadataLanguageAdmin(admin.ModelAdmin):
    list_display = ('id', 'language', 'iso_639_2_tlc',)
    list_filter = ('language', 'iso_639_2_tlc',)
    search_fields = ['id', 'language', 'iso_639_2_tlc', ]


class MetadataAdmin(admin.ModelAdmin):
    list_display = ('id', 'title', 'service', 'identifier', 'metadata_type', 'is_active', 'is_broken', 'contact', 'uuid')
    list_filter = ('metadata_type', 'is_active', 'is_broken')
    search_fields = ['id', 'title', ]


class MetadataRelationAdmin(admin.ModelAdmin):
    list_display = ('id', 'metadata_from_link', 'relation_type', 'metadata_to_link')
    list_filter = ('relation_type',)
    search_fields = ['metadata_from__title', 'metadata_to__title',]

    def metadata_from_link(self, obj):
        return mark_safe('<a href="%s">%s</a>' % (reverse("admin:service_metadata_change", args=(obj.metadata_from.id,)), escape(obj.metadata_from)))

    metadata_from_link.allow_tags = True
    metadata_from_link.short_description = "metadata_from"

    def metadata_to_link(self, obj):
        return mark_safe('<a href="%s">%s</a>' % (reverse("admin:service_metadata_change", args=(obj.metadata_to.id,)), escape(obj.metadata_to)))

    metadata_to_link.allow_tags = True
    metadata_to_link.short_description = "metadata_to"


class TermsOfUseAdmin(admin.ModelAdmin):
    list_display = ('identifier', 'name', 'is_open_data', 'is_active')


class LegalReportAdmin(admin.ModelAdmin):
    list_display = ('id', 'title', 'explanation', 'date')


class LegalDateAdmin(admin.ModelAdmin):
    list_display = ('id', 'date_type_code')


class ServiceAdmin(admin.ModelAdmin):
    list_display = ('id', 'is_active', 'is_deleted',  'service_type', 'metadata', 'parent_service', 'published_for')
    pass


class ReferenceSystemAdmin(admin.ModelAdmin):
    list_display = ('id', 'code', 'prefix', 'version')
    pass


class FeatureTypeAdmin(admin.ModelAdmin):
    list_display = ('id', 'metadata', 'parent_service')


class FeatureTypeElementAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'type')


class LayerAdmin(admin.ModelAdmin):
    list_display = ('id', 'identifier', 'parent_service', 'parent_layer', 'last_modified')


class MimeTypeAdmin(admin.ModelAdmin):
    list_display = ('id', 'operation', 'mime_type')


class NamespaceAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'uri', 'version')


class ProxyLogAdmin(admin.ModelAdmin):
    list_display = ('id', 'metadata', 'operation', 'user', 'response_wms_megapixel', 'response_wfs_num_features', 'timestamp')


class ExternalAuthenticationAdmin(admin.ModelAdmin):
    list_display = ('id', 'metadata', 'auth_type')


class StyleAdmin(admin.ModelAdmin):
    list_display = ('id', 'layer',)


admin.site.register(Dimension, DimensionAdmin)
admin.site.register(Document, DocumentAdmin)
admin.site.register(RequestOperation, RequestOperationAdmin)
admin.site.register(SecuredOperation, SecuredOperationAdmin)
admin.site.register(Category, CategoryAdmin)
admin.site.register(CategoryOrigin, CategoryOriginAdmin)
admin.site.register(ServiceType, ServiceTypeAdmin)
admin.site.register(Module, ModuleAdmin)
admin.site.register(Dataset, DatasetAdmin)
admin.site.register(Keyword, KeywordAdmin)
admin.site.register(MetadataLanguage, MetadataLanguageAdmin)
admin.site.register(Metadata, MetadataAdmin)
admin.site.register(MetadataRelation, MetadataRelationAdmin)
admin.site.register(Licence, TermsOfUseAdmin)
admin.site.register(ReferenceSystem, ReferenceSystemAdmin)
admin.site.register(Service, ServiceAdmin)
admin.site.register(MimeType, MimeTypeAdmin)
admin.site.register(Layer, LayerAdmin)
admin.site.register(FeatureType, FeatureTypeAdmin)
admin.site.register(FeatureTypeElement, FeatureTypeElementAdmin)
admin.site.register(Namespace, NamespaceAdmin)
admin.site.register(ProxyLog, ProxyLogAdmin)
admin.site.register(ExternalAuthentication, ExternalAuthenticationAdmin)
admin.site.register(Style, StyleAdmin)

# NOT NEEDED ADMIN PAGES CAN BE OUTCOMMENTED

#admin.site.register(LegalDate, LegalDateAdmin)
#admin.site.register(LegalReport, LegalReportAdmin)
