"""
dedicated MrMap model based permissions to optimize performance

For more information on this file, see
https://django-guardian.readthedocs.io/en/v2.3.0/userguide/performance.html#direct-foreign-keys

"""
from guardian.models import UserObjectPermissionBase, GroupObjectPermissionBase
from django.db import models
from service.models import Metadata


class MetadataUserObjectPermission(UserObjectPermissionBase):
    content_object = models.ForeignKey(to=Metadata,
                                       on_delete=models.CASCADE,
                                       related_name="metadata_user_object_permissions")


class MetadataGroupObjectPermission(GroupObjectPermissionBase):
    content_object = models.ForeignKey(to=Metadata,
                                       on_delete=models.CASCADE,
                                       related_name="metadata_group_object_permissions")
