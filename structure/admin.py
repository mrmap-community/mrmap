from django.contrib import admin

# Register your models here.
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.forms import UserChangeForm

from structure.models import *


class PendingTaskAdmin(admin.ModelAdmin):
    list_display = [p.name for p in PendingTask._meta.fields]


class RoleAdmin(admin.ModelAdmin):
    list_display = [p.name for p in Role._meta.fields]


class OrganizationAdmin(admin.ModelAdmin):
    list_display = ['id', 'organization_name', 'is_auto_generated', 'country', 'city', 'postal_code']


class ThemeAdmin(admin.ModelAdmin):
    list_display = ['id', 'name']


class GroupAdmin(admin.ModelAdmin):
    list_display = [p.name for p in MrMapGroup._meta.fields]


class GroupActivityAdmin(admin.ModelAdmin):
    list_display = [p.name for p in GroupActivity._meta.fields]


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
