from django.db import models
from django.db.models import F


class PendingTaskManager(models.Manager):

    def with_execution_time(self):
        return self.get_queryset().annotate(execution_time=F("done_at")-F("started_at"))

