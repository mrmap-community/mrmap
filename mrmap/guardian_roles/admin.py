from django.contrib import admin

from guardian.models import UserObjectPermission, GroupObjectPermission

from guardian_roles.models.acl import ObjectRelation, AccessControlList
from guardian_roles.models.object_perms import MetadataUserObjectPermission, MetadataGroupObjectPermission


admin.site.register(ObjectRelation)
admin.site.register(AccessControlList)


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


admin.site.register(MetadataUserObjectPermission, MetadataUserObjectPermissionAdmin)
admin.site.register(MetadataGroupObjectPermission, MetadataUserObjectPermissionAdmin)
