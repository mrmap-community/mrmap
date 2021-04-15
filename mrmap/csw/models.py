"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 05.05.20

"""
import uuid

from django.conf import settings
from django.db import models, transaction
from service.models import Metadata


class HarvestResult(models.Model):
    id = models.UUIDField(default=uuid.uuid4, primary_key=True)
    metadata = models.ForeignKey(Metadata, on_delete=models.CASCADE, related_name='harvest_results')
    timestamp_start = models.DateTimeField(blank=True, null=True)
    timestamp_end = models.DateTimeField(blank=True, null=True)
    number_results = models.IntegerField(blank=True, null=True)
    created = models.DateTimeField(auto_now_add=True, null=True)

    def __str__(self):
        return "Harvest Result ({})".format(self.metadata.title)

    def save(self, *args, **kwargs):
        if self._state.adding:
            from csw.tasks import async_harvest
            transaction.on_commit(lambda: async_harvest.apply_async(args=(self.pk, ), countdown=settings.CELERY_DEFAULT_COUNTDOWN))
        super().save(*args, **kwargs)
