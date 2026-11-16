"""Task-side SQL guards for the harvesting and registration families (#1395).

Audit page: ``docs/source/development/celery-task-orm-audit.rst``. The
checklist items this module carries:

*   import chord build (``call_chord_md_metadata_file_to_db``) and
    ``finish_harvesting_job``: the audit classes both as *already optimal* -
    "keep the current query counts as the green baseline (guard against
    regressions)". Their backlog reads go through the
    ``["job_id", "has_import_error"]`` index of #886, and the guard asserts
    an index-backed plan on top of the count.
*   import chunk (``call_md_metadata_files_to_db``): "exactly 1 locked
    SELECT per row; the flagged-row path pays 1 UPDATE and the chunk
    continues; progress UPDATEs coalesced (#958)". The per-row locked read
    is the deliberate per-record transaction of #895 - fewer SQL statements
    would mean batching records into one transaction, which #895 forbids -
    so the guard names the allowance instead of pretending flatness.
*   ``collect_reference`` claim path: "the claim->decide path statement
    order asserts the process->row lock order of #1263"; a lost-permit
    delivery "pays the re-lock SELECTs and writes nothing".
*   ``_store_page``: "a page of 100 records: 2 SELECTs + the batched
    INSERT"; the job lock and the duplicate count of #688 pin as one each,
    the records arrive as bulk batches of 50, and a redelivered page writes
    nothing.
*   ``watch_import_backlogs`` (paired with the watchdog on the checklist):
    the first-look sweep costs per open job - locked read, index-backed
    waiting-count of #886, baseline write - and nothing per backlog row;
    the stalled branch with its mocked broker inspection stays with the
    neighbour ``tests_harvest_import_watchdog.py``.

Runtime (chunk durations, drain rates) is V2 (#1396) - statements, rows and
plans only.
"""
from contextlib import contextmanager
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from celery.exceptions import Retry
from django.db import connection
from django.test import TestCase, override_settings
from django.utils import timezone as dj_timezone
from notify.models import BackgroundProcess
from registry.enums.harvesting import HarvestingPhaseEnum as Phase
from registry.models.harvest import (HarvestingJob, TemporaryMdMetadataFile)
from registry.models.metadata import MetadataContact
from registry.models.service import CatalogueService, WebMapService
from registry.tasks.harvest import (call_chord_md_metadata_file_to_db,
                                    call_md_metadata_files_to_db,
                                    finish_harvesting_job,
                                    watch_import_backlogs)
from tests.django.registry.tasks.tests_harvest_application_records import \
    get_records_document
from tests.django.registry.tasks.tests_harvest_import_fan_out import (
    HTTP_REQUEST, StoredFilesTestCaseMixin, imports_a_record)
from tests.django.sql_guard import (SqlGuardMixin, first_index_of,
                                    statements_of)
from tests.django.utils import MockResponse

WMS_PK = 'cd16cc1f-3abb-4625-bb96-fbe80dbe23e3'
BACKLOG_TABLE = TemporaryMdMetadataFile._meta.db_table


@contextmanager
def off_seqscan():
    """EXPLAIN under ``enable_seqscan = off`` for one assertion block.

    ``SET LOCAL`` lives and dies with the surrounding transaction, which in
    a TestCase is the test's own atomic block - no state leaks to the next
    test. This does not force anything in production; it asks the planner
    "if a scan of this table were indexable here, would you take the
    index?" while the table is too small to make the seq scan interesting.
    """
    with connection.cursor() as cursor:
        cursor.execute('SET LOCAL enable_seqscan = off')
    yield


class ImportChordBuildTest(StoredFilesTestCaseMixin, SqlGuardMixin, TestCase):
    """``call_chord_md_metadata_file_to_db``: already optimal - pinned.

    One fire reads the backlog ids in ONE values-list statement no matter
    how large the backlog is (#886), registers the chunk ids in one bulk
    insert and saves the job once. A regression towards per-row backlog
    reads fails here.
    """

    def _seed(self, size):
        self.job = HarvestingJob.objects.create(
            total_records=size, phase=Phase.RECORDS_TO_DB)
        self._store_many(self.job, size)

    def _fan_out(self):
        with patch('registry.tasks.harvest.chord'):
            with self.captureOnCommitCallbacks(execute=True):
                call_chord_md_metadata_file_to_db.run(
                    harvesting_job_id=self.job.pk, http_request=HTTP_REQUEST)

    def test_the_fan_out_costs_the_same_statements_per_backlog(self):
        measured = self.assertQueryCountIndependent(
            sizes=(1, 10, 100),
            seed=self._seed,
            run=self._fan_out,
            label='the import chord build')
        self.assertEqual(len(measured), 3)

    def test_the_backlog_read_is_index_backed(self):
        """The ``["job_id", "has_import_error"]`` index of #886 is used.

        ``enable_seqscan`` is switched off for the EXPLAIN: on a small test
        table the cost-based planner often prefers a seq scan, and what this
        guards is that the composite index EXISTS and answers this exact
        read shape - not the planner's mood on a cold fixture.
        """
        self._seed(100)
        _, context = self.capture(self._fan_out)
        backlog_reads = [
            query for query in context.captured_queries
            if query['sql'].lstrip().lower().startswith('select')
            and '"registry_temporarymdmetadatafile"' in query['sql']
            and 'has_import_error' in query['sql']]
        self.assertTrue(backlog_reads, 'the fan-out reads its backlog')
        with off_seqscan():
            self.assertPlanUsesIndex(
                backlog_reads[-1]['sql'], BACKLOG_TABLE,
                label='the backlog-id read')


class ImportChunkShapeTest(StoredFilesTestCaseMixin, SqlGuardMixin, TestCase):
    """A 100-record import chunk: the per-record contract, exactly.

    The per-record locked read and the row delete are the design of #895
    (a failing record flags itself and must not fail the chunk, and every
    record commits on its own). The guards therefore pin *slope one* - one
    locked read, one delete per record, nothing else repeating - instead of
    a flat count.
    """

    def _chunk_run(self, ids, import_one=imports_a_record):
        def run():
            with patch.object(TemporaryMdMetadataFile,
                              'md_metadata_file_to_db', import_one):
                call_md_metadata_files_to_db.run(
                    md_metadata_file_ids=list(ids),
                    harvesting_job_id=self.job.pk,
                    background_process_pk=self.job.background_process_id,
                    http_request=HTTP_REQUEST)
        return run

    def _seed(self, count):
        self.job = HarvestingJob.objects.create(
            total_records=count, phase=Phase.RECORDS_TO_DB)
        self.stored = self._store_many(self.job, count)

    def test_a_chunk_locks_reads_and_deletes_exactly_once_per_record(self):
        self._seed(100)
        _, context = self.capture(self._chunk_run(
            (file.pk for file in self.stored)))

        locked_reads = [
            query for query in statements_of(
                context, verb='select', table=BACKLOG_TABLE)
            if 'for update' in query['sql'].lower()]
        self.assertEqual(len(locked_reads), 100,
                         'exactly one locked read per record (#895)')
        deletes = statements_of(
            context, verb='delete', table=BACKLOG_TABLE)
        self.assertEqual(len(deletes), 100,
                         'a successful import removes its row, once')
        # nothing else reads the backlog table, and the relation tables are
        # not swept per record: the task wrapper stays narrow
        other_backlog_reads = [
            query for query in statements_of(
                context, verb='select', table=BACKLOG_TABLE)
            if 'for update' not in query['sql'].lower()]
        self.assertLessEqual(len(other_backlog_reads), 1,
                             'the chunk reads its ids from the kwargs, not '
                             'from a second backlog read per record')

    def test_progress_writes_stay_coalesced(self):
        """>200 files are one flush, not a report per file (#958)."""
        self._seed(100)
        _, context = self.capture(self._chunk_run(
            (file.pk for file in self.stored)))
        process_writes = statements_of(
            context, verb='update', table='notify_backgroundprocess')
        self.assertLessEqual(
            len(process_writes), 2,
            'below the 200-step threshold only the trailing flush reports')
        self.assertEqual(
            BackgroundProcess.objects.get(
                pk=self.job.background_process_id).done_steps, 100)

    def test_a_failing_record_pays_one_update_and_the_chunk_continues(self):
        """The red-path shape of #895: 1 flag UPDATE for the broken record.

        The other records import normally; the failure flags its own row and
        the chunk still finishes - the guard asks how many writes that cost
        the backlog table.
        """
        self._seed(10)
        broken = self.stored[3].pk

        def import_or_fail(record):
            if record.pk == broken:
                raise ValueError('the record is broken')
            return imports_a_record(record)

        _, context = self.capture(self._chunk_run(
            (file.pk for file in self.stored), import_one=import_or_fail))

        backlog_writes = statements_of(
            context, verb='update', table=BACKLOG_TABLE)
        self.assertEqual(
            len(backlog_writes), 1,
            'the documented import error is exactly one flagged UPDATE')
        flagged = TemporaryMdMetadataFile.objects.get(pk=broken)
        self.assertTrue(flagged.has_import_error)
        self.assertEqual(
            TemporaryMdMetadataFile.objects.filter(
                job=self.job, has_import_error=False).count(), 0,
            'the other nine records imported and deleted their rows')

    def test_nothing_outside_the_record_contract_repeats(self):
        """Duplicate detection over the whole chunk, contract aside.

        The sanctioned shapes are the ones asserted count-by-count above:
        the locked per-record read and the per-record delete. A new
        per-row statement of any other shape fails here.
        """
        self._seed(20)
        self.assertNoNPlusOne(
            self._chunk_run((file.pk for file in self.stored)),
            sanctioned={
                'from "registry_temporarymdmetadatafile"': 20,
                'delete from "registry_temporarymdmetadatafile"': 20,
            },
            label='the import chunk')


class FinishHarvestingTest(StoredFilesTestCaseMixin, SqlGuardMixin, TestCase):
    """``finish_harvesting_job``: backlog-independence of the waiting check.

    While files wait, the fire locks the job, flushes the worker's steps and
    asks ``exists()`` over the #886 index - a retry, never a per-row read.
    When nothing waits, it completes. Both shapes stay constant in the
    backlog size.
    """

    def setUp(self):
        # total_records=0 would make save() complete the job right away
        # (harvest.py: "error case. CSW does not provide records") - the
        # finish under test needs a job that still sits in RECORDS_TO_DB
        self.job = HarvestingJob.objects.create(
            total_records=1, phase=Phase.RECORDS_TO_DB)

    def _finish(self):
        def run():
            try:
                with patch.object(finish_harvesting_job, 'retry',
                                  side_effect=Retry('backlog waits')):
                    finish_harvesting_job.run(
                        harvesting_job_id=self.job.pk,
                        http_request=HTTP_REQUEST)
            except Retry:
                pass
        return run

    def test_a_waiting_finish_scales_not_with_the_backlog(self):
        def seed(size):
            self._store_many(self.job, size)
            self.job.refresh_from_db()

        measured = self.assertQueryCountIndependent(
            sizes=(1, 10, 100), seed=seed, run=self._finish(),
            label='the waiting finish')
        self.assertEqual(len(set(measured.values())), 1,
                         'waiting is one exists(), not a backlog read')

    def test_the_wait_check_is_index_backed(self):
        self._store_many(self.job, 100)
        _, context = self.capture(self._finish())
        wait_checks = [
            query for query in context.captured_queries
            if query['sql'].lstrip().lower().startswith('select')
            and '"registry_temporarymdmetadatafile"' in query['sql']
            and 'limit' in query['sql'].lower()]
        self.assertTrue(
            wait_checks,
            'the fire asks whether the backlog waits; captured: %s' % [
                q['sql'][:120] for q in context.captured_queries])
        with off_seqscan():
            self.assertPlanUsesIndex(
                wait_checks[-1]['sql'], BACKLOG_TABLE,
                label='the backlog exists()')

    def test_a_drained_finish_completes_without_repeating_a_statement(self):
        """Green baseline of the terminal fire (no service -> no snapshot
        aggregates; those belong to the #1392 fixtures).

        The locked job read repeats by design: the task locks, then
        ``complete_harvest`` re-locks within the same transaction (#1263's
        seam). The history writes of the terminal save are excluded - the
        task base owes them per save, not per row.
        """
        self.assertNoNPlusOne(
            self._finish(),
            sanctioned={'from "registry_harvestingjob"': 3},
            exclude=['historical'],
            label='the finishing fire')
        self.job.refresh_from_db()
        self.assertEqual(self.job.phase, Phase.COMPLETED)


class ImportWatchShapeTest(StoredFilesTestCaseMixin, SqlGuardMixin,
                           TestCase):
    """The beat sweep of ``watch_import_backlogs`` - first looks at open jobs.

    The checklist pairs this beat task with the watchdog ("query count
    constant for 1 vs 10 open jobs with the broker inspection mocked").
    A first look never reaches the broker - the neighbour suite
    ``tests_harvest_import_watchdog.py`` owns the stalled branch with its
    mocked inspection; what this guard pins is the SQL shape: per job one
    locked read, one index-backed count of the waiting rows and the
    baseline write, and NOTHING grows with the backlog rows themselves.
    """

    def _open_job(self):
        return HarvestingJob.objects.create(
            total_records=1, phase=Phase.RECORDS_TO_DB)

    def _close_previous(self):
        """Close the jobs of an earlier seed (like the neighbour harness).

        Each measured fire must see EXACTLY its own jobs, and see them for
        the first time - an open job of an earlier fire would walk the
        stalled branch with its broker inspection, which is the neighbour
        watchdog suite's subject, not this shape guard's.
        """
        HarvestingJob.objects.filter(
            done_at__isnull=True).update(done_at=dj_timezone.now())

    def test_the_sweep_grows_with_open_jobs_not_with_backlogs(self):
        """1 vs 10 open jobs; the waiting rows stay out of the count.

        ``per_row`` here counts the per-JOB work (locked read, count,
        baseline) - the decision unit of this beat task. The second test
        pins that this per-job cost ignores the size of each backlog.
        """
        def seed(size):
            self._close_previous()
            for _ in range(size):
                job = self._open_job()
                self._store_many(job, 1)

        self.assertQueryCountIndependent(
            sizes=(1, 10), seed=seed,
            run=lambda: watch_import_backlogs.run(),
            per_row=6,
            label='the import backlog sweep')

    def test_a_hundred_waiting_rows_cost_the_same_as_one(self):
        """The count is an aggregate over the #886 index, never a read.

        Two first-seen jobs in both fires; the wide backlog enters as a
        NEW job of the second fire. If any part of the sweep read per
        row, the second fire would pay 99 statements more than the first.
        """
        def seed_backlogs(size):
            self._close_previous()
            wide = self._open_job()
            self._store_many(wide, size)
            narrow = self._open_job()
            self._store_many(narrow, 1)

        self.assertQueryCountIndependent(
            sizes=(1, 100), seed=seed_backlogs,
            run=lambda: watch_import_backlogs.run(),
            label='the import backlog sweep over a widening backlog')

    def test_the_backlog_count_never_scans_and_886_stands(self):
        """The waiting-count the sweep issues plans through an index.

        Which of the two job_id-prefixed indexes the planner picks over a
        handful of rows is a statistics question, not a contract; the two
        contract halves are asserted separately: the count of the executed
        fire never falls back to a scan of the backlog, and the #886 index
        over (job_id, has_import_error) - the covering shape which answers
        the count alone at scale - stands in the catalog with exactly that
        column order.
        """
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT indexdef FROM pg_indexes WHERE tablename = %s"
                " AND indexdef LIKE %s",
                [BACKLOG_TABLE, '%job_id%has_import_error%'])
            defs = [row[0] for row in cursor.fetchall()]
        self.assertTrue(
            defs, 'the #886 index naming has_import_error stands on the '
            'backlog table')
        self.assertTrue(
            any('(job_id, has_import_error)' in definition
                for definition in defs),
            msg=f'the #886 index covers (job_id, has_import_error) in that '
                f'order: {defs}')
        self._close_previous()
        job = self._open_job()
        self._store_many(job, 10)
        _, context = self.capture(lambda: watch_import_backlogs.run())
        counts = [
            query for query in context.captured_queries
            if '__count' in query['sql'] and BACKLOG_TABLE in query['sql']]
        self.assertTrue(counts, 'the fire asks the waiting-count')
        with off_seqscan():
            self.assertPlanUsesIndex(
                counts[-1]['sql'], BACKLOG_TABLE,
                label='the waiting-count of the import watchdog')
    """The lock order of ``claim_for_processing`` is asserted, not hoped (#1263).

    The whole registration collection shares one order: the background
    process is locked first, the work row second. The capture answers the
    order; a lost-permit delivery pays the re-lock reads and writes nothing.
    """

    fixtures = ['test_users.json', 'test_keywords.json', 'test_crs.json',
                'test_wms.json']

    URL = 'http://references.example.org/one'

    def setUp(self):
        self.wms = WebMapService.objects.get(pk=WMS_PK)
        self.layer = self.wms.layers.first()
        self.process = BackgroundProcess.objects.create(
            process_type='registration', description='a sealed plan')
        row = TemporaryMdMetadataFile(
            background_process_id=self.process.pk,
            reference_key=TemporaryMdMetadataFile.build_reference_key(
                self.layer, self.URL),
            requested_url=self.URL,
            described_layer=self.layer,
            request_id=dj_timezone.now())
        TemporaryMdMetadataFile.objects.bulk_create([row])
        self.row = TemporaryMdMetadataFile.objects.get(pk=row.pk)

    def test_the_claim_locks_the_process_before_the_row(self):
        _, context = self.capture(
            lambda: self.row.claim_for_processing(self.process.pk, 900))
        process_lock = first_index_of(
            context, verb='select', table='notify_backgroundprocess',
            contains='for update')
        row_lock = first_index_of(
            context, verb='select', table=BACKLOG_TABLE,
            contains='for update')
        lease_write = first_index_of(
            context, verb='update', table=BACKLOG_TABLE)
        self.assertIsNotNone(process_lock, 'the process is locked')
        self.assertIsNotNone(row_lock, 'the row is locked')
        self.assertIsNotNone(lease_write, 'the lease is written')
        self.assertLess(process_lock, row_lock,
                        msg='the lock order process -> row (#1263)')
        self.assertLess(row_lock, lease_write,
                        msg='both locks before any write on the row')

    def test_a_lost_permit_reads_its_locks_and_writes_nothing(self):
        token, _ = self.row.claim_for_processing(self.process.pk, 900)
        self.assertIsNotNone(token)

        _, context = self.capture(
            lambda: self.row.claim_for_processing(self.process.pk, 900))
        writes = statements_of(context, verb='update')
        self.assertEqual(
            writes, [],
            'the second delivery of an unexpired lease claims nothing and '
            'writes nothing - but it did pay the re-lock reads')
        self.assertGreaterEqual(
            len(statements_of(context, verb='select')), 2,
            'a denied claim still reads process and row under their locks')


class StorePageShapeTest(SqlGuardMixin, TestCase):
    """``HarvestingJob._store_page`` - one download page into the backlog.

    The checklist item "a page of 100 records: 2 SELECTs + the batched
    INSERT" plus what the audit found: the page lock is one SELECT FOR
    UPDATE of the job, the duplicate guard of #688 is one COUNT bounded by
    its plan, and the records go in with ``bulk_create`` of batches of 50
    (``batch_size``) - never one INSERT per record, and no other statement
    per record either. That the duplicate-guard COUNT has no index naming
    ``requested_url`` yet is the audit's index candidate; until it lands,
    the guard pins the statement shape and the 1-row answer of the count.
    """

    def setUp(self):
        media = TemporaryDirectory()
        self.addCleanup(media.cleanup)
        override = override_settings(MEDIA_ROOT=media.name)
        override.enable()
        self.addCleanup(override.disable)
        contact = MetadataContact.objects.create(name='store page contact')
        self.catalogue = CatalogueService.objects.bulk_create([
            CatalogueService(
                id='33333333-1111-1111-1111-111111111111',
                title='Store page catalogue', version=202, origin=1,
                service_url='https://example.com/csw',
                metadata_contact=contact, service_contact=contact)])[0]
        # bulk_create like the neighbour harness: the job row without the
        # process and publication that save() would attach; _store_page
        # only ever reads the job under its lock
        self.job = HarvestingJob.objects.bulk_create([HarvestingJob(
            service=self.catalogue, total_records=1,
            phase=Phase.DOWNLOAD_RECORDS)])[0]

    def _page(self, size):
        """Store one answered GetRecords page of ``size`` records."""
        request = SimpleNamespace(url=f'https://example.com/csw?page={size}')
        response = MockResponse(content=get_records_document(0, size, size))
        return lambda: self.job._store_page(response, request, 0)

    def test_a_wider_page_costs_no_more_statements(self):
        """60 and 100 records both fill two INSERT batches of 50 - constant.

        Sizes chosen inside one batch count on purpose: the honest shape
        grows with BATCHES, not records; a read per record would fail here.
        """
        pending = [None]

        def seed(size):
            pending[0] = size

        def store():
            return self._page(pending[0])()

        measured = self.assertQueryCountIndependent(
            sizes=(60, 100), seed=seed, run=store,
            label='the stored page')
        self.assertEqual(measured[60], measured[100],
                         'a page twice as wide is the same statements - '
                         'both answer two INSERT batches of the batch of 50')

    def test_the_page_is_the_job_lock_the_duplicate_count_and_two_batches(self):
        """The exact shape of a 100-record page, statement by statement."""
        _, context = self.capture(self._page(100))
        job_locks = statements_of(
            context, verb='select', table='registry_harvestingjob')
        self.assertEqual(len(job_locks), 1,
                         'one locked read of the job - the page decides '
                         'under the job lock (#688)')
        self.assertIn('for update', job_locks[0]['sql'].lower())
        backlog_selects = statements_of(
            context, verb='select', table=BACKLOG_TABLE)
        self.assertEqual(len(backlog_selects), 1,
                         'the duplicate guard of #688 is one count')
        backlog_inserts = statements_of(
            context, verb='insert', table=BACKLOG_TABLE)
        self.assertEqual(len(backlog_inserts), 2,
                         '100 records arrive as two bulk batches of 50 - '
                         'never one INSERT per record')
        # the count is bounded by its plan: it answers one row, whatever
        # backlog already stands under the job
        self.assertRowsReadBound(self._page(70), max_rows=1,
                                 label='the duplicate-guard count')

    def test_a_redelivered_page_writes_nothing(self):
        """The race winner's answer costs the loser two reads and no write.

        ``_store_page`` answers the winner's count when the page is already
        stored - the green baseline of #688's duplicate guard.
        """
        self.assertEqual(self._page(10)(), 10)
        _, context = self.capture(self._page(10))
        self.assertEqual(
            statements_of(context, verb='insert'), [],
            'the redelivery of a stored page stores nothing a second time')
        self.assertEqual(
            len(statements_of(context, verb='select')), 2,
            'job lock and duplicate count are all the loser pays')
