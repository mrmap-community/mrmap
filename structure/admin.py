from django.contrib import admin

# Register your models here.
from structure.models import *


class RoleAdmin(admin.ModelAdmin):
    list_display = [p.name for p in Role._meta.fields]


class OrganizationAdmin(admin.ModelAdmin):
    list_display = ['organization_name', 'is_auto_generated', 'country', 'city', 'postal_code']


class GroupAdmin(admin.ModelAdmin):
    list_display = [p.name for p in Group._meta.fields]

class GroupActivityAdmin(admin.ModelAdmin):
    list_display = [p.name for p in GroupActivity._meta.fields]

class PermissionAdmin(admin.ModelAdmin):
    list_display = [p.name for p in Permission._meta.fields]


class UserAdmin(admin.ModelAdmin):
    list_display = ['id', 'person_name', 'username', 'last_login']


class UserActivationAdmin(admin.ModelAdmin):
    list_display = ['id', 'user']

class PendingRequestAdmin(admin.ModelAdmin):
    list_display = ['type', 'group', 'organization', 'activation_until']


admin.site.register(User, UserAdmin)
admin.site.register(UserActivation, UserActivationAdmin)
admin.site.register(Role, RoleAdmin)
admin.site.register(Group, GroupAdmin)
admin.site.register(GroupActivity, GroupActivityAdmin)
admin.site.register(Organization, OrganizationAdmin)
admin.site.register(Permission, PermissionAdmin)
admin.site.register(PendingRequest, PendingRequestAdmin)
