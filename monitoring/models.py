from django.contrib.gis.db import models

from service.models import Metadata


class MonitoringSetting(models.Model):
    metadatas = models.ManyToManyField(Metadata, related_name='monitoring_setting')
    interval = models.DurationField()
    timeout = models.IntegerField()


class MonitoringResult(models.Model):
    timestamp = models.DateTimeField(auto_now_add=True)
    metadata = models.ForeignKey(Metadata)
    needs_update = models.BooleanField(null=True, blank=True)
    error_msg = models.TextField(null=True, blank=True)
    duration = models.DurationField(null=True, blank=True)
    diff = models.TextField(null=True, blank=True)
