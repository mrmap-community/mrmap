from django.contrib import admin

# Register your models here.
from django.contrib.auth.admin import UserAdmin
from django.urls import reverse
from django.utils.safestring import mark_safe
from django.template.defaultfilters import escape


from structure.models import *


class PendingTaskAdmin(admin.ModelAdmin):
    list_display = [p.name for p in PendingTask._meta.fields]


class RoleAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'description', 'permission_link')
    search_fields = ['id', 'name', 'description', ]

    def permission_link(self, obj):
        if obj.permission:
            return mark_safe('<a href="%s">%s</a>' % (reverse("admin:structure_permission_change", args=(obj.permission.id,)), escape(obj.permission)))
        else:
            "-"
    permission_link.allow_tags = True
    permission_link.short_description = "permission"


class OrganizationAdmin(admin.ModelAdmin):
    list_display = ['id', 'organization_name', 'is_auto_generated', 'country', 'city', 'postal_code']
    list_filter = ('is_auto_generated', )
    search_fields = ['id', 'organization_name', 'country', 'city', 'postal_code' ]


class ThemeAdmin(admin.ModelAdmin):
    list_display = ['id', 'name']


class GroupAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'description', 'parent_group_link', 'organization_link', 'role_link', 'created_by_link', 'is_public_group', )
    list_filter = ('role', 'created_by', 'is_public_group' )
    search_fields = ['id', 'name', 'description', 'parent_group__name', ]

    def parent_group_link(self, obj):
        if obj.parent_group:
            return mark_safe('<a href="%s">%s</a>' % (reverse("admin:structure_mrmapgroup_change", args=(obj.parent_group.id,)), escape(obj.parent_group)))
        else:
            "-"
    parent_group_link.allow_tags = True
    parent_group_link.short_description = "parent_group"

    def organization_link(self, obj):
        if obj.organization:
            return mark_safe('<a href="%s">%s</a>' % (reverse("admin:structure_organization_change", args=(obj.organization.id,)), escape(obj.organization)))
        else:
            "-"
    organization_link.allow_tags = True
    organization_link.short_description = "organization"

    def role_link(self, obj):
        if obj.role:
            return mark_safe('<a href="%s">%s</a>' % (reverse("admin:structure_role_change", args=(obj.role.id,)), escape(obj.role)))
        else:
            "-"
    role_link.allow_tags = True
    role_link.short_description = "role"

    def created_by_link(self, obj):
        if obj.created_by:
            return mark_safe('<a href="%s">%s</a>' % (reverse("admin:structure_mrmapgroup_change", args=(obj.created_by.id,)), escape(obj.created_by)))
        else:
            "-"
    created_by_link.allow_tags = True
    created_by_link.short_description = "Created by"


class GroupActivityAdmin(admin.ModelAdmin):
    list_display = ('id', 'group_link', 'description', 'user', 'metadata', 'created_on')
    list_filter = ('group', )
    search_fields = ['id', 'user__username', 'metadata', 'group__name', ]

    def group_link(self, obj):
        if obj.group:
            return mark_safe('<a href="%s">%s</a>' % (reverse("admin:structure_mrmapgroup_change", args=(obj.group.id,)), escape(obj.group)))
        else:
            "-"
    group_link.allow_tags = True
    group_link.short_description = "group"


class PermissionAdmin(admin.ModelAdmin):
    list_display = [p.name for p in Permission._meta.fields]


class MrMapUserAdmin(UserAdmin):
    # We want to use the UserAdmin interface, which provides great support for security related settings.
    # But it won't show all the fields, that exist in our custom User class.
    # Therefore we need to reference them like this.
    model = MrMapUser
    fieldsets = (
            ("User details",
             {
                 'fields': (
                     'organization',
                     'confirmed_newsletter',
                     'confirmed_survey',
                     'confirmed_dsgvo',
                     'theme',
                 )
             }
             ),
    ) + UserAdmin.fieldsets
    readonly_fields = ("confirmed_dsgvo",)


class UserActivationAdmin(admin.ModelAdmin):
    list_display = ['id', 'user', 'activation_until']


class PendingRequestAdmin(admin.ModelAdmin):
    list_display = ['type', 'group', 'organization', 'activation_until']


admin.site.register(PendingRequest, PendingRequestAdmin)
admin.site.register(UserActivation, UserActivationAdmin)
admin.site.register(GroupActivity, GroupActivityAdmin)
admin.site.register(Organization, OrganizationAdmin)
admin.site.register(PendingTask, PendingTaskAdmin)
admin.site.register(Permission, PermissionAdmin)
admin.site.register(MrMapUser, MrMapUserAdmin)
admin.site.register(MrMapGroup, GroupAdmin)
admin.site.register(Theme, ThemeAdmin)
admin.site.register(Role, RoleAdmin)
