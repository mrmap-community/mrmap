from django.db import models
from django.db.models import OuterRef

from registry.models import DatasetMetadata


class ConformityCheckConfigurationManager(models.Manager):
    """ Custom manager to extend ConformityCheckConfiguration methods """

    def get_for_metadata_type(self, metadata_type: str):
        """ Gets all configs that are allowed for the given metadata_type """
        return super().get_queryset().filter(
            metadata_types__contains=metadata_type)


class ConformityCheckRunManager(models.Manager):
    """ Custom manager to extend ConformityCheckRun methods """

    def has_running_check(self, metadata: DatasetMetadata):
        """ Checks if the given metadata object has a non-finished
        ConformityCheckRun.

            Returns:
                True, if a non-finished ConformityCheckRun was found,
                false otherwise.
        """
        running_checks = super().get_queryset().filter(
            metadata=metadata, passed__isnull=True).count()
        return running_checks != 0

    def get_latest_check(self, metadata):
        from quality.models import ConformityCheckRun
        try:
            return super().get_queryset().filter(metadata=metadata).latest()
        except ConformityCheckRun.DoesNotExist:
            return None

    def get_total_check_count(self, metadata):
        from quality.models import ConformityCheckRun
        try:
            return super().get_queryset().filter(metadata=metadata).count()
        except ConformityCheckRun.DoesNotExist:
            return None
