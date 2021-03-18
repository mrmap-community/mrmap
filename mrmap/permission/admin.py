from django.contrib import admin
from permission.models.core import TemplateRole, ObjectBasedTemplateRole
from guardian.models import UserObjectPermission, GroupObjectPermission
from permission.models.object_perms import MetadataUserObjectPermission, MetadataGroupObjectPermission

"""
Django admin view pages for core models placed models.core.py

For more information on this file, see
# todo: link to the docs

"""


class TemplateRoleAdmin(admin.ModelAdmin):
    filter_horizontal = ('permissions',)


class ObjectBasedTemplateRoleAdmin(admin.ModelAdmin):
    fields = ('name', 'object_pk', 'content_type', 'based_template', 'description')


admin.site.register(TemplateRole, TemplateRoleAdmin)
admin.site.register(ObjectBasedTemplateRole, ObjectBasedTemplateRoleAdmin)
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
