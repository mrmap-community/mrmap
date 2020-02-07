from django.contrib.gis.db import models


class MonitoringSetting(models.Model):
    metadatas = models.ManyToManyField('service.Metadata', related_name='monitoring_setting')
    interval = models.DurationField()
    timeout = models.IntegerField()


class MonitoringResult(models.Model):
    monitoring_successful = models.BooleanField(null=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    metadata = models.ForeignKey('service.Metadata', on_delete=models.CASCADE)
    needs_update = models.BooleanField(null=True, blank=True)
    error_msg = models.TextField(null=True, blank=True)
    duration = models.DurationField(null=True, blank=True)
    diff = models.TextField(null=True, blank=True)
