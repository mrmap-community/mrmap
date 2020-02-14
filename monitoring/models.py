from django.contrib.gis.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver

from service.models import Metadata


class MonitoringSetting(models.Model):
    metadatas = models.ManyToManyField('service.Metadata', related_name='monitoring_setting')
    interval = models.DurationField()
    timeout = models.IntegerField()


@receiver(post_save, sender=Metadata)
def add_to_setting_on_metadata_create(created=False, instance=None, **kwargs):
    if created:
        # NOTE: Since we do not have a clear handling for which setting to use, always use first (default) setting.
        monitoring_setting = MonitoringSetting.objects.first()
        monitoring_setting.metadatas.add(instance)
        monitoring_setting.save()


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
