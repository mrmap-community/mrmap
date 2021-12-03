"""
dedicated model based permissions to optimize performance

For more information on this file, see
https://django-guardian.readthedocs.io/en/v2.3.0/userguide/performance.html#direct-foreign-keys

"""
from auth.models.groups import Organization
from django.db import models

from guardian.models import GroupObjectPermissionBase, UserObjectPermissionBase


class OrganizationUserObjectPermission(UserObjectPermissionBase):
    content_object = models.ForeignKey(
        to=Organization, on_delete=models.CASCADE)


class OrganizationGroupObjectPermission(GroupObjectPermissionBase):
    content_object = models.ForeignKey(
        to=Organization, on_delete=models.CASCADE)
