from django.contrib import admin

# Register your models here.
from django.contrib.auth.admin import UserAdmin

from structure.models import *

class PendingTaskAdmin(admin.ModelAdmin):
    list_display = [p.name for p in PendingTask._meta.fields]

class RoleAdmin(admin.ModelAdmin):
    list_display = [p.name for p in Role._meta.fields]


class OrganizationAdmin(admin.ModelAdmin):
    list_display = ['organization_name', 'is_auto_generated', 'country', 'city', 'postal_code']


class ThemeAdmin(admin.ModelAdmin):
    list_display = ['id', 'name']

class GroupAdmin(admin.ModelAdmin):
    list_display = [p.name for p in MrMapGroup._meta.fields]

class GroupActivityAdmin(admin.ModelAdmin):
    list_display = [p.name for p in GroupActivity._meta.fields]

class PermissionAdmin(admin.ModelAdmin):
    list_display = [p.name for p in Permission._meta.fields]


class UserAdmin(UserAdmin):
    list_display = ['id', 'username', 'last_login', 'theme']


class UserActivationAdmin(admin.ModelAdmin):
    list_display = ['id', 'user']

class PendingRequestAdmin(admin.ModelAdmin):
    list_display = ['type', 'group', 'organization', 'activation_until']


admin.site.register(PendingTask, PendingTaskAdmin)
admin.site.register(Role, RoleAdmin)
admin.site.register(Organization, OrganizationAdmin)

admin.site.register(Theme, ThemeAdmin)

admin.site.register(MrMapUser, UserAdmin)
admin.site.register(UserActivation, UserActivationAdmin)
admin.site.register(MrMapGroup, GroupAdmin)
admin.site.register(GroupActivity, GroupActivityAdmin)
admin.site.register(Permission, PermissionAdmin)
admin.site.register(PendingRequest, PendingRequestAdmin)
