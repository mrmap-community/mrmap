from django.contrib import admin

# Register your models here.
from structure.models import *


class RoleAdmin(admin.ModelAdmin):
    list_display = [p.name for p in Role._meta.fields]


class OrganizationAdmin(admin.ModelAdmin):
    list_display = ['organization_name', 'country', 'city', 'postal_code']


class GroupAdmin(admin.ModelAdmin):
    list_display = [p.name for p in Group._meta.fields]


class PermissionAdmin(admin.ModelAdmin):
    list_display = [p.name for p in Permission._meta.fields]


admin.site.register(Role, RoleAdmin)
admin.site.register(Group, GroupAdmin)
admin.site.register(Organization, OrganizationAdmin)
admin.site.register(Permission, PermissionAdmin)
