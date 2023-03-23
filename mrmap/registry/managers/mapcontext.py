from django.db import models
from extras.managers import DefaultHistoryManager
from mptt.managers import TreeManager


class MapContextManager(DefaultHistoryManager, models.Manager):
    pass


class MapContextLayerManager(DefaultHistoryManager, TreeManager):
    pass
