import logging

from celery import shared_task
from django.core.cache import cache

logger = logging.getLogger(__name__)


@shared_task(
    queue="default",
    bind=True,
)
def refresh_materialized_views(self, *args, **kwargs):
    from registry.models.materialized_views import (
        MaterializedHarvestingStatsPerDay, SearchableDatasetMetadataRecord,
        SearchableServiceMetadataRecord)

    lock_id = "refresh_materialized_views"
    if not cache.add(lock_id, self.request.id, timeout=300):
        logger.info(
            "refresh_materialized_views skipped: another instance is running")
        return "there is a running task: skip"
    try:
        SearchableDatasetMetadataRecord.refresh()
        SearchableServiceMetadataRecord.refresh()
        MaterializedHarvestingStatsPerDay.refresh()
        return "materialized views refreshed."
    finally:
        cache.delete(lock_id)
