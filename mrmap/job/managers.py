from django.db import models
from django.db.models import F
from django.db.models import Avg, Max, Min


class TaskManager(models.Manager):

    def get_stats(self):
        self.get_queryset().aggregate(Avg('execution_time'), Max('execution_time'), Min('execution_time'))

    def get_queryset(self):
        return super().get_queryset().annotate(execution_time=F("done_at")-F("started_at"))

