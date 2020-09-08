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
    list_display = ('id', 'name', 'description')
    search_fields = ['id', 'name', 'description', ]


class OrganizationAdmin(admin.ModelAdmin):
    list_display = ['id', 'organization_name', 'is_auto_generated', 'person_name', 'country', 'city', 'postal_code']
    list_filter = ('is_auto_generated', )
    search_fields = ['id', 'organization_name', 'country', 'city', 'postal_code']


class ThemeAdmin(admin.ModelAdmin):
    list_display = ['id', 'name']


class GroupAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'description', 'parent_group_link', 'organization_link', 'role_link', 'created_by_link', 'is_public_group', 'is_permission_group', )
    list_filter = ('role', 'created_by', 'is_public_group' )
    search_fields = ['id', 'name', 'description', 'parent_group__name', ]
    readonly_fields = (
        "permissions",  # prevent accidental changing of permissions. Permissions are managed by Roles
    )

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
    list_display = ["name",]


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
    readonly_fields = (
        "confirmed_dsgvo",
        "user_permissions",  # Prevent accidental changes on user_permissions (inherited from AbstractUser) since groups manage permissions!
    )


class UserActivationAdmin(admin.ModelAdmin):
    list_display = ['id', 'user', 'activation_until']


class PublishRequestAdmin(admin.ModelAdmin):
    list_display = ['group', 'organization', 'activation_until', 'created_by']

class GroupInvitationAdmin(admin.ModelAdmin):
    list_display = ['invited_user', 'to_group', 'activation_until', 'created_by']


admin.site.register(PublishRequest, PublishRequestAdmin)
admin.site.register(GroupInvitationRequest, GroupInvitationAdmin)
admin.site.register(UserActivation, UserActivationAdmin)
admin.site.register(GroupActivity, GroupActivityAdmin)
admin.site.register(Organization, OrganizationAdmin)
admin.site.register(PendingTask, PendingTaskAdmin)
admin.site.register(Permission, PermissionAdmin)
admin.site.register(MrMapUser, MrMapUserAdmin)
admin.site.register(MrMapGroup, GroupAdmin)
admin.site.register(Theme, ThemeAdmin)
admin.site.register(Role, RoleAdmin)
