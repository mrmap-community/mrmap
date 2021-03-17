from django.contrib import admin
from guardian.models import GroupObjectPermission, UserObjectPermission

from permission.models import MetadataUserObjectPermission, MetadataGroupObjectPermission


class UserObjectPermissionAdmin(admin.ModelAdmin):
    pass


class GroupObjectPermissionAdmin(admin.ModelAdmin):
    pass


class MetadataUserObjectPermissionAdmin(admin.ModelAdmin):
    pass


class MetadataGroupObjectPermissionAdmin(admin.ModelAdmin):
    pass


admin.site.register(UserObjectPermission, UserObjectPermissionAdmin)
admin.site.register(GroupObjectPermission, GroupObjectPermissionAdmin)
admin.site.register(MetadataUserObjectPermission, MetadataUserObjectPermissionAdmin)
admin.site.register(MetadataGroupObjectPermission, MetadataGroupObjectPermissionAdmin)
