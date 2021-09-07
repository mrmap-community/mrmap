"""
dedicated MrMap model based permissions to optimize performance

For more information on this file, see
https://django-guardian.readthedocs.io/en/v2.3.0/userguide/performance.html#direct-foreign-keys

"""
from guardian.models import UserObjectPermissionBase, GroupObjectPermissionBase
from django.db import models

from resourceNew.models import Service


class ServiceUserObjectPermission(UserObjectPermissionBase):
    content_object = models.ForeignKey(to=Service, on_delete=models.CASCADE)


class ServiceGroupObjectPermission(GroupObjectPermissionBase):
    content_object = models.ForeignKey(to=Service, on_delete=models.CASCADE)
