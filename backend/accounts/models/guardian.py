"""
dedicated model based permissions to optimize performance

For more information on this file, see
https://django-guardian.readthedocs.io/en/v2.3.0/userguide/performance.html#direct-foreign-keys

Guardian stores an object permission of *any* model in one table and names the
object by ``content_type`` and the text of its primary key. A lookup for a model
whose primary key is a uuid compares that text column by casting it to a uuid,
and whether the plan evaluates the cast only for the rows of the looked up model
or for the rows of every other model in the table is its own decision: one row of
a model with an integer primary key can make the lookup of a service fail with
``invalid input syntax for type uuid``.

A model with a table of its own is answered from that table and its permissions
never take part in such a cast, so every model the permission bootstrap of
``accounts.signals`` grants something on has one here: an organization, the
groups an organization administers and - in ``registry`` - the services.
"""
from accounts.models.groups import Organization
from django.contrib.auth.models import Group
from django.db import models

from guardian.models import GroupObjectPermissionBase, UserObjectPermissionBase


class OrganizationUserObjectPermission(UserObjectPermissionBase):
    # an Organization is a Group, so the reverse accessor of the base class'
    # "user"/"group" key and the one of this key would land on the same model
    # under the same name (fields.E304)
    content_object = models.ForeignKey(
        to=Organization, on_delete=models.CASCADE,
        related_name="user_object_permissions")


class OrganizationGroupObjectPermission(GroupObjectPermissionBase):
    content_object = models.ForeignKey(
        to=Organization, on_delete=models.CASCADE,
        related_name="group_object_permissions")


class GroupUserObjectPermission(UserObjectPermissionBase):
    # the names of the accessors above are inherited by an Organization, which
    # is a Group, so the tables of a plain group name them differently
    content_object = models.ForeignKey(
        to=Group, on_delete=models.CASCADE,
        related_name="granted_user_object_permissions")


class GroupGroupObjectPermission(GroupObjectPermissionBase):
    content_object = models.ForeignKey(
        to=Group, on_delete=models.CASCADE,
        related_name="granted_group_object_permissions")
