"""The migration which drops the statistics materialized views.

The nine views of #857 answered the per-day statistics of a resource; the
endpoints answer the same aggregation over the audit records themselves since
that issue. A view is not part of the migration state -- django-pgviews used to
create it from its model -- and its models and startup hook are gone. The
migration carries the statement of both directions itself, and that statement
is what this test asks for.

Which rows the way back recreates matters as much as the fact that it recreates
them: a definition which no longer answers the audit rows it aggregated is a
rollback which builds empty statistics, and nothing but this comparison notices.
"""

from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from django.core.management import call_command
from django.db import connection
from django.test import TransactionTestCase
from mptt2.models import Tree

from registry.models.service import Layer

APP_LABEL = "registry"

#: the revision the statistics views still existed at
MIGRATE_BACK_TO = "0025_history_records_know_their_own_diff_size"

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

WMS = UUID("cd16cc1f-3abb-4625-bb96-fbe80dbe23e3")

DAY = datetime(2026, 1, 1, 12, tzinfo=timezone.utc)


class StatisticsViewsMigrationTest(TransactionTestCase):
    """Going back over the migration which dropped the statistics views."""

    # need the transaction test case, because the migration under test creates and
    # drops database objects outside the transaction of the test
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

        self.addCleanup(self.migrate)
        self.assertEqual(self.materialized_views(), [])
        self.migrate(APP_LABEL, MIGRATE_BACK_TO)

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

    @staticmethod
    def migrate(*args):
        call_command("migrate", *args, verbosity=0, interactive=False)

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

    def test_the_view_of_the_alerts_is_not_dropped(self):
        """The one view which remains is not one of the statistics."""
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT count(*) FROM pg_views WHERE viewname = "
                "'registry_servicealertview'")
            self.assertEqual(cursor.fetchone()[0], 1)

    def test_the_views_are_gone_again_on_the_way_forward(self):
        self.migrate(APP_LABEL)
        for view in STATISTICS_VIEWS:
            with self.subTest(view=view):
                self.assertNotIn(view, self.materialized_views())
