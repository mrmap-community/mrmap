from django.db import models
from django.db.models.functions import Coalesce


class MapContextManager(models.Manager):

    def with_meta(self):
        return self.annotate(
            map_context_layer_count=Coalesce(
                models.Count("map_context_layer"), 0),
        )
