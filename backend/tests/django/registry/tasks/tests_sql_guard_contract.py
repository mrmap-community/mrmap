"""The guard contract of ``tests.django.sql_guard`` (#1395).

These are the meta-tests of the acceptance criterion "the fixture detects an
introduced N+1; a huge unbounded prefetch does NOT pass simply because the
query count fell": each test *injects* the shape the guard must catch and
proves the guard fires, and each has a twin which runs the narrow, already
optimal plan and proves the guard passes it. Without the passing twins a guard
which always fails would be green here - so both directions are pinned.

The data shape is the deployment's own representative large-data shape: a
harvesting job with a backlog of stored metadata files (0/1/10/100+), the same
cardinalities #1395 asks the family tests to run at.
"""
from django.test import SimpleTestCase, TestCase

from registry.models.harvest import HarvestingJob, TemporaryMdMetadataFile
from registry.models.metadata import MetadataRelation, Style
from registry.models.service import WebMapService
from tests.django.registry.tasks.tests_harvest_import_fan_out import (
    StoredFilesTestCaseMixin)
from tests.django.sql_guard import (SqlGuardMixin, fingerprint,
                                    normalize_sql, table_counter)


class StatementFingerprintTest(SimpleTestCase):
    """What makes two statements the same shape - no database involved.

    The duplicate detection stands and falls with this: a per-row read only
    shows up as a repetition once the row data is folded out of the text.
    """

    def test_literals_do_not_split_a_fingerprint(self):
        one = 'SELECT * FROM "t" WHERE "t"."name" = \'a\' AND "t"."n" = 1'
        other = 'SELECT * FROM "t" WHERE "t"."name" = \'b\' AND "t"."n" = 42'
        self.assertEqual(normalize_sql(one), normalize_sql(other))

    def test_an_in_list_of_any_length_is_one_fingerprint(self):
        small = 'SELECT * FROM "t" WHERE "t"."id" IN (1, 2)'
        large = 'SELECT * FROM "t" WHERE "t"."id" IN (1, 2, 3, 4, 5)'
        self.assertEqual(normalize_sql(small), normalize_sql(large))

    def test_a_bulk_insert_of_any_size_is_one_fingerprint(self):
        one = 'INSERT INTO "t" ("a") VALUES (1)'
        many = 'INSERT INTO "t" ("a") VALUES (1), (2), (3)'
        self.assertNotEqual(normalize_sql(one), normalize_sql(many))
        huge = 'INSERT INTO "t" ("a") VALUES (1), (2), (3), (4), (5)'
        self.assertEqual(normalize_sql(many), normalize_sql(huge))

    def test_fingerprint_reads_the_captured_shape(self):
        queries = [{'sql': 'SELECT 1 FROM "t" WHERE "id" = 1'},
                   'SELECT 1 FROM "t" WHERE "id" = 2']
        self.assertEqual(len(fingerprint(queries)), 2)
        self.assertEqual(fingerprint(queries)[0], fingerprint(queries)[1])

    def test_table_counter_names_the_main_table(self):
        queries = [{'sql': 'SELECT * FROM "registry_layer" JOIN "x" ON 1=1'}]
        self.assertEqual(table_counter(queries)['registry_layer'], 1)


class InjectedNPlusOneTest(StoredFilesTestCaseMixin, SqlGuardMixin, TestCase):
    """An intentionally introduced N+1 fails the guards (#1395 acceptance).

    The loop below is what a task regression looks like: reading or writing
    one related entity per row instead of once for the set.
    """

    def _job_with_backlog(self, count):
        job = HarvestingJob.objects.create(total_records=count)
        self._store_many(job, count)
        return job

    def test_a_per_row_read_loop_is_detected(self):
        job = self._job_with_backlog(10)
        pks = list(TemporaryMdMetadataFile.objects.filter(
            job=job).values_list('pk', flat=True))

        def naive():
            for pk in pks:
                TemporaryMdMetadataFile.objects.get(pk=pk)

        with self.assertRaises(AssertionError) as caught:
            self.assertNoNPlusOne(naive, label='the injected loop')
        self.assertIn('registry_temporarymdmetadatafile',
                      str(caught.exception))

    def test_the_bulk_read_of_the_same_work_passes(self):
        """The fix of that loop: two statements for the whole set."""
        job = self._job_with_backlog(10)

        def narrow():
            pks = list(TemporaryMdMetadataFile.objects.filter(
                job=job).values_list('pk', flat=True))
            list(TemporaryMdMetadataFile.objects.filter(pk__in=pks))

        self.assertNoNPlusOne(narrow, label='the bulk read')

    def test_a_per_row_write_loop_is_detected(self):
        """The repeated write shape - a full UPDATE per row.

        #1388 names exactly this as the red baseline of the artifact purge:
        an update in a loop over rows pays one statement per row.
        """
        job = self._job_with_backlog(10)
        pks = list(TemporaryMdMetadataFile.objects.filter(
            job=job).values_list('pk', flat=True))

        def write_loop():
            for pk in pks:
                TemporaryMdMetadataFile.objects.filter(pk=pk).update(
                    has_import_error=True)

        with self.assertRaises(AssertionError) as caught:
            self.assertNoNPlusOne(write_loop, label='the injected writes')
        self.assertIn('update', str(caught.exception).lower())

    def test_the_batched_update_of_the_same_work_passes(self):
        job = self._job_with_backlog(10)

        def batched():
            TemporaryMdMetadataFile.objects.filter(job=job).update(
                has_import_error=True)

        self.assertNoNPlusOne(batched, label='the batched update')

    def test_a_sanctioned_per_record_read_passes(self):
        """The import's per-record locked read (#895) is by design, not N+1.

        An allowance is written down as "exactly once per record": it grows
        only with the records the test seeded, so making the loop read a
        second table per row still fails.
        """
        job = self._job_with_backlog(10)
        pks = list(TemporaryMdMetadataFile.objects.filter(
            job=job).values_list('pk', flat=True))

        def per_record():
            for pk in pks:
                TemporaryMdMetadataFile.objects.get(pk=pk)

        self.assertNoNPlusOne(
            per_record,
            sanctioned={'"registry_temporarymdmetadatafile"."id" = ?': len(pks)},
            label='the sanctioned per-record read')

    def test_scaling_catches_growth_that_a_single_number_hides(self):
        """The growing shape: constant for a small fixture, linear for a big one.

        ``assertQueryCountIndependent`` measures at growing sizes precisely so
        that "12 queries" cannot silently become "12 + N queries" the moment
        the deployment holds more rows.
        """
        sizes = (1, 10, 100)

        def seed(size):
            self._job_with_backlog(size)

        def naive():
            for pk in TemporaryMdMetadataFile.objects.values_list(
                    'pk', flat=True):
                TemporaryMdMetadataFile.objects.get(pk=pk)

        with self.assertRaises(AssertionError):
            self.assertQueryCountIndependent(sizes, seed, naive,
                                             label='the injected loop')

    def test_a_constant_run_measures_green(self):
        job = None

        def seed(size):
            nonlocal job
            job = self._job_with_backlog(size)

        def guarded():
            TemporaryMdMetadataFile.objects.filter(
                job=job, has_import_error=False).exists()

        measured = self.assertQueryCountIndependent(
            (1, 10, 100), seed, guarded, label='the exists read')
        self.assertEqual(len(set(measured.values())), 1,
                         'one exists() stays one statement whatever the backlog')


class UnboundedPrefetchTest(StoredFilesTestCaseMixin, SqlGuardMixin, TestCase):
    """A huge prefetch is not an optimization (#1397 rule read by #1395).

    The plan under test lowers the *statement count* - which a naive query
    count assertion would reward - while it reads the whole backlog through
    one statement. The row-bound guard is what refuses it.
    """

    fixtures = ['test_users.json', 'test_keywords.json', 'test_wms.json']

    def _job_with_backlog(self, count):
        job = HarvestingJob.objects.create(total_records=count)
        self._store_many(job, count)
        return job

    def test_a_wide_prefetch_fails_although_its_count_is_lower(self):
        backlog = 100
        job = self._job_with_backlog(backlog)

        def per_row():
            for pk in TemporaryMdMetadataFile.objects.filter(
                    job=job).values_list('pk', flat=True):
                TemporaryMdMetadataFile.objects.get(pk=pk)

        def wide():
            # one job read + ONE prefetch statement: fewer statements than the
            # loop, but it drains the whole backlog - rows, memory, the works
            return HarvestingJob.objects.prefetch_related(
                'temporary_md_metadata_files').get(pk=job.pk)

        _, loop_queries = self.capture(per_row)
        _, wide_queries = self.capture(wide)
        # the reward a count-only assertion would wrongly pay out...
        self.assertLess(len(wide_queries), len(loop_queries.captured_queries))
        # ...and the guard which withholds it
        with self.assertRaises(AssertionError) as caught:
            self.assertRowsReadBound(
                wide, max_rows=10, label='the whole-backlog prefetch')
        self.assertIn('backlog', str(caught.exception))

    def test_a_bounded_read_of_the_same_work_passes(self):
        job = self._job_with_backlog(100)

        def bounded():
            # the pages of #1237: a sliced read never sees more than its bound
            return list(TemporaryMdMetadataFile.objects.filter(
                job=job).order_by('pk').values_list('pk', flat=True)[:10])

        self.assertRowsReadBound(bounded, max_rows=10, label='the bounded page')
        self.assertNoNPlusOne(bounded, label='the bounded page')

    def test_the_view_oriented_service_plan_fails_the_width_guard(self):
        """``prefetch_whole_service`` stays with the API (#1397).

        A task which reads what its plan names must not reach for the view
        plan: its styles and metadata relations (per layer) are exactly the
        breadth the guard forbids, even though the prefetch answers the read
        in a low, flat number of statements. The fixture service is the one
        with layers - the chain only fires where a service has elements.
        """
        service = WebMapService.objects.get(
            pk='cd16cc1f-3abb-4625-bb96-fbe80dbe23e3')
        forbidden = [Style._meta.db_table,
                     MetadataRelation._meta.db_table]

        def wide_task_plan():
            return WebMapService.objects.prefetch_whole_service().get(
                pk=service.pk)

        with self.assertRaises(AssertionError):
            self.assertStatementTouchesNo(
                wide_task_plan, forbidden, label='the view plan')

        def narrow_task_plan():
            return WebMapService.objects.select_related(
                'metadata_contact').get(pk=service.pk)

        self.assertStatementTouchesNo(
            narrow_task_plan, forbidden, label='the narrow task read')


class LockReadSafetyTest(StoredFilesTestCaseMixin, SqlGuardMixin, TestCase):
    """The EXPLAIN helpers never execute anything that writes or locks.

    ``EXPLAIN ANALYZE`` runs the statement. A guard must not take row locks
    or replay writes "to measure them", so `explain_select` refuses those
    shapes - asserted here. Row measurement never goes through EXPLAIN at
    all: it reads the cursor's row count, which is safe for every statement.
    """

    def test_explain_refuses_writes_and_locking_reads(self):
        with self.assertRaises(ValueError):
            self.explain_select('UPDATE "registry_harvestingjob" SET x = 1')
        with self.assertRaises(ValueError):
            self.explain_select(
                'SELECT * FROM "registry_harvestingjob" FOR UPDATE')

    def test_the_row_guard_measures_locked_reads_without_explain(self):
        job = HarvestingJob.objects.create(total_records=1)

        def locked():
            return list(TemporaryMdMetadataFile.objects.filter(
                job=job).select_for_update(of=('self',)))

        # the locked read is measured by its returned rows - no re-execution,
        # no lock replay - and the bound holds with an empty backlog
        self.assertRowsReadBound(locked, max_rows=1, label='the locked read')


class OrderGuardTest(StoredFilesTestCaseMixin, SqlGuardMixin, TestCase):
    """``statements_of``/``first_index_of`` answer the order questions.

    The #1263 lock order is one of them (process before row) - the helpers
    which read that order from a capture are pinned here so the family tests
    can trust them.
    """

    def test_statement_order_is_answered_from_the_capture(self):
        job = HarvestingJob.objects.create(total_records=1)
        self._store(job, 'a.xml')

        def reads_then_writes():
            TemporaryMdMetadataFile.objects.filter(job=job).exists()
            HarvestingJob.objects.filter(pk=job.pk).update(
                total_records=7)

        _, context = self.capture(reads_then_writes)
        select_index = self.first_index_of(
            context, verb='select', table='registry_temporarymdmetadatafile')
        update_index = self.first_index_of(
            context, verb='update', table='registry_harvestingjob')
        self.assertIsNotNone(select_index)
        self.assertIsNotNone(update_index)
        self.assertLess(select_index, update_index)
