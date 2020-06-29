"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 28.05.19

"""
import uuid

from django.db import models

from service.models import Metadata
from structure.models import MrMapUser


class Subscription(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    metadata = models.ForeignKey(Metadata, on_delete=models.CASCADE)
    user = models.ForeignKey(MrMapUser, on_delete=models.CASCADE)
    notify_on_update = models.BooleanField(default=True)
    notify_on_metadata_edit = models.BooleanField(default=True)
    notify_on_access_edit = models.BooleanField(default=True)
    created_on = models.DateTimeField(auto_now_add=True)
