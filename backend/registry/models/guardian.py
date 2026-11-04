"""
dedicated model based permissions to optimize performance

For more information on this file, see
https://django-guardian.readthedocs.io/en/v2.3.0/userguide/performance.html#direct-foreign-keys

Guardian names the object of an object permission it stores generically by
``content_type`` and the text of its primary key, in one table for every model.
A lookup for a model with a uuid primary key compares that text column by casting
it to a uuid, and whether the plan evaluates the cast only for the rows of the
looked up model or for the rows of every other model in the table is its own
decision: one row of a model with an integer primary key can make the lookup of a
service fail with ``invalid input syntax for type uuid``.

A model with a table of its own is answered from that table, so the services,
which the permission bootstrap of ``accounts.signals`` grants object permissions
on, have their tables here. The organizations and groups it also grants on are
in ``accounts/models/guardian.py``.
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
