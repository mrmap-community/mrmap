from celery import shared_task
from celery.utils.log import get_task_logger

logger = get_task_logger(__name__)


@shared_task(
    queue="default",
)
def refresh_materialized_views(*args, **kwargs):
    from registry.models.materialized_views import (
        MaterializedHarvestingStatsPerDay, SearchableDatasetMetadataRecord,
        SearchableServiceMetadataRecord)
    SearchableDatasetMetadataRecord.refresh()
    SearchableServiceMetadataRecord.refresh()
    MaterializedHarvestingStatsPerDay.refresh()
