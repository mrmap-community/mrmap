from django.db import models
from extras.managers import DefaultHistoryManager
from treebeard.ns_tree import NS_NodeManager as NestedSetNodeManager


class MapContextManager(DefaultHistoryManager, models.Manager):
    pass


class MapContextLayerManager(DefaultHistoryManager, NestedSetNodeManager):
    pass
