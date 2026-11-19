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
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from celery.exceptions import Retry
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.test import TestCase, override_settings
from django.utils import timezone as dj_timezone
from lxml import etree
from notify.models import BackgroundProcess
from registry.enums.harvesting import HarvestingPhaseEnum as Phase
from registry.exceptions.service import CapabilitiesBackupMissing
from registry.models import service as service_module
from registry.models.harvest import (AnswerOutcome, CheckedResponse,
                                     HarvestingJob, TemporaryMdMetadataFile)
from registry.models.metadata import DatasetMetadataRecord, MetadataContact
from registry.models.service import CatalogueService, WebMapService
from registry.tasks.harvest import (call_chord_md_metadata_file_to_db,
                                    call_fetch_total_records,
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


class ReferenceClaimLockOrderTest(SqlGuardMixin, TestCase):
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
    per record either. The index candidate the audit named for that count
    landed with #1392 as the hash index ``tmpmd_page_dedup_idx`` (hash and
    not btree: the guard is equality-only and this URLField stores 4096
    characters, see the Meta comment) - so the guard pins the plan through
    it, not just the statement shape and the 1-row answer of the count.
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
        content = get_records_document(0, size, size)
        # the checked answer of #1412: the tree arrives pre-parsed, exactly as
        # the fetch hands it over after the single hardened parse of the page
        checked = CheckedResponse(
            response=MockResponse(content=content),
            outcome=AnswerOutcome.DOCUMENT,
            document=etree.fromstring(content.encode('UTF-8')))
        return lambda: self.job._store_page(checked, request, 0)

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

    def test_the_duplicate_guard_reads_the_page_dedup_index(self):
        """The #1392 index behind the duplicate guard stands and is used.

        Two halves, like the #886 guard of the watchdog: the catalog holds
        a HASH index over ``requested_url`` - hash on purpose, a btree
        would refuse the very long filter-URLs this column stores - and
        the executed count plans through it.
        """
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT indexdef FROM pg_indexes WHERE tablename = %s"
                " AND indexname = 'tmpmd_page_dedup_idx'", [BACKLOG_TABLE])
            defs = [row[0] for row in cursor.fetchall()]
        self.assertEqual(
            len(defs), 1, 'the #1392 dedup index stands on the backlog')
        self.assertIn('USING hash', defs[0])
        self.assertIn('(requested_url)', defs[0])

        self._page(10)()
        _, context = self.capture(self._page(70))
        counts = [
            query for query in context.captured_queries
            if '__count' in query['sql'] and BACKLOG_TABLE in query['sql']]
        self.assertTrue(counts, 'the page asks its duplicate count')
        with off_seqscan():
            self.assertPlanUsesIndex(
                counts[-1]['sql'], BACKLOG_TABLE,
                label='the duplicate-guard count of a stored page')


class TotalRecordsFanOutShapeTest(SqlGuardMixin, TestCase):
    """``call_fetch_total_records``: the fan-out pays nothing per round trip.

    The audit's "optimize (small)" row of #1392 had two halves: the locked
    read carried no related service (paid lazily, per fire, on top of the
    lock), and the planning loop of ``handle_total_records_defined`` asked
    ``self._http_request()`` once PER PLANNED PAGE - a dict decided by
    nothing the loop changes, whose two reads a big catalogue therefore
    paid thousands of times. The guards fire the task over 1 and 100 round
    trips: the statement count must not move, and exactly one request-
    context read remains (the hoisted one - zero would mean the context
    went missing, which the fan-out must not do either).
    """

    def setUp(self):
        self.total = None

    def _seed(self, size):
        self.total = size
        self.job = HarvestingJob.objects.bulk_create([HarvestingJob(
            total_records=None, phase=Phase.DOWNLOAD_RECORDS)])[0]

    def _fire(self):
        """the task over the job of the current seed, chord mocked

        The job was bulk_created: no history, no service, so ``_http_request``
        answers the file-import branch - the deployment's configured
        superuser read is its per-call cost, the same repeated statement
        the catalogue branch pays as history plus user reads.
        """
        def run():
            with patch.object(
                    HarvestingJob, 'fetch_total_records',
                    lambda job: setattr(job, 'total_records', self.total)):
                with patch('registry.models.harvest.chord'):
                    with self.captureOnCommitCallbacks(execute=True):
                        call_fetch_total_records.run(
                            harvesting_job_id=self.job.pk)
        return run

    def test_a_hundred_round_trips_cost_the_same_as_one(self):
        """1 vs 100 planned pages (step size 50): the loop reads nothing.

        Before #1392 the wide fire paid one SELECT of the user table per
        planned page; the hoist took exactly that slope out.
        """
        self.assertQueryCountIndependent(
            sizes=(50, 5000), seed=self._seed, run=self._fire(),
            label='the total-records fan-out')

    def test_the_fan_out_keeps_exactly_one_request_context_read(self):
        """one hoisted ``_http_request`` - not zero, not one per page"""
        self._seed(5000)
        _, context = self.capture(self._fire())
        # the context read is the deployment user named by settings.MRMAP_USER
        # (``accounts.User``, not the stock auth table - derive the name)
        user_table = get_user_model()._meta.db_table
        user_reads = statements_of(context, verb='select', table=user_table)
        self.assertEqual(
            len(user_reads), 1,
            'the fan-out still carries its request context into every '
            'signature, but reads it once (#1392)')
        self.job.refresh_from_db()
        self.assertEqual(self.job.total_records, 5000,
                         'the fire is the real thing, not an early return')


class CapabilitiesDocumentReadShapeTest(SqlGuardMixin, TestCase):
    """The stored capabilities document is read once per chunk, not per record.

    ``_record_provenance`` asks ``self.job.service.client`` for the origin
    url of every imported record; the client is a ``cached_property`` of
    the SERVICE INSTANCE (#1044) and every backlog row loaded its own job,
    its own service - so a catalogue harvest read and parsed the document
    once per record. #1392 hands the chunk one shared service instance: the
    guards count the reads of a real import over a real catalogue and pin
    the answer at one, while the locked per-record reads of #895 stay
    per-record and the boundary of #1044 - a document gone from the storage
    ends the run once, loudly, and flags no backlog row - holds per chunk.
    """

    RECORD = Path(__file__).parent / '../../test_data/iso_metadata/dataset.xml'
    CAPABILITIES = (
        Path(__file__).parent / '../../test_data/capabilities/csw/2.0.2.xml')

    def setUp(self):
        media = TemporaryDirectory()
        self.addCleanup(media.cleanup)
        override = override_settings(MEDIA_ROOT=media.name)
        override.enable()
        self.addCleanup(override.disable)
        # the module-level incident state of #1044 must not leak out of a
        # guard which raises CapabilitiesBackupMissing on purpose
        self.addCleanup(service_module._capabilities_backup_missing.clear)
        contact = MetadataContact.objects.create(name='chunk caps contact')
        self.service = CatalogueService.objects.create(
            title='Chunk caps catalogue', version=202, origin=1,
            service_url='https://example.com/csw',
            metadata_contact=contact, service_contact=contact)
        self.service.xml_backup_file = SimpleUploadedFile(
            'capabilities.xml', self.CAPABILITIES.read_bytes())
        self.service.save()
        self.job = HarvestingJob.objects.create(
            total_records=4, phase=Phase.RECORDS_TO_DB, service=self.service)

    def _record(self, number):
        """the real dataset document with its fileIdentifier made unique

        Four copies of one identifier would not be four imports: the second
        import of a stored identifier runs the DUPLICATED branch of
        #1044-era dedup, which keeps its backlog row for analysis instead of
        retiring it. The guard measures one import per row, so the fixture
        hands four records the mapper can actually import.
        """
        tree = etree.fromstring(self.RECORD.read_bytes())
        codes = tree.xpath(
            '//*[local-name()="fileIdentifier"]'
            '//*[local-name()="CharacterString"]')
        self.assertTrue(codes, 'the test document carries a fileIdentifier')
        codes[0].text = f'urn:guard:chunk:{number}'
        return etree.tostring(tree)

    def _store(self, count, first_number=0):
        files = []
        for number in range(first_number, first_number + count):
            stored = TemporaryMdMetadataFile(job=self.job)
            stored.md_metadata_file.save(
                f'dataset_{number}.xml',
                ContentFile(self._record(number)), save=False)
            files.append(stored)
        return list(TemporaryMdMetadataFile.objects.bulk_create(files))

    def _chunk(self, stored):
        return lambda: call_md_metadata_files_to_db.run(
            md_metadata_file_ids=[file.pk for file in stored],
            harvesting_job_id=self.job.pk,
            background_process_pk=self.job.background_process_id,
            http_request=HTTP_REQUEST)

    @contextmanager
    def counting_capabilities(self, counter):
        """delegate to the real property, count the reads"""
        real = CatalogueService.capabilities

        def counting(self):
            counter.append(self.pk)
            return real.fget(self)

        with patch.object(CatalogueService, 'capabilities',
                          property(counting)):
            yield counter

    def test_a_real_chunk_reads_the_document_once_for_all_its_records(self):
        stored = self._store(4)
        with self.counting_capabilities([]) as reads:
            _, context = self.capture(self._chunk(stored))

        self.assertEqual(
            len(reads), 1,
            f'one capabilities read per chunk, not per record; the chunk '
            f'read it {len(reads)} times (#1392)')
        # the per-record contract of #895 is untouched by the sharing
        locked_reads = [
            query for query in statements_of(
                context, verb='select', table=BACKLOG_TABLE)
            if 'for update' in query['sql'].lower()]
        self.assertEqual(len(locked_reads), 4,
                         'the per-record locked read stays per record')
        self.assertEqual(
            len(statements_of(context, verb='delete', table=BACKLOG_TABLE)),
            4,
            'four records imported, four backlog rows retired')
        self.assertTrue(
            DatasetMetadataRecord.objects.exists(),
            'the import was the real mapper run, provenance included')
        self.assertEqual(
            DatasetMetadataRecord.objects.count(), 4,
            'all four stored files became records')

    def test_a_document_gone_between_chunks_ends_the_next_chunk_loudly(self):
        """#1044 at the granularity of #1392: the boundary re-reads.

        Chunk one imports with the cached client. The document disappears
        from the storage. Chunk two must notice - raise
        ``CapabilitiesBackupMissing``, flag nothing, and end the run there
        and not per record.
        """
        with self.counting_capabilities([]) as reads:
            self._chunk(self._store(1))()
        self.assertEqual(len(reads), 1)

        self.service.xml_backup_file.storage.delete(
            self.service.xml_backup_file.name)
        waiting = self._store(2, first_number=1)

        with self.assertRaises(CapabilitiesBackupMissing):
            self._chunk(waiting)()
        self.assertFalse(
            TemporaryMdMetadataFile.objects.filter(
                pk__in=[file.pk for file in waiting],
                has_import_error=True).exists(),
            'the broken service is never laundered into per-record import '
            'errors (#1044) - the run ends once, with one loud report')
