from django.contrib import admin

from guardian.models import UserObjectPermission, GroupObjectPermission

from acl.models.acl import AccessControlList
from acl.models.object_perms import ServiceUserObjectPermission, ServiceGroupObjectPermission


class AccessControlListAdmin(admin.ModelAdmin):
    autocomplete_fields = ['permissions']


admin.site.register(AccessControlList, AccessControlListAdmin)


"""
Django admin view pages for dedicated MrMap models placed in models.object_perms.py

For more information on this file, see
# todo: link to the docs

"""


class UserObjectPermissionAdmin(admin.ModelAdmin):
    pass


class GroupObjectPermissionAdmin(admin.ModelAdmin):
    pass


admin.site.register(UserObjectPermission, UserObjectPermissionAdmin)
admin.site.register(GroupObjectPermission, GroupObjectPermissionAdmin)


"""
Django admin view pages for dedicated MrMap models placed in models.object_perms.py

For more information on this file, see
# todo: link to the docs

"""


class MetadataUserObjectPermissionAdmin(admin.ModelAdmin):
    pass


class MetadataGroupObjectPermissionAdmin(admin.ModelAdmin):
    pass


admin.site.register(ServiceUserObjectPermission, MetadataUserObjectPermissionAdmin)
admin.site.register(ServiceGroupObjectPermission, MetadataUserObjectPermissionAdmin)
