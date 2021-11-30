from django.db import models
from django.utils.translation import gettext_lazy as _
from extras.models import CommonInfo
from registry.api.serializers.jobs import TaskResultSerializer


class CollectRemoteMetadataJob(CommonInfo):
    celery_tasks = models.ManyToManyField(to=TaskResultSerializer)
    pass
