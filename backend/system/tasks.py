import logging

from celery import shared_task
from extras.tasks import SingletonTask

logger = logging.getLogger(__name__)


@shared_task(
    queue="default",
    bind=True,
    base=SingletonTask,
)
def refresh_materialized_views(self, *args, **kwargs):
    from registry.models.materialized_views import (
        MaterializedHarvestingStatsPerDay, SearchableDatasetMetadataRecord,
        SearchableServiceMetadataRecord)

    SearchableDatasetMetadataRecord.refresh()
    SearchableServiceMetadataRecord.refresh()
    MaterializedHarvestingStatsPerDay.refresh()
    return "materialized views refreshed."
