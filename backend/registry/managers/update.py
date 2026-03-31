from django.db import models


class LayerMappingQuerySet(models.QuerySet):

    def unmatched_layers(self):
        return self.filter(old_layer__isnull=True)

    def auto_matched_but_unconfirmed(self):
        return self.filter(is_confirmed=False, old_layer__isnull=False)

    def is_autoupdate_able(self, service):
        qs = self.filter(old_layer__service=service)
        return not qs.filter(old_layer__isnull=True).exists()


class LayerMappingManager(models.Manager.from_queryset(LayerMappingQuerySet)):
    pass
