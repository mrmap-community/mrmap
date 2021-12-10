from django.db import models
from extras.models import CommonInfo
from registry.serializers.jobs import TaskResultSerializer


class CollectRemoteMetadataJob(CommonInfo):
    celery_tasks = models.ManyToManyField(to=TaskResultSerializer)
