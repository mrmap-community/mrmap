"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 05.05.20

"""
import uuid
from django.db import models

# Create your models here.
from service.models import Service


class HarvestResult(models.Model):
    id = models.UUIDField(default=uuid.uuid4, primary_key=True)
    service = models.ForeignKey(Service, on_delete=models.CASCADE)
    timestamp_start = models.DateTimeField(blank=True, null=True)
    timestamp_end = models.DateTimeField(blank=True, null=True)
    number_results = models.IntegerField(blank=True, null=True)
    created = models.DateTimeField(auto_now_add=True, null=True)

    def __str__(self):
        return "Harvest Result ({})".format(self.service.metadata.title)
