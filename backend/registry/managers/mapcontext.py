from django.db import models
from django.db.models.functions import Coalesce
from extras.managers import DefaultHistoryManager
from mptt.managers import TreeManager


class MapContextManager(DefaultHistoryManager, models.Manager):

    def with_meta(self):
        return self.annotate(
            map_context_layer_count=Coalesce(
                models.Count("map_context_layer"), 0),
        )


class MapContextLayerManager(DefaultHistoryManager, TreeManager):
    pass
