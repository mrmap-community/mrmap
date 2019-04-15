from django.contrib import admin

# Register your models here.
from structure.models import *


class RoleAdmin(admin.ModelAdmin):
    pass

class UserAdmin(admin.ModelAdmin):
    pass


class OrganizationAdmin(admin.ModelAdmin):
    pass


class GroupAdmin(admin.ModelAdmin):
    pass


class PermissionsAdmin(admin.ModelAdmin):
    pass


class UserGroupRoleRelAdmin(admin.ModelAdmin):
    pass

admin.site.register(Role, RoleAdmin)
admin.site.register(User, UserAdmin)
admin.site.register(Organization, OrganizationAdmin)
admin.site.register(Permissions, PermissionsAdmin)
admin.site.register(UserGroupRoleRel, UserGroupRoleRelAdmin)
