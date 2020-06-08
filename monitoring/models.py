"""
Author: Jan Suleiman
Organization: terrestris GmbH & Co. KG, Bonn, Germany
Contact: suleiman@terrestris.de
Created on: 26.02.2020

"""

from django.contrib.gis.db import models
from django_celery_beat.models import PeriodicTask


class MonitoringSetting(models.Model):
    metadatas = models.ManyToManyField('service.Metadata', related_name='monitoring_setting')
    interval = models.DurationField()
    timeout = models.IntegerField()
    periodic_task = models.OneToOneField(PeriodicTask, on_delete=models.CASCADE, null=True, blank=True)


class MonitoringRun(models.Model):
    start = models.DateTimeField(auto_now_add=True)
    end = models.DateTimeField(null=True, blank=True)
    duration = models.DurationField(null=True, blank=True)


class Monitoring(models.Model):
    metadata = models.ForeignKey('service.Metadata', on_delete=models.CASCADE)
    timestamp = models.DateTimeField(auto_now_add=True)
    duration = models.DurationField(null=True, blank=True)
    status_code = models.IntegerField(null=True, blank=True)
    error_msg = models.TextField(null=True, blank=True)
    available = models.BooleanField(null=True)
    monitored_uri = models.CharField(max_length=2000)
    monitoring_run = models.ForeignKey(MonitoringRun, on_delete=models.CASCADE)


class MonitoringCapability(Monitoring):
    needs_update = models.BooleanField(null=True, blank=True)
    diff = models.TextField(null=True, blank=True)
