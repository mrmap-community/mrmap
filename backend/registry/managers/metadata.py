from logging import Logger
from django.conf import settings
from django.db import models
from registry.querys.metadata import (MetadataRelationQuerySet,
                                      TimeExtentQuerySet)
from extras.managers import UniqueConstraintDefaultValueManager


logger: Logger = settings.ROOT_LOGGER


class KeywordManager(models.Manager):
    """Needed to insert fixtures without pk by there natural key attribute"""

    def get_by_natural_key(self, keyword):
        return self.get(keyword=keyword)


class DatasetMetadataRecordManager(UniqueConstraintDefaultValueManager):
    """The manager of the dataset metadata records.

    It asked the searchable projection of the records to be refreshed after every bulk
    write, which the harvest of a catalogue did on every document. The searchable
    representation of a record is a column of the record since #854, so there is
    nothing left to refresh and nothing left here but the behaviour of the base.
    """


class ServiceMetadataRecordManager(UniqueConstraintDefaultValueManager):
    # see DatasetMetadataRecordManager
    pass


class TimeExtentManager(models.Manager):

    def get_queryset(self):
        return TimeExtentQuerySet(self.model, using=self._db)

    def with_effective_timerange(self):
        return self.get_queryset().with_effective_timerange()


class MetadataRelationManager(models.Manager):
    """ Manager which exposes the coupling policy of MrMap, see
        :class:`registry.querys.metadata.MetadataRelationQuerySet`.
    """

    def get_queryset(self):
        return MetadataRelationQuerySet(self.model, using=self._db)

    def imported_evidence(self):
        return self.get_queryset().imported_evidence()

    def local_only(self):
        return self.get_queryset().local_only()

    def publishable(self):
        return self.get_queryset().publishable()
