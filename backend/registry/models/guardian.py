"""
dedicated model based permissions to optimize performance

For more information on this file, see
https://django-guardian.readthedocs.io/en/v2.3.0/userguide/performance.html#direct-foreign-keys

"""
from django.db import models
from registry.models.service import WebFeatureService, WebMapService

from guardian.models import GroupObjectPermissionBase, UserObjectPermissionBase


class WebMapServiceUserObjectPermission(UserObjectPermissionBase):
    content_object = models.ForeignKey(
        to=WebMapService, on_delete=models.CASCADE)


class WebMapServiceGroupObjectPermission(GroupObjectPermissionBase):
    content_object = models.ForeignKey(
        to=WebMapService, on_delete=models.CASCADE)


class WebFeatureServiceUserObjectPermission(UserObjectPermissionBase):
    content_object = models.ForeignKey(
        to=WebFeatureService, on_delete=models.CASCADE)


class WebFeatureServiceGroupObjectPermission(GroupObjectPermissionBase):
    content_object = models.ForeignKey(
        to=WebFeatureService, on_delete=models.CASCADE)
