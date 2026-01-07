from logging import Logger
from django.conf import settings
from django.db import models
from registry.querys.metadata import TimeExtentQuerySet
from extras.managers import UniqueConstraintDefaultValueManager


logger: Logger = settings.ROOT_LOGGER


class KeywordManager(models.Manager):
    """Needed to insert fixtures without pk by there natural key attribute"""

    def get_by_natural_key(self, keyword):
        return self.get(keyword=keyword)


class DatasetMetadataRecordManager(UniqueConstraintDefaultValueManager):

    def bulk_create(self, *args, **kwargs):
        from registry.models.materialized_views import \
            SearchableDatasetMetadataRecord
        objs = super().bulk_create(*args, **kwargs)
        SearchableDatasetMetadataRecord.refresh()
        return objs

    def bulk_update(self, *args, **kwargs) -> int:
        objs = super().bulk_update(*args, **kwargs)
        from registry.models.materialized_views import \
            SearchableDatasetMetadataRecord
        SearchableDatasetMetadataRecord.refresh()
        return objs


class ServiceMetadataRecordManager(UniqueConstraintDefaultValueManager):

    def bulk_create(self, *args, **kwargs):
        objs = super().bulk_create(*args, **kwargs)
        from registry.models.materialized_views import \
            SearchableServiceMetadataRecord
        SearchableServiceMetadataRecord.refresh()
        return objs

    def bulk_update(self, *args, **kwargs) -> int:
        objs = super().bulk_update(*args, **kwargs)
        from registry.models.materialized_views import \
            SearchableServiceMetadataRecord
        SearchableServiceMetadataRecord.refresh()
        return objs


class TimeExtentManager(models.Manager):

    def get_queryset(self):
        return TimeExtentQuerySet(self.model, using=self._db)

    def with_effective_timerange(self):
        return self.get_queryset().with_effective_timerange()
