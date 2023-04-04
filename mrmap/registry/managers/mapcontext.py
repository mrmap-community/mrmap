from django.db import models
from extras.managers import DefaultHistoryManager


class MapContextManager(DefaultHistoryManager, models.Manager):
    pass


class MapContextLayerManager(DefaultHistoryManager, models.Manager):
    pass
