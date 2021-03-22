from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import Permission
from guardian_roles.admin_forms import GroupAdminForm
from structure.models import *
from users.models import MrMapUser, UserActivation


class PendingTaskAdmin(admin.ModelAdmin):
    list_display = [p.name for p in PendingTask._meta.fields]


class RoleAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'description')
    search_fields = ['id', 'name', 'description', ]


class OrganizationAdmin(admin.ModelAdmin):
    list_display = ['id', 'organization_name', 'is_auto_generated', 'person_name', 'country', 'city', 'postal_code']
    list_filter = ('is_auto_generated', )
    search_fields = ['id', 'organization_name', 'country', 'city', 'postal_code']
    form = GroupAdminForm


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
                 )
             }
             ),
    ) + UserAdmin.fieldsets
    readonly_fields = (
        "confirmed_dsgvo",
        "user_permissions",  # Prevent accidental changes on user_permissions (inherited from AbstractUser) since groups manage permissions!
    )


class UserActivationAdmin(admin.ModelAdmin):
    list_display = ['user', 'activation_until']


class PublishRequestAdmin(admin.ModelAdmin):
    list_display = ['from_organization', 'to_organization', 'activation_until', 'created_by_user']


admin.site.register(PublishRequest, PublishRequestAdmin)
admin.site.register(UserActivation, UserActivationAdmin)
admin.site.register(Organization, OrganizationAdmin)
admin.site.register(PendingTask, PendingTaskAdmin)
admin.site.register(Permission, PermissionAdmin)
admin.site.register(MrMapUser, MrMapUserAdmin)
