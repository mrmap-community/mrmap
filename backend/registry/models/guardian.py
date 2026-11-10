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

A model with a table of its own is answered from that table and never takes part
in such a cast. The models whose object permissions the code or the fixtures of
MrMap write have one here or in ``accounts/models/guardian.py``:

* the services: the permission bootstrap of ``accounts.signals`` grants on the
  two kinds it secures, and the reads which scope by permission look all three
  kinds up per kind - ``registry.querys.alerts.collect_service_alerts`` and the
  background activity in ``notify/managers.py``. A lookup takes the cast whether
  or not the model was ever granted anything, so the catalogue has its tables
  too, although no code grants on it today;
* the map applications and their layers, and the monitoring setting of a web map
  service: the fixtures of this repository write their grants, and their primary
  keys are integers - the shape which breaks the lookup of a service, so these
  have their tables before anything grants on them in code.

The organizations and the groups the bootstrap also grants on - all of them of an
integer primary key - are in ``accounts/models/guardian.py``. What is left are the
models whose permissions nothing writes today, like the ``User`` of
``accounts.models.users.User.assign_object_perms``: named by a uuid, their rows in
the shared table are readable for every lookup, so they answer generically until
the role work needs a table. The guard which watches the whole set is #735.
"""
from django.db import models
from registry.models.mapcontext import MapContext, MapContextLayer
from registry.models.monitoring import WebMapServiceMonitoringSetting
from registry.models.service import (CatalogueService, WebFeatureService,
                                     WebMapService)

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


# The catalogue is no secured model and nothing grants on it today, but both
# reads which scope by permission ask it as one kind of service:
# `registry.querys.alerts.collect_service_alerts` and the visibility of the
# background activity in `notify/managers.py`. Answered from the shared table,
# those lookups cast its text column whether or not the catalogue has ever been
# granted to anybody.
class CatalogueServiceUserObjectPermission(UserObjectPermissionBase):
    content_object = models.ForeignKey(
        to=CatalogueService, on_delete=models.CASCADE)


class CatalogueServiceGroupObjectPermission(GroupObjectPermissionBase):
    content_object = models.ForeignKey(
        to=CatalogueService, on_delete=models.CASCADE)


# An object permission of these three models is written by the fixtures of this
# repository today - ``registry/fixtures/test_mapcontext.json`` and
# ``registry/fixtures/test_monitoring.json`` - which name their integer primary
# keys in the shared table. Their own tables keep those rows out of the cast a
# lookup of a service takes, for a fixture as well as for the code which will
# grant on them later.
class MapContextUserObjectPermission(UserObjectPermissionBase):
    content_object = models.ForeignKey(
        to=MapContext, on_delete=models.CASCADE)


class MapContextGroupObjectPermission(GroupObjectPermissionBase):
    content_object = models.ForeignKey(
        to=MapContext, on_delete=models.CASCADE)


class MapContextLayerUserObjectPermission(UserObjectPermissionBase):
    content_object = models.ForeignKey(
        to=MapContextLayer, on_delete=models.CASCADE)


class MapContextLayerGroupObjectPermission(GroupObjectPermissionBase):
    content_object = models.ForeignKey(
        to=MapContextLayer, on_delete=models.CASCADE)


class WebMapServiceMonitoringSettingUserObjectPermission(
        UserObjectPermissionBase):
    content_object = models.ForeignKey(
        to=WebMapServiceMonitoringSetting, on_delete=models.CASCADE)


class WebMapServiceMonitoringSettingGroupObjectPermission(
        GroupObjectPermissionBase):
    content_object = models.ForeignKey(
        to=WebMapServiceMonitoringSetting, on_delete=models.CASCADE)
