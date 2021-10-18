from django.db import models


class MapContextManager(models.Manager):

    def get_queryset(self):
        return super().get_queryset()


class MapContextLayerManager(models.Manager):

    def get_queryset(self):
        return super().get_queryset()
