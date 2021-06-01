from django.db import models
from django.db.models import F


class PendingTaskManager(models.Manager):

    def get_queryset(self):
        return super().get_queryset().annotate(execution_time=F("done_at")-F("started_at"))

