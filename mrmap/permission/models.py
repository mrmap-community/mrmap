from guardian.models import UserObjectPermissionBase, GroupObjectPermissionBase
from django.db import models

from service.models import Metadata


class MetadataUserObjectPermission(UserObjectPermissionBase):
    """create dedicated user permission table for metadata objects to speed up"""
    content_object = models.ForeignKey(Metadata, on_delete=models.CASCADE)


class MetadataGroupObjectPermission(GroupObjectPermissionBase):
    """create dedicated group permission table for metadata objects to speed up"""
    content_object = models.ForeignKey(Metadata, on_delete=models.CASCADE)
