"""The nine statistics materialized views are dropped (#857).

Every one of these views answered the same question for one resource: how many
of its records were created, changed and deleted on a day. That answer is one
aggregation over the audit records of the resource, and since #856 the day of a
record and the number of fields it differs in from its predecessor are columns
of the audit row itself -- so the aggregation is a single pass over a table
which is indexed on exactly that day, and the endpoints of
``registry/views/statistical.py`` answer it themselves now. What a view added
was a rebuild: a scheduled task refreshed all nine every few minutes, a change
had to wait for that rebuild to show up in the statistics, and a busy harvest
made the database rewrite these aggregations over and over.

The views are dropped here instead of being left behind, and the way back
answers their statement itself, for the same reason the searchable projections
were dropped that way (see migration ``0023``): a view is not part of the
migration state -- django-pgviews creates it from the model, see
``system.apps.sync_pg_views_if_missing`` -- and the models which answered these
are gone from the code, so the hook which watches for missing views cannot help
on the way back. The statements below are the ones the models of the previous
revision answered, taken from ``pg_matviews`` of a migrated database, which is
what a deployment rolling back this migration finds again. The indexes of a view
are not recreated with it; ``manage.py sync_pgviews --force`` creates those from
the models a rolled back deployment checks out.
"""

import django_pgviews.db.migrations.operations
from django.db import migrations

# the statement the per-day statistics view of one resource answered: the
# aggregation over its audit records. The day is answered twice, once as the
# grouping column and once as the id of the row, because the frontend charts
# order and label their axis by the id of a statistics row. An audit row without
# a predecessor is not an update but the first thing known about a record, which
# is why it counts as new (#856).
CREATE_PER_DAY_VIEW = """
CREATE MATERIALIZED VIEW %(view)s AS
 SELECT history_day,
    history_day AS id,
    count(history_id) FILTER (WHERE (((history_type)::text = '+'::text) OR ((delta_size IS NULL) AND ((history_type)::text = '~'::text)))) AS new,
    count(history_id) FILTER (WHERE ((history_type)::text = '-'::text)) AS deleted,
    count(history_id) FILTER (WHERE ((delta_size > 0) AND ((history_type)::text = '~'::text))) AS updated
   FROM %(history)s
  WHERE (((history_type)::text = '+'::text) OR ((history_type)::text = '-'::text) OR ((delta_size > 0) AND ((history_type)::text = '~'::text)) OR ((delta_size IS NULL) AND ((history_type)::text = '~'::text)))
  GROUP BY history_day
  ORDER BY history_day
WITH DATA;
"""

# the same aggregation of layers, grouped by the service a layer belongs to,
# which is what the change chart of one service asks for
CREATE_LAYER_PER_SERVICE_VIEW = """
CREATE MATERIALIZED VIEW registry_materializedlayerstatsperdayandservice AS
 SELECT history_day,
    service_id AS service,
    history_day AS id,
    count(history_id) FILTER (WHERE (((history_type)::text = '+'::text) OR ((delta_size IS NULL) AND ((history_type)::text = '~'::text)))) AS new,
    count(history_id) FILTER (WHERE ((history_type)::text = '-'::text)) AS deleted,
    count(history_id) FILTER (WHERE ((delta_size > 0) AND ((history_type)::text = '~'::text))) AS updated
   FROM registry_historicallayer
  WHERE (((history_type)::text = '+'::text) OR ((history_type)::text = '-'::text) OR ((delta_size > 0) AND ((history_type)::text = '~'::text)) OR ((delta_size IS NULL) AND ((history_type)::text = '~'::text)))
  GROUP BY history_day, service_id
  ORDER BY history_day, service_id
WITH DATA;
"""

# what a harvesting job found on a day is not an audit record but the relation
# it wrote, so this one aggregated the relation table joined to its job -- the
# service of a harvested record is the service of the job which harvested it
CREATE_HARVESTING_VIEW = """
CREATE MATERIALIZED VIEW registry_materializedharvestingstatsperday AS
 SELECT registry_harvestedmetadatarelation.history_day,
    registry_harvestedmetadatarelation.collecting_state,
    registry_harvestedmetadatarelation.harvesting_job_id AS harvesting_job,
    registry_harvestingjob.service_id AS harvesting_job__service,
    registry_harvestedmetadatarelation.history_day AS id,
    count(registry_harvestedmetadatarelation.id) FILTER (WHERE (registry_harvestedmetadatarelation.collecting_state = 1)) AS new,
    count(registry_harvestedmetadatarelation.id) FILTER (WHERE (registry_harvestedmetadatarelation.collecting_state = 2)) AS updated,
    count(registry_harvestedmetadatarelation.id) FILTER (WHERE (registry_harvestedmetadatarelation.collecting_state = 3)) AS existed,
    registry_harvestingjob.service_id AS service
   FROM (registry_harvestedmetadatarelation
     JOIN registry_harvestingjob ON ((registry_harvestedmetadatarelation.harvesting_job_id = registry_harvestingjob.id)))
  GROUP BY registry_harvestedmetadatarelation.history_day, registry_harvestedmetadatarelation.collecting_state, registry_harvestedmetadatarelation.harvesting_job_id, registry_harvestingjob.service_id
WITH DATA;
"""

# the seven resources whose per-day statistics had a view of their own, with the
# audit table that view aggregated
PER_DAY_STATISTICS_VIEWS = {
    "registry_materializedcatalogueservicestatsperday":
        "registry_historicalcatalogueservice",
    "registry_materializeddatasetmetadatarecordstatsperday":
        "registry_historicaldatasetmetadatarecord",
    "registry_materializedfeaturetypestatsperday":
        "registry_historicalfeaturetype",
    "registry_materializedlayerstatsperday":
        "registry_historicallayer",
    "registry_materializedservicemetadatarecordstatsperday":
        "registry_historicalservicemetadatarecord",
    "registry_materializedwebfeatureservicestatsperday":
        "registry_historicalwebfeatureservice",
    "registry_materializedwebmapservicestatsperday":
        "registry_historicalwebmapservice",
}

# the way forward removes the nine relations of the previous revision, the way
# back creates them again with the data of the deployment it rolls back to
DROP_VIEWS = [
    'DROP MATERIALIZED VIEW IF EXISTS "%s";' % view
    for view in PER_DAY_STATISTICS_VIEWS
] + [
    'DROP MATERIALIZED VIEW IF EXISTS "registry_materializedlayerstatsperdayandservice";',
    'DROP MATERIALIZED VIEW IF EXISTS "registry_materializedharvestingstatsperday";',
]

CREATE_VIEWS = [
    CREATE_PER_DAY_VIEW % {"view": view, "history": history}
    for view, history in PER_DAY_STATISTICS_VIEWS.items()
] + [CREATE_LAYER_PER_SERVICE_VIEW, CREATE_HARVESTING_VIEW]


class Migration(migrations.Migration):

    dependencies = [
        ('registry', '0025_history_records_know_their_own_diff_size'),
    ]

    operations = [
        # a statistics view is a model which is not managed: its relation is not
        # Django's, so Django's DeleteModel would drop it with DROP TABLE --
        # which postgres refuses for a materialized view. The state of the nine
        # models and of the bookkeeping django-pgviews keeps for its views goes
        # here, the statement which removes the relations themselves comes from
        # below.
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.DeleteModel(
                    name='MaterializedCatalogueServiceStatsPerDay',
                ),
                migrations.DeleteModel(
                    name='MaterializedDatasetMetadataRecordStatsPerDay',
                ),
                migrations.DeleteModel(
                    name='MaterializedFeatureTypeStatsPerDay',
                ),
                migrations.DeleteModel(
                    name='MaterializedLayerStatsPerDay',
                ),
                migrations.DeleteModel(
                    name='MaterializedServiceMetadataRecordStatsPerDay',
                ),
                migrations.DeleteModel(
                    name='MaterializedWebFeatureServiceStatsPerDay',
                ),
                migrations.DeleteModel(
                    name='MaterializedWebMapServiceStatsPerDay',
                ),
                migrations.DeleteModel(
                    name='MaterializedLayerStatsPerDayAndService',
                ),
                migrations.DeleteModel(
                    name='MaterializedHarvestingStatsPerDay',
                ),
                django_pgviews.db.migrations.operations.DeleteViewOperation(
                    name='MaterializedCatalogueServiceStatsPerDay',
                    materialized=True,
                    db_name='registry_materializedcatalogueservicestatsperday',
                ),
                django_pgviews.db.migrations.operations.DeleteViewOperation(
                    name='MaterializedDatasetMetadataRecordStatsPerDay',
                    materialized=True,
                    db_name='registry_materializeddatasetmetadatarecordstatsperday',
                ),
                django_pgviews.db.migrations.operations.DeleteViewOperation(
                    name='MaterializedFeatureTypeStatsPerDay',
                    materialized=True,
                    db_name='registry_materializedfeaturetypestatsperday',
                ),
                django_pgviews.db.migrations.operations.DeleteViewOperation(
                    name='MaterializedLayerStatsPerDay',
                    materialized=True,
                    db_name='registry_materializedlayerstatsperday',
                ),
                django_pgviews.db.migrations.operations.DeleteViewOperation(
                    name='MaterializedServiceMetadataRecordStatsPerDay',
                    materialized=True,
                    db_name='registry_materializedservicemetadatarecordstatsperday',
                ),
                django_pgviews.db.migrations.operations.DeleteViewOperation(
                    name='MaterializedWebFeatureServiceStatsPerDay',
                    materialized=True,
                    db_name='registry_materializedwebfeatureservicestatsperday',
                ),
                django_pgviews.db.migrations.operations.DeleteViewOperation(
                    name='MaterializedWebMapServiceStatsPerDay',
                    materialized=True,
                    db_name='registry_materializedwebmapservicestatsperday',
                ),
                django_pgviews.db.migrations.operations.DeleteViewOperation(
                    name='MaterializedLayerStatsPerDayAndService',
                    materialized=True,
                    db_name='registry_materializedlayerstatsperdayandservice',
                ),
                django_pgviews.db.migrations.operations.DeleteViewOperation(
                    name='MaterializedHarvestingStatsPerDay',
                    materialized=True,
                    db_name='registry_materializedharvestingstatsperday',
                ),
            ],
            database_operations=[
                migrations.RunSQL(DROP_VIEWS, CREATE_VIEWS),
            ],
        ),
    ]
