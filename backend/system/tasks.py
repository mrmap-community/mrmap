import logging

from celery import shared_task
from extras.tasks import SingletonTask
from registry.models.materialized_views import (
    MaterializedCatalogueServiceStatsPerDay,
    MaterializedDatasetMetadataRecordStatsPerDay,
    MaterializedFeatureTypeStatsPerDay, MaterializedLayerStatsPerDay,
    MaterializedServiceMetadataRecordStatsPerDay,
    MaterializedWebFeatureServiceStatsPerDay,
    MaterializedWebMapServiceStatsPerDay)

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

    MaterializedDatasetMetadataRecordStatsPerDay.refresh()
    MaterializedCatalogueServiceStatsPerDay.refresh()
    MaterializedFeatureTypeStatsPerDay.refresh()
    MaterializedLayerStatsPerDay.refresh()
    MaterializedServiceMetadataRecordStatsPerDay.refresh()
    MaterializedWebFeatureServiceStatsPerDay.refresh()
    MaterializedWebMapServiceStatsPerDay.refresh()

    return "materialized views refreshed."
