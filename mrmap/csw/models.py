"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 05.05.20

"""
import uuid

from django.conf import settings
from django.db import models, transaction

from main.models import CommonInfo
from service.models import Metadata


class HarvestResult(CommonInfo):
    id = models.UUIDField(default=uuid.uuid4, primary_key=True)
    metadata = models.ForeignKey(Metadata, on_delete=models.CASCADE, related_name='harvest_results')
    timestamp_start = models.DateTimeField(blank=True, null=True)
    timestamp_end = models.DateTimeField(blank=True, null=True)
    number_results = models.IntegerField(blank=True, null=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return "Harvest Result ({})".format(self.metadata.title)

    def save(self, *args, **kwargs):
        adding = self._state.adding
        super().save(*args, **kwargs)
        if adding:
            from csw.tasks import async_harvest
            transaction.on_commit(lambda: async_harvest.apply_async(args=(self.metadata.owned_by_org.pk if self.metadata.owned_by_org else None,
                                                                          self.pk, ),
                                                                    kwargs={'created_by_user_pk': self.created_by_user.pk},
                                                                    countdown=settings.CELERY_DEFAULT_COUNTDOWN))
