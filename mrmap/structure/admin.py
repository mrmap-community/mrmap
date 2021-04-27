from django.contrib import admin
from django.contrib.auth.models import Permission
from acl.admin_forms import GroupAdminForm
from structure.models import *
from users.models import UserActivation


class RoleAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'description')
    search_fields = ['id', 'name', 'description', ]


class OrganizationAdmin(admin.ModelAdmin):
    list_display = ['id', 'name', 'person_name', 'country', 'city', 'postal_code']
    search_fields = ['id', 'name', 'country', 'city', 'postal_code']
    form = GroupAdminForm


class PermissionAdmin(admin.ModelAdmin):
    list_display = ["name", ]
    search_fields = ['name', 'codename', ]


class UserActivationAdmin(admin.ModelAdmin):
    list_display = ['user', 'activation_until']


class PublishRequestAdmin(admin.ModelAdmin):
    list_display = ['from_organization', 'to_organization', 'activation_until', 'created_by_user']


admin.site.register(PublishRequest, PublishRequestAdmin)
admin.site.register(UserActivation, UserActivationAdmin)
admin.site.register(Organization, OrganizationAdmin)
admin.site.register(Permission, PermissionAdmin)
