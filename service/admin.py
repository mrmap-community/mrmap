from django.contrib import admin
from django.utils.safestring import mark_safe

from service.models import *
from django.urls import reverse
from django.template.defaultfilters import escape


class CategoryOriginAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'uri', )
    search_fields = ['id', 'name', 'uri', ]


class CategoryAdmin(admin.ModelAdmin):
    list_display = ('id', 'type', 'title_EN', 'online_link', )
    list_filter = ('type', )
    search_fields = ['id', 'type', 'title_EN', 'online_link', ]


class DatasetAdmin(admin.ModelAdmin):
    list_display = ('id', 'metadata_link', 'date_stamp', 'md_identifier_code', 'created_by_link', 'last_modified', )
    list_filter = ('language_code', 'character_set_code', 'update_frequency_code', 'legal_restriction_code', 'created_by')
    search_fields = ['id', 'metadata__title', 'md_identifier_code', 'date_stamp', 'created_by__name', 'last_modified', ]

    def metadata_link(self, obj):
        return mark_safe('<a href="%s">%s</a>' % (reverse("admin:service_metadata_change", args=(obj.metadata.id,)), escape(obj.metadata)))

    metadata_link.allow_tags = True
    metadata_link.short_description = "metadata"

    def created_by_link(self, obj):
        if obj.created_by:
            return mark_safe('<a href="%s">%s</a>' % (reverse("admin:structure_mrmapgroup_change", args=(obj.created_by.id,)), escape(obj.created_by)))
        else:
            "-"
    created_by_link.allow_tags = True
    created_by_link.short_description = "created_by"


class DimensionAdmin(admin.ModelAdmin):
    list_display = ("id", "type", "extent", "custom_name")
    list_filter = ('type', )
    search_fields = ['id', 'type', 'extent', 'custom_name', ]


class DocumentAdmin(admin.ModelAdmin):
    list_display = ('id', 'metadata_link', 'document_type', 'is_original', 'is_active', 'created', 'created_by_link', 'last_modified')
    list_filter = ('is_active', 'document_type', 'is_original', 'is_active', )
    search_fields = ['id', 'metadata__id', 'metadata__title', 'last_modified']

    def metadata_link(self, obj):
        return mark_safe('<a href="%s">%s</a>' % (reverse("admin:service_metadata_change", args=(obj.metadata.id,)), escape(obj.metadata)))

    metadata_link.allow_tags = True
    metadata_link.short_description = "metadata"

    def created_by_link(self, obj):
        if obj.created_by:
            return mark_safe('<a href="%s">%s</a>' % (reverse("admin:structure_mrmapgroup_change", args=(obj.created_by.id,)), escape(obj.created_by)))
        else:
            "-"

    created_by_link.allow_tags = True
    created_by_link.short_description = "created_by"


class ExternalAuthenticationAdmin(admin.ModelAdmin):
    list_display = ('id', 'metadata', 'auth_type')
    list_filter = ('auth_type',)
    search_fields = ['id', 'metadata__id', ]


class FeatureTypeElementAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'type', 'created', 'created_by')
    list_filter = ('created_by', )
    search_fields = ['id', 'name', 'type', 'created', 'created_by__name', ]


class FeatureTypeAdmin(admin.ModelAdmin):
    list_display = ('id', 'metadata', 'parent_service', 'created', 'created_by', 'last_modified')
    list_filter = ('created_by',)
    search_fields = ['id', 'metadata__title', 'created', 'created_by__name', ]


class KeywordAdmin(admin.ModelAdmin):
    list_display = ('id', "keyword")
    search_fields = ['id', 'keyword', ]


class LayerAdmin(admin.ModelAdmin):
    list_display = ('id', 'metadata', 'identifier', 'parent_service', 'parent_layer', 'created', 'created_by', 'last_modified')
    list_filter = ('created_by',)
    search_fields = ['id', 'metadata__title', 'identifier', 'created', 'created_by__name', 'last_modified',]


class MetadataAdmin(admin.ModelAdmin):
    list_display = ('id', 'title', 'service', 'identifier', 'metadata_type', 'is_active', 'is_broken', 'contact')
    list_filter = ('metadata_type', 'is_active', 'is_broken')
    search_fields = ['id', 'title', ]
    ordering = ["-created"]
    readonly_fields = (
        "related_metadata",
    )


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


class MetadataTypeAdmin(admin.ModelAdmin):
    list_display = ('id', 'type',)
    list_filter = ('type', )
    search_fields = ['id', 'type',]


class TermsOfUseAdmin(admin.ModelAdmin):
    list_display = ('identifier', 'name', 'is_open_data', 'is_active')

    def service_link(self, obj):
        if obj.service:
            return mark_safe('<a href="%s">%s</a>' % (reverse("admin:service_service_change", args=(obj.service.id,)), escape(obj.service)))
        else:
            return ''
    service_link.allow_tags = True
    service_link.short_description = "service"


class MimeTypeAdmin(admin.ModelAdmin):
    list_display = ('id', 'operation', 'mime_type')
    list_filter = ('operation', 'mime_type',)
    search_fields = ['id', 'operation', 'mime_type', ]


class ModuleAdmin(admin.ModelAdmin):
    list_display = ('id', 'type', )
    list_filter = ('type', )
    search_fields = ['id', 'type', ]


class NamespaceAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'uri', 'version')
    list_filter = ('version',)
    search_fields = ['id', 'name', 'uri', 'version', ]


class ProxyLogAdmin(admin.ModelAdmin):
    list_display = ('id', 'metadata', 'operation', 'user', 'response_wms_megapixel', 'response_wfs_num_features', 'timestamp')
    list_filter = ('operation', )
    search_fields = ['id', 'metadata__title', 'timestamp', ]


class ReferenceSystemAdmin(admin.ModelAdmin):
    list_display = ('id', 'code', 'prefix', 'version')
    list_filter = ('version', 'prefix', 'code')
    search_fields = ['id', 'code', 'prefix', 'version', ]


class RequestOperationAdmin(admin.ModelAdmin):
    list_display = ('id', 'operation_name',)
    list_filter = ('operation_name', )
    search_fields = ['id', 'operation_name', ]


class SecuredOperationAdmin(admin.ModelAdmin):
    list_display = ("id", 'secured_metadata', 'allowed_group', "operation")
    list_filter = ('operation', 'allowed_group')
    search_fields = ['id', 'operation', 'secured_metadata__title', 'allowed_group__name']


class GenericUrlAdmin(admin.ModelAdmin):
    list_display = ('method', 'description', 'url')
    search_fields = ['id', 'service__metadata__title']


class ServiceUrlAdmin(admin.ModelAdmin):
    list_display = ('operation', 'method', 'description', 'url')
    search_fields = ['id', 'service__metadata__title']


class ServiceTypeAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'version')
    list_filter = ('version', 'name', )
    search_fields = ['id', 'version', 'name']


class ServiceAdmin(admin.ModelAdmin):
    list_display = ('id', 'is_active', 'is_deleted',  'service_type', 'metadata_link', 'parent_service_link', 'published_for', 'created_by')
    list_filter = ('is_active', 'is_deleted', 'service_type', 'published_for')
    search_fields = ['id', 'metadata__title']
    readonly_fields = ("operation_urls",)
    ordering = ["-created"]

    def metadata_link(self, obj):
        return mark_safe('<a href="%s">%s</a>' % (reverse("admin:service_metadata_change", args=(obj.metadata.id,)), escape(obj.metadata)))

    metadata_link.allow_tags = True
    metadata_link.short_description = "metadata"

    def parent_service_link(self, obj):
        if obj.parent_service:
            return mark_safe('<a href="%s">%s</a>' % (reverse("admin:service_service_change", args=(obj.parent_service.id,)), escape(obj.parent_service)))
        else:
            "-"
    parent_service_link.allow_tags = True
    parent_service_link.short_description = "parent_service"


class StyleAdmin(admin.ModelAdmin):
    list_display = ('id', 'layer',)
    search_fields = ['id', 'layer__identifier']


class LegalReportAdmin(admin.ModelAdmin):
    list_display = ('id', 'title', 'explanation', 'date')


class LegalDateAdmin(admin.ModelAdmin):
    list_display = ('id', 'date_type_code')


admin.site.register(Dimension, DimensionAdmin)
admin.site.register(Document, DocumentAdmin)
admin.site.register(RequestOperation, RequestOperationAdmin)
admin.site.register(SecuredOperation, SecuredOperationAdmin)
admin.site.register(Category, CategoryAdmin)
admin.site.register(Module, ModuleAdmin)
admin.site.register(Dataset, DatasetAdmin)
admin.site.register(Keyword, KeywordAdmin)
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
#admin.site.register(ServiceType, ServiceTypeAdmin)
admin.site.register(ServiceUrl, ServiceUrlAdmin)
admin.site.register(GenericUrl, GenericUrlAdmin)
