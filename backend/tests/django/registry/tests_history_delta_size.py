"""What a history row changed, and whether the database was told about it (#856).

The per-day statistics answer "new / updated / deleted" by asking, for every
history row, how many tracked fields it differs in from the row that precedes
it. That used to be answered per request -- `with_delta_size()` compared every
tracked field of a row with its predecessor, a correlated subquery per row, which
is why the aggregation could only ever be answered from a materialized view.
Since #856 the number is written when the row is written, and the aggregation is
a single pass over the table.

Three things are worth keeping an eye on once a value moves into the database,
and one class each is here for them. The number has to mean the same thing for
every write path the project has, or a harvest would count differently from a
save; the assertions therefore go through `with_delta_size()` and
`stats_per_day()` rather than through whatever computes the value, because both
keep their meaning across the switch -- `tests_historical_filters.py` covers the
same value against `diff_against()` of the library. It has to be answered again
by a writer which rewrites a row without knowing the column, because such a
writer exists and it writes whole rows. And the comparison, which is literal sql
now, has to keep covering every field a resource is tracked in: a field it misses
answers statistics which are quietly wrong.
"""

import re
from datetime import datetime, timedelta, timezone
from importlib import import_module
from uuid import uuid4

from django.core.management import call_command
from django.db import connection
from django.db.models import F
from django.test import TestCase
from registry.models.metadata import (DatasetMetadataRecord, MetadataContact,
                                      ServiceMetadataRecord)
from registry.models.service import (CatalogueService, FeatureType, Layer,
                                     WebFeatureService, WebMapService)
from registry.querys.historical import with_delta_size, with_prev_record_id

# the migration which writes the comparison into the database, named the way a
# migration has to be named to be found by Django
HISTORY_DIFF = import_module(
    "registry.migrations."
    "0025_history_records_know_their_own_diff_size")

DAY1 = datetime(2026, 1, 1, 12, tzinfo=timezone.utc)


class HistoryDeltaSizeTest(TestCase):
    """The changed-field count of a history row, for every way of writing one.

    Audit rows reach the database three ways in mrmap: through ``Model.save()``
    and simple_history, through ``HistoryModel.objects.create()`` in the audit
    views and the tests, and through ``HistoryModel.objects.bulk_create()`` --
    ``bulk_create_with_history()`` ends in that call and the WMS and WFS mapper
    configs select it as ``_create_mode``. The database answers the count for all
    three, out of the row it is inserting and whatever is already stored, so what
    these tests hold is that the three ways do not answer differently.
    """

    @classmethod
    def setUpTestData(cls):
        cls.model = WebMapService.change_log.model
        cls.contact = MetadataContact.objects.create(name="Delta size contact")
        # The statistics are unfiltered, so only this test's audit rows may
        # exist -- the tests of the proxy endpoints leave rows of their own.
        cls.model.objects.all().delete()

    def values(self, object_id, history_type, day, minute=0, **changes):
        """Audit row values; the untouched ones are the same for every row."""
        return {
            "id": object_id,
            "history_relation_id": object_id,
            "history_type": history_type,
            "history_date": DAY1 + timedelta(days=day, minutes=minute),
            "title": "Original title",
            "abstract": "Original abstract",
            "origin": 1,
            "version": 130,
            "service_url": "https://example.com/wms",
            "metadata_contact_id": self.contact.pk,
            "service_contact_id": self.contact.pk,
            **changes,
        }

    def deltas(self, *object_ids):
        """The delta size of every audit row of these records, by history date.

        ``with_delta_size()`` only aliases, so the value has to be selected into
        an attribute of the row to be readable -- the same way
        ``tests_historical_filters.py`` reads it. Under a name of its own, because
        ``delta_size`` is the field the alias reads and an annotation may not
        shadow it.
        """
        queryset = with_delta_size(
            with_prev_record_id(self.model.objects.filter(id__in=object_ids))
        ).annotate(
            changed_fields=F("_delta_size")
        ).order_by("history_date")
        return [(row.history_type, row.changed_fields) for row in queryset]

    def statistics(self):
        """The per-day aggregation, as the dashboard endpoints read it."""
        return [
            (row["history_day"], row["new"], row["updated"], row["deleted"])
            for row in WebMapService.history.stats_per_day()
        ]

    def test_only_changes_of_tracked_fields_count(self):
        """History bookkeeping and non-editable fields do not make an update."""
        object_id = uuid4()
        rows = [
            self.values(object_id, "+", 0),
            # a new change reason and a non-editable field, but no tracked change
            self.values(object_id, "~", 0, 10, history_change_reason="harvest",
                        version=111),
            self.values(object_id, "~", 1, title="Changed title"),
            self.values(object_id, "~", 2, title="More title", abstract="More abstract"),
        ]
        self.model.objects.bulk_create([self.model(**row) for row in rows])

        self.assertEqual(
            self.deltas(object_id),
            [("+", None), ("~", 0), ("~", 1), ("~", 2)],
        )

    def test_a_row_without_a_predecessor_has_no_delta(self):
        """The first row of a record cannot be compared, which the statistics
        read as "this record is new" -- also for an ``~`` row, which is what a
        record harvested before history existed produces."""
        object_id = uuid4()
        self.model.objects.create(**self.values(object_id, "~", 0))

        self.assertEqual(self.deltas(object_id), [("~", None)])
        self.assertEqual(self.statistics(), [(DAY1.date(), 1, 0, 0)])

    def test_bulk_created_rows_are_classified_like_saved_ones(self):
        """One statement inserting several rows of one record still knows who
        precedes whom: the aggregation must not depend on how the rows arrived."""
        object_id = uuid4()
        rows = [
            self.values(object_id, "+", 0),
            self.values(object_id, "~", 1, title="Changed title"),
            self.values(object_id, "~", 1, 10, title="Changed title"),
            # a delete carries the tracked values of its predecessor: what makes
            # it a delete is its history_type, not its delta
            self.values(object_id, "-", 2, title="Changed title"),
        ]
        self.model.objects.bulk_create([self.model(**row) for row in rows])

        self.assertEqual(
            self.deltas(object_id),
            [("+", None), ("~", 1), ("~", 0), ("-", 0)],
        )
        self.assertEqual(self.statistics(), [
            (DAY1.date(), 1, 0, 0),
            (DAY1.date() + timedelta(days=1), 0, 1, 0),
            (DAY1.date() + timedelta(days=2), 0, 0, 1),
        ])

    def test_an_unchanged_save_is_not_an_update(self):
        """The write path of the api: saving a record without touching a field
        adds an audit row, but the day it happened stays without an update."""
        object_id = uuid4()
        service = WebMapService(
            id=object_id,
            title="Original title",
            abstract="Original abstract",
            origin=1,
            version=130,
            service_url="https://example.com/wms",
            metadata_contact=self.contact,
            service_contact=self.contact,
        )
        service._history_date = DAY1
        service.save()

        self.assertEqual(self.statistics(), [(DAY1.date(), 1, 0, 0)])

        service._history_date = DAY1 + timedelta(days=1)
        service.save()

        self.assertEqual(self.deltas(object_id), [("+", None), ("~", 0)])
        self.assertEqual(self.statistics(), [(DAY1.date(), 1, 0, 0)])

        service._history_date = DAY1 + timedelta(days=2)
        service.title = "Changed title"
        service.save()

        self.assertEqual(self.deltas(object_id), [("+", None), ("~", 0), ("~", 1)])
        self.assertEqual(self.statistics(), [
            (DAY1.date(), 1, 0, 0),
            (DAY1.date() + timedelta(days=2), 0, 1, 0),
        ])


class DiffSizeOfARewrittenRowTest(TestCase):
    """A row which is written again is answered by its predecessor again.

    ``loaddata`` ends in ``save_base(raw=True)`` without ``update_fields``, which
    writes every column of a row it found in the database from the instance the
    fixture built -- so a column the fixture does not name is written as its
    default. The behave suite loads the fixtures of a feature for every feature
    which asks for them, and thirty of them ask for ``test_wms.json``, so the two
    audit rows of its web map service were written by the first of them and
    rewritten by the twenty-nine after it. While the trigger only saw inserts,
    that rewrite reset the column of every row it touched, which is what
    ``filter[delta_size__gt]`` and the per-day statistics answer from (#874). The
    same write path is a restore of a dump on a deployment.

    Both rows are addressed by the ``history_id`` which the fixture declares for
    them, not by the service they belong to: other classes of this suite write
    audit rows of that very service, and a full-suite run answers them here.
    """

    fixtures = ["test_users.json", "test_keywords.json", "test_wms.json"]

    #: the two audit rows of the service which ``test_wms.json`` declares
    CREATED = "639cb553-8c30-4e72-a38d-10351ce81cf1"
    CHANGED = "40d6bddd-6e8b-4487-b3ed-ee2a4ac5dee2"

    def diff_sizes(self):
        """What the database answers as the diff size of those two rows."""
        return list(
            WebMapService.change_log.model.objects
            .filter(history_id__in=[self.CREATED, self.CHANGED])
            .order_by("history_date")
            .values_list("delta_size", flat=True))

    def test_reloading_the_fixture_keeps_the_diff_size(self):
        self.assertEqual(self.diff_sizes(), [None, 2])
        call_command("loaddata", "test_wms.json", verbosity=0)
        self.assertEqual(self.diff_sizes(), [None, 2])

    def test_a_change_of_a_tracked_field_changes_the_diff_size(self):
        """The other half: the value follows the data it is computed out of."""
        audit = WebMapService.change_log.model
        changed = audit.objects.get(history_id=self.CHANGED)
        # its predecessor's title, so only the abstract is left as a difference
        changed.title = audit.objects.get(history_id=self.CREATED).title
        changed.save()
        changed.refresh_from_db()
        self.assertEqual(changed.delta_size, 1)


class HistoryDiffCoversEveryTrackedFieldTest(TestCase):
    """The persisted diff compares exactly the fields a record is tracked in.

    The comparison lives in the database now, as literal sql which the migration
    writes out per audit table. That is the price of reaching the writers which
    no signal reaches -- `bulk_create()`, which is what a harvest of WMS and WFS
    layers ends in -- and it buys the statistics a single pass over the table.
    The price is paid by a column list which is frozen in a migration: a field a
    resource starts to track afterwards is a change the numbers would never
    count, and a wrong number is not something the dashboard shows.

    So the list and the models are held against each other here, read back from
    the database rather than from the migration module -- the trigger which is
    actually installed is what the answers are computed by.
    """

    RESOURCES = [
        DatasetMetadataRecord, ServiceMetadataRecord, WebMapService,
        WebFeatureService, CatalogueService, Layer, FeatureType,
    ]

    def compared_columns(self, table):
        """The columns the installed trigger of an audit table compares."""
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT prosrc FROM pg_proc WHERE proname = %s",
                [HISTORY_DIFF.function_name(table)],
            )
            function = cursor.fetchone()
        self.assertIsNotNone(
            function, "no diff size trigger for %s" % table)
        return set(re.findall(
            r"previous\.(\w+) IS DISTINCT FROM NEW\.\1", function[0]))

    def test_the_trigger_compares_the_tracked_editable_fields(self):
        for resource in self.RESOURCES:
            history_model = resource.change_log.model
            with self.subTest(table=history_model._meta.db_table):
                tracked = {
                    field.attname
                    for field in history_model.tracked_fields
                    if field.editable
                }
                self.assertEqual(
                    self.compared_columns(history_model._meta.db_table), tracked,
                    "the audit table and the model do not compare the same fields",
                )

    def test_the_migration_answers_every_audit_table_it_names(self):
        """Every table the migration writes a trigger for is one of the resources.

        A table which drops out of the migration while its statistics stay -- or
        the other way round -- leaves an audit table answering nothing or a
        statement for a table which is gone.
        """
        self.assertEqual(
            set(HISTORY_DIFF.HISTORY_TABLES),
            {resource.change_log.model._meta.db_table
             for resource in self.RESOURCES},
        )
