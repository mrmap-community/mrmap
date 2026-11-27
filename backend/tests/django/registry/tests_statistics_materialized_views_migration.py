"""The statistics materialized views around the rebuilt history (#857, #1850).

The nine views of #857 answered the per-day statistics of a resource; the
endpoints answer the same aggregation over the audit records themselves since
that issue. A view is not part of the migration state -- django-pgviews used to
create it from its model -- and its models and startup hook are gone. The drop
node of the old chain carried the statement of both directions itself, and this
test asked the migration executor for that statement by travelling back to the
revision the views still existed at.

The rebuilt history (#1850) creates the final schema from the models and never
had a node at which one of these views stood, so there is no name of it left to
travel to. What the class proves has survived that and reads off both states:

* the end state -- the final schema of the rebuilt chain answers no statistics
  view at all, and the attention of the services is answered by the stored
  ``ServiceAlert`` relation, so the view of its predecessor is gone as well;
* the statement of the way back -- the create statements of the nine views are
  carried here exactly as the drop node of the old chain carried them, the test
  builds the intermediate state with them itself, and asks what it asked
  before: all nine stand, and the layer aggregations answer the audit rows they
  aggregate, with data. The statements read the audit relations of the live
  schema, so a column taken from under the aggregation -- the same columns the
  statistics endpoints aggregate over -- goes red here.
"""

from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase
from mptt2.models import Tree

from registry.models.alerts import ServiceAlert
from registry.models.service import Layer

#: the migration of the rebuilt chain which creates the schema this class
#: reads off; the plan around it is what the tests run on
INITIAL = ("registry", "0001_initial")

#: the nine views the statistics endpoints used to be answered from
STATISTICS_VIEWS = (
    "registry_materializedcatalogueservicestatsperday",
    "registry_materializeddatasetmetadatarecordstatsperday",
    "registry_materializedfeaturetypestatsperday",
    "registry_materializedlayerstatsperday",
    "registry_materializedservicemetadatarecordstatsperday",
    "registry_materializedwebfeatureservicestatsperday",
    "registry_materializedwebmapservicestatsperday",
    "registry_materializedlayerstatsperdayandservice",
    "registry_materializedharvestingstatsperday",
)

# the statements which the drop node of the old chain carried for the way
# back, verbatim: an audit row without a predecessor is not an update but the
# first thing known about a record, which is why it counts as new (#856), and
# the day is answered twice, once as the grouping column and once as the id of
# the row, because the frontend charts order and label their axis by the id of
# a statistics row
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

# the seven resources whose per-day statistics had a view of their own, with
# the audit table that view aggregated
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

# the statements of the way back in full: the seven per-day aggregations
# beside the layer aggregation of one service and the harvesting aggregation
CREATE_STATISTICS_VIEWS = [
    CREATE_PER_DAY_VIEW % {"view": view, "history": history}
    for view, history in PER_DAY_STATISTICS_VIEWS.items()
] + [CREATE_LAYER_PER_SERVICE_VIEW, CREATE_HARVESTING_VIEW]

WMS = UUID("cd16cc1f-3abb-4625-bb96-fbe80dbe23e3")

DAY = datetime(2026, 1, 1, 12, tzinfo=timezone.utc)


class StatisticsViewsMigrationTest(TestCase):
    """The end state of the rebuilt chain and the statement of the way back.

    ``TransactionTestCase`` was needed while this class rolled the migration
    executor back over the drop node of the old chain; nothing migrates any
    more -- the intermediate state is plain sql inside the transaction of the
    test, which postgres rolls back with it.
    """

    fixtures = ["test_users.json", "test_keywords.json", "test_crs.json",
                "test_wms.json"]

    def setUp(self):
        # the layers of the fixtures are not what this test writes its counts of
        Layer.change_log.model.objects.all().delete()
        self.layers = (first, second) = uuid4(), uuid4()
        self.trees = {layer: Tree.objects.create() for layer in self.layers}
        for index, (layer, change, title) in enumerate((
            (first, '+', 'Wasserversorgung'),
            (second, '+', 'Bodenrichtwerte'),
            (first, '~', 'Wasserversorgung NRW'),
            (second, '-', 'Bodenrichtwerte'),
        )):
            self.audit_row(layer, change, title, index)

        self.assert_rebuilt_chain_end_state()
        self.create_statistics_views()

    def audit_row(self, layer, history_type, title, index):
        """One audit row of a layer, written the way a saved layer writes it.

        Its moment is the moment it was written, minute by minute apart: a record
        is only compared against the row whose moment is in front of its own, and
        two rows of one record which answer the same second have no order the
        database could tell apart.
        """
        return Layer.change_log.model.objects.create(
            id=layer, history_relation_id=layer, service_id=WMS,
            mptt_tree=self.trees[layer], mptt_lft=1, mptt_rgt=2, mptt_depth=0,
            file_identifier=str(layer), title=title,
            history_type=history_type,
            history_date=DAY + timedelta(minutes=index))

    def assert_rebuilt_chain_end_state(self):
        """The plan of the rebuilt chain resolves and answers no view.

        The end state the chain owes: the statistics views were dropped
        (#857) before the rebuild, and the rebuild carried no node which
        creates them -- the test database, migrated to the leaf, is the
        deployment this reads off.
        """
        plan = MigrationExecutor(connection).loader.graph.forwards_plan(
            INITIAL)
        self.assertIn(INITIAL, plan)
        self.assertEqual(self.materialized_views(), [])

    @staticmethod
    def create_statistics_views():
        """The intermediate state of the way back, as the drop node made it.

        The node itself is gone from the rebuilt chain, so its statements
        stand in for it here; with them the state the executor used to
        migrate back into is what the test builds.
        """
        with connection.cursor() as cursor:
            for statement in CREATE_STATISTICS_VIEWS:
                cursor.execute(statement)

    @staticmethod
    def drop_statistics_views():
        """The way forward of the drop node: the nine relations removed."""
        with connection.cursor() as cursor:
            for view in STATISTICS_VIEWS:
                cursor.execute(
                    'DROP MATERIALIZED VIEW IF EXISTS "%s";' % view)

    @staticmethod
    def materialized_views():
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT matviewname FROM pg_matviews WHERE schemaname = 'public'")
            return sorted(row[0] for row in cursor.fetchall())

    @staticmethod
    def rows_of(view, *columns):
        """Every row of a view, as the values of the named columns."""
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT %s FROM %s ORDER BY 1, 2" % (", ".join(columns), view))
            return cursor.fetchall()

    def test_all_nine_views_come_back(self):
        """The statement of the way back creates every one of the nine."""
        for view in STATISTICS_VIEWS:
            with self.subTest(view=view):
                self.assertIn(view, self.materialized_views())

    def test_the_recreated_view_answers_the_audit_rows_it_aggregates(self):
        """The statement of the way back is the aggregation of #856, with data."""
        self.assertEqual(
            self.rows_of(
                "registry_materializedlayerstatsperday",
                "id", "new", "updated", "deleted"),
            [(DAY.date(), 2, 1, 1)],
        )
        self.assertEqual(
            self.rows_of(
                "registry_materializedlayerstatsperdayandservice",
                "id", "service", "new", "updated", "deleted"),
            [(DAY.date(), WMS, 2, 1, 1)],
        )

    def test_the_alerts_are_answered_by_stored_rows_not_by_a_view(self):
        """The one view which was never one of the statistics left as well.

        The attention rows became the stored ``ServiceAlert`` relation
        (#1030) before the rebuild; the rebuilt chain neither creates the
        alert view of the predecessor nor has anything left to drop. The end
        state this pins: no view answers the statistics and no view answers
        the alerts -- the table does.
        """
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT count(*) FROM pg_views WHERE viewname = "
                "'registry_servicealertview'")
            self.assertEqual(cursor.fetchone()[0], 0)
        self.assertIn(
            ServiceAlert._meta.db_table,
            connection.introspection.table_names())

    def test_the_views_are_gone_again_on_the_way_forward(self):
        """The way forward returns the end state the rebuilt chain answers."""
        self.drop_statistics_views()
        for view in STATISTICS_VIEWS:
            with self.subTest(view=view):
                self.assertNotIn(view, self.materialized_views())
        self.assertEqual(self.materialized_views(), [])
