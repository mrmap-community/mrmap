"""The import of a harvest reports the files it commits (#958).

The load test of a 411k catalogue showed `done_steps = 0` on processes whose
`total_steps` was 411708 while 722 files per ten minutes became records: the
import tasks never told the background process about the files they committed.
Reporting naively per file would turn the one row of the process into a
row-lock hotspot behind 400k+ import transactions, so a worker coalesces its
committed files into one atomic bulk increment per threshold or interval, a
retry credits only what it committed itself, and a chord rebuild reconciles
what a dead worker lost from the backlog which is still there.

The stored files of these tests are rows without content: the import below the
`md_metadata_file_to_db` boundary is the stub, so no test needs to write XML
to the media root of them.
"""
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from django.test import TestCase, TransactionTestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.db import connection
from notify.enums import ProcessStatusEnum
from notify.models import BackgroundProcess
from registry.enums.harvesting import HarvestingPhaseEnum as Phase
from registry.models.harvest import HarvestingJob, TemporaryMdMetadataFile
from registry.querys.harvest_history import complete_harvest
from registry.tasks.harvest import (call_chord_md_metadata_file_to_db,
                                    call_md_metadata_file_to_db,
                                    call_md_metadata_files_to_db,
                                    credit_import_progress,
                                    flush_import_progress, import_md_metadata_file)
from requests.exceptions import ConnectionError

# the fan-out hands this to the tasks instead of asking the job for it, which would
# want the admin user of the deployment to build it
HTTP_REQUEST = {"path": "somepath", "method": "GET",
                "content_type": "application/json", "data": {}, "user_pk": None}

# the coalescing of the tests reports per file at the latest, so every credit
# is visible in the database without the tests having to wind a clock; where a
# test wants to see the coalescing itself it overrides these
COALESCED_PER_FILE = {
    "HARVEST_IMPORT_PROGRESS_STEPS": 1,
    "HARVEST_IMPORT_PROGRESS_SECONDS": 0,
}


def imports_a_record(record):
    """what `md_metadata_file_to_db` answers for a record: the instance of the
    metadata record it wrote, whether it was updated and whether it was newly
    created, and it deletes the stored file of itself"""
    imported = SimpleNamespace(pk=record.pk)
    record.delete()
    return [(imported, False, False)]


class ProgressMixin:
    """a harvesting job whose background process reports a running import"""

    def setUp(self):
        super().setUp()
        self.pending_cleanup = set()
        self.addCleanup(self._drain_pending)

    def _drain_pending(self):
        """forget worker-local credits left over by the test of a process which
        no longer exists, so one test cannot flush its pending batch into the
        row of a later one (the pending store lives per worker process, and the
        tests of a module share this one)"""
        for pk in self.pending_cleanup:
            flush_import_progress(pk)
        self.pending_cleanup.clear()

    def _watch_pending(self, pk):
        self.pending_cleanup.add(pk)

    def _job(self, total_records=1, phase=Phase.PENDING):
        return HarvestingJob.objects.create(
            total_records=total_records, phase=phase)

    def _store_many(self, job, count):
        stored = [TemporaryMdMetadataFile(job=job) for _ in range(count)]
        return list(TemporaryMdMetadataFile.objects.bulk_create(stored))

    def _process(self, job):
        return BackgroundProcess.objects.get(pk=job.background_process_id)

    def _bound_import(self, job, total):
        """the process of the job reports a running import over `total` files"""
        BackgroundProcess.objects.report(
            job.background_process_id, ProcessStatusEnum.RUNNING,
            phase=str(Phase.RECORDS_TO_DB.label), total_steps=total)


class ImportProgressBatcherTest(ProgressMixin, TestCase):
    """the worker-local threshold and interval of the coalesced report (#958)"""

    def setUp(self):
        super().setUp()
        self.job = self._job()
        self.pk = self.job.background_process_id
        self._bound_import(self.job, 1000)
        self._watch_pending(self.pk)

    def test_credits_below_the_threshold_stay_unreported(self):
        with override_settings(HARVEST_IMPORT_PROGRESS_STEPS=5,
                               HARVEST_IMPORT_PROGRESS_SECONDS=0):
            for _ in range(4):
                credit_import_progress(self.pk)
            self.assertEqual(0, self._process(self.job).done_steps)

            credit_import_progress(self.pk)
            self.assertEqual(5, self._process(self.job).done_steps)

    def test_the_interval_reports_an_aging_batch(self):
        clock = [0.0]
        with override_settings(HARVEST_IMPORT_PROGRESS_STEPS=1000,
                               HARVEST_IMPORT_PROGRESS_SECONDS=30), \
                patch("registry.tasks.harvest._import_progress_clock",
                      new=lambda: clock[0]):
            credit_import_progress(self.pk)
            self.assertEqual(0, self._process(self.job).done_steps)

            clock[0] = 31.0
            credit_import_progress(self.pk)
            self.assertEqual(2, self._process(self.job).done_steps)

    def test_the_flush_reports_whatever_is_pending(self):
        with override_settings(HARVEST_IMPORT_PROGRESS_STEPS=1000,
                               HARVEST_IMPORT_PROGRESS_SECONDS=0):
            credit_import_progress(self.pk)
            flush_import_progress(self.pk)
            self.assertEqual(1, self._process(self.job).done_steps)

            with CaptureQueriesContext(connection) as queries:
                flush_import_progress(self.pk)
            self.assertFalse([
                query for query in queries.captured_queries
                if query["sql"].startswith('UPDATE "notify_backgroundprocess"')],
                'an empty flush writes nothing')

    def test_a_credit_without_a_process_credits_nothing(self):
        credit_import_progress(None, 5)
        flush_import_progress(None)

    def test_a_bulk_credit_counts_in_one_write(self):
        with override_settings(HARVEST_IMPORT_PROGRESS_STEPS=100,
                               HARVEST_IMPORT_PROGRESS_SECONDS=0):
            credit_import_progress(self.pk, 100)
        self.assertEqual(100, self._process(self.job).done_steps)


class ImportTaskProgressReportingTest(ProgressMixin, TestCase):
    """what the running import tasks report of the files they commit"""

    def setUp(self):
        super().setUp()
        self.job = self._job(total_records=3)
        self._bound_import(self.job, 4)

    def test_a_chunk_reports_the_files_it_imported(self):
        stored = self._store_many(self.job, 3)
        with patch.object(TemporaryMdMetadataFile, 'md_metadata_file_to_db',
                          imports_a_record), \
                override_settings(**COALESCED_PER_FILE):
            call_md_metadata_files_to_db.run(
                md_metadata_file_ids=[file.pk for file in stored],
                harvesting_job_id=self.job.pk,
                background_process_pk=self.job.background_process_id)

        self.assertEqual(3, self._process(self.job).done_steps,
                         'the process counts every file the chunk committed')

    def test_a_replayed_chunk_counts_nothing_again(self):
        """the redelivery of a chunk which already committed works its ids
        again over rows which are gone - progress is credited per committed
        transition, never per delivery (#958)"""
        stored = self._store_many(self.job, 3)
        with patch.object(TemporaryMdMetadataFile, 'md_metadata_file_to_db',
                          imports_a_record), \
                override_settings(**COALESCED_PER_FILE):
            call_md_metadata_files_to_db.run(
                md_metadata_file_ids=[file.pk for file in stored],
                harvesting_job_id=self.job.pk,
                background_process_pk=self.job.background_process_id)
            call_md_metadata_files_to_db.run(
                md_metadata_file_ids=[file.pk for file in stored],
                harvesting_job_id=self.job.pk,
                background_process_pk=self.job.background_process_id)

        self.assertEqual(3, self._process(self.job).done_steps)

    def test_a_broken_file_counts_as_handled_exactly_once(self):
        """a flagged file never becomes a record but stays accounted for: the
        total of the run counted it and completion has to be reachable with it"""
        broken, good = self._store_many(self.job, 2)

        def import_file(record):
            if record.pk == broken.pk:
                raise ValueError('invalid metadata')
            return imports_a_record(record)

        with patch.object(TemporaryMdMetadataFile, 'md_metadata_file_to_db',
                          import_file), override_settings(**COALESCED_PER_FILE):
            call_md_metadata_files_to_db.run(
                md_metadata_file_ids=[broken.pk, good.pk],
                harvesting_job_id=self.job.pk,
                background_process_pk=self.job.background_process_id)
            self.assertEqual(2, self._process(self.job).done_steps)

            call_md_metadata_files_to_db.run(
                md_metadata_file_ids=[broken.pk, good.pk],
                harvesting_job_id=self.job.pk,
                background_process_pk=self.job.background_process_id)

        broken.refresh_from_db()
        self.assertTrue(broken.has_import_error)
        self.assertEqual(2, self._process(self.job).done_steps,
                         'the flagged file of a redelivery credits nothing again')

    def test_the_trailing_batch_of_a_chunk_is_flushed(self):
        """a run may end on a partial batch - the file of an import worker which
        never crosses the threshold again must still be visible (#958)"""
        stored = self._store_many(self.job, 1)
        with patch.object(TemporaryMdMetadataFile, 'md_metadata_file_to_db',
                          imports_a_record), \
                override_settings(HARVEST_IMPORT_PROGRESS_STEPS=1000,
                                  HARVEST_IMPORT_PROGRESS_SECONDS=0):
            call_md_metadata_files_to_db.run(
                md_metadata_file_ids=[file.pk for file in stored],
                harvesting_job_id=self.job.pk,
                background_process_pk=self.job.background_process_id)

        self.assertEqual(1, self._process(self.job).done_steps)

    def test_an_aborted_job_reports_nothing_for_its_chunk(self):
        """the progress of an aborted process freezes where the abort decided
        about it: skipped files were never handled work and the terminal
        process is not touched by reports which are still in flight"""
        stored = self._store_many(self.job, 2)
        HarvestingJob.objects.filter(pk=self.job.pk).update(phase=Phase.ABORTED)
        BackgroundProcess.objects.report(
            self.job.background_process_id, ProcessStatusEnum.ABORTED)

        with patch.object(TemporaryMdMetadataFile, 'md_metadata_file_to_db',
                          imports_a_record), \
                override_settings(**COALESCED_PER_FILE):
            call_md_metadata_files_to_db.run(
                md_metadata_file_ids=[file.pk for file in stored],
                harvesting_job_id=self.job.pk,
                background_process_pk=self.job.background_process_id)
            credit_import_progress(self.job.background_process_id)
            flush_import_progress(self.job.background_process_id)

        self.assertEqual(0, self._process(self.job).done_steps)
        self.assertEqual(
            2, TemporaryMdMetadataFile.objects.filter(job=self.job).count(),
            'the files of the aborted job were skipped, not handled')

    def test_a_single_file_task_reports_the_file_it_imported(self):
        stored = self._store_many(self.job, 1)
        with patch.object(TemporaryMdMetadataFile, 'md_metadata_file_to_db',
                          imports_a_record), \
                override_settings(**COALESCED_PER_FILE):
            call_md_metadata_file_to_db.run(
                md_metadata_file_id=stored[0].pk,
                harvesting_job_id=self.job.pk,
                background_process_pk=self.job.background_process_id)
            self.assertEqual(1, self._process(self.job).done_steps)

            # the redelivery of the same message (acks_late) imports nothing
            # again and credits nothing again
            call_md_metadata_file_to_db.run(
                md_metadata_file_id=stored[0].pk,
                harvesting_job_id=self.job.pk,
                background_process_pk=self.job.background_process_id)
            self.assertEqual(1, self._process(self.job).done_steps)

    def test_a_task_whose_kwargs_predate_the_kwarg_resolves_the_process(self):
        """a message which was already queued when the deployment learned to
        name the process on the task must not import into silence (#958)"""
        stored = self._store_many(self.job, 1)
        with patch.object(TemporaryMdMetadataFile, 'md_metadata_file_to_db',
                          imports_a_record), \
                override_settings(**COALESCED_PER_FILE):
            call_md_metadata_file_to_db.run(
                md_metadata_file_id=stored[0].pk,
                harvesting_job_id=self.job.pk)

        self.assertEqual(1, self._process(self.job).done_steps)

    def test_the_import_function_credits_only_committed_transitions(self):
        gone_credits = []

        def on_handled():
            gone_credits.append(1)

        stored = self._store_many(self.job, 1)
        with patch.object(TemporaryMdMetadataFile, 'md_metadata_file_to_db',
                          imports_a_record):
            self.assertIsNotNone(import_md_metadata_file(
                stored[0].pk, on_handled=on_handled))
            self.assertEqual([1], gone_credits)

            # the row is gone: a redelivery imports nothing and credits nothing
            self.assertIsNone(import_md_metadata_file(
                stored[0].pk, on_handled=on_handled))
            self.assertEqual([1], gone_credits)

            # a row which never existed is not handled work either
            self.assertIsNone(import_md_metadata_file(uuid4(), on_handled=on_handled))
            self.assertEqual([1], gone_credits)


class ImportProgressRebuildTest(ProgressMixin, TestCase):
    """the chord rebuild of the recovery reconciles progress from the backlog (#958)

    A worker which died took the credits it had not reported with it; the
    rebuild must raise the progress to what the durable backlog proves - and
    never lower what live workers already reported, nor shrink the denominator
    the overview computes the percentage from.
    """

    def setUp(self):
        super().setUp()
        self.job = self._job(total_records=10)
        self._bound_import(self.job, 11)  # 10 files + the finish step
        self.stored = self._store_many(self.job, 10)
        HarvestingJob.objects.filter(pk=self.job.pk).update(
            phase=Phase.RECORDS_TO_DB.value)

    def _rebuild(self):
        with patch.object(HarvestingJob, '_http_request',
                          return_value=HTTP_REQUEST), \
                self.captureOnCommitCallbacks(execute=True):
            call_chord_md_metadata_file_to_db.run(
                harvesting_job_id=self.job.pk)

    def _import_some(self, count):
        """the rows of `count` stored files go: the deletion of an import"""
        gone = TemporaryMdMetadataFile.objects.filter(
            job=self.job).order_by('pk').values_list(
                'pk', flat=True)[:count]
        TemporaryMdMetadataFile.objects.filter(pk__in=list(gone)).delete()

    def test_a_rebuild_reconciles_the_progress_from_the_backlog(self):
        """four files became records while the process still read 0: the bound
        of the backlog was 10 files, 6 wait, so 4 are done"""
        self._import_some(4)

        with patch("registry.tasks.harvest.chord") as mocked_chord:
            self._rebuild()

        process = self._process(self.job)
        self.assertEqual(11, process.total_steps,
                         'the rebuild must not shrink the total with the drain')
        self.assertEqual(4, process.done_steps)
        chunk = mocked_chord.call_args.args[0][0]
        self.assertEqual(6, len(chunk.kwargs["md_metadata_file_ids"]))
        self.assertEqual(self.job.background_process_id,
                         chunk.kwargs["background_process_pk"],
                         'the published chunks have to know whose progress they move')

    def test_a_rebuild_never_lowers_a_reported_progress(self):
        """live workers reported 9 of 10 - one unflushed credit less than the
        backlog now proves: reconciliation answers 9 is what stays"""
        self._import_some(4)
        BackgroundProcess.objects.report(
            self.job.background_process_id, ProcessStatusEnum.RUNNING,
            steps_done=9)

        with patch("registry.tasks.harvest.chord"):
            self._rebuild()

        self.assertEqual(9, self._process(self.job).done_steps)

    def test_a_rebuild_accounts_for_flagged_files(self):
        """three imported, one flagged: both transitions leave the backlog for
        good and both are handled work - the reconciliation of a bound of 10
        with 6 waiting answers 4, exactly what the live reporters credit"""
        self._import_some(3)
        flagged = TemporaryMdMetadataFile.objects.filter(
            job=self.job).order_by('pk').first()
        TemporaryMdMetadataFile.objects.filter(
            pk=flagged.pk).update(has_import_error=True)

        with patch("registry.tasks.harvest.chord"):
            self._rebuild()

        self.assertEqual(4, self._process(self.job).done_steps)

    def test_a_rebuild_keeps_the_progress_of_a_run_which_lost_its_chord(self):
        """crash right after the first bound: nothing was imported, nothing was
        reported - a rebuild of an untouched backlog changes nothing"""
        with patch("registry.tasks.harvest.chord"):
            self._rebuild()

        process = self._process(self.job)
        self.assertEqual(11, process.total_steps)
        self.assertEqual(0, process.done_steps)

    def test_the_first_build_of_a_backlog_still_bounds_the_total_by_the_files(self):
        """the entry into the import phase keeps the existing math: one step
        per file plus the finish step, unaccounted progress starting at 0"""
        job = self._job(total_records=10, phase=Phase.PENDING)
        self._store_many(job, 10)

        with patch("registry.tasks.harvest.chord"):
            with patch.object(HarvestingJob, '_http_request',
                              return_value=HTTP_REQUEST), \
                    self.captureOnCommitCallbacks(execute=True):
                call_chord_md_metadata_file_to_db.run(harvesting_job_id=job.pk)

        process = self._process(job)
        self.assertEqual(11, process.total_steps)
        self.assertEqual(0, process.done_steps)


class ImportProgressRecoveryRetryTest(ProgressMixin, TransactionTestCase):
    """the celery machinery must not double-count a retried import (#958)

    TransactionTestCase: the deployment closes connections around every task
    run (MrMap/celery.py), which the transaction of a TestCase does not
    survive - the eager apply of this test needs the real machinery.
    """

    def setUp(self):
        super().setUp()
        self.job = HarvestingJob.objects.create(total_records=10)
        self._bound_import(self.job, 11)
        self.files = self._store_many(self.job, 10)
        HarvestingJob.objects.filter(pk=self.job.pk).update(
            phase=Phase.RECORDS_TO_DB.value)
        self._watch_pending(self.job.background_process_id)

    def test_a_retried_chunk_credits_its_files_once(self):
        """the first attempt commits the first file, loses the catalogue on the
        second and goes to retry - the credit for the committed file is
        flushed on the way out and the redelivery credits only the file it
        commits itself: never the first one a second time"""
        attempts = []

        def import_file(record):
            attempts.append(record.pk)
            if len(attempts) == 1:
                # commit this one, fail on the next like on a read timeout
                imports_a_record(record)
                raise ConnectionError('the catalogue hung up')
            return imports_a_record(record)

        with patch.object(TemporaryMdMetadataFile, 'md_metadata_file_to_db',
                          import_file), \
                override_settings(**COALESCED_PER_FILE):
            result = call_md_metadata_files_to_db.apply(
                kwargs={'md_metadata_file_ids': [f.pk for f in self.files[:2]],
                        'harvesting_job_id': self.job.pk,
                        'background_process_pk': self.job.background_process_id},
                throw=False)

        self.assertEqual('SUCCESS', result.state, str(result.result))
        self.assertEqual(8, TemporaryMdMetadataFile.objects.filter(
            job=self.job).count())
        self.assertEqual(2, self._process(self.job).done_steps,
                         'both files count, neither twice')

    def test_a_worker_which_died_with_unreported_credits_is_reconciled(self):
        """the worker imported two files and died before its pending batch was
        due: the report never went out, the records are committed. Recovery
        finds the backlog without those two files and raises the progress which
        the process never saw (#958)"""
        with patch.object(TemporaryMdMetadataFile, 'md_metadata_file_to_db',
                          imports_a_record), \
                override_settings(HARVEST_IMPORT_PROGRESS_STEPS=1000,
                                  HARVEST_IMPORT_PROGRESS_SECONDS=0):
            # credits which this worker will not flush: simulate the death by
            # draining the pending store without reporting
            for stored in self.files[:2]:
                import_md_metadata_file(
                    stored.pk,
                    on_handled=lambda: credit_import_progress(
                        self.job.background_process_id))
            from registry.tasks.harvest import _import_progress_pending
            _import_progress_pending.pop(
                str(self.job.background_process_id), None)

        self.assertEqual(0, self._process(self.job).done_steps,
                         'the lost report never reached the process')

        # TransactionTestCase commits for real, so the on_commit publishing of
        # the chord runs without any capture - and the chord is the mock
        with patch("registry.tasks.harvest.chord"), \
                patch.object(HarvestingJob, '_http_request',
                             return_value=HTTP_REQUEST):
            call_chord_md_metadata_file_to_db.run(
                harvesting_job_id=self.job.pk)

        process = self._process(self.job)
        self.assertEqual(11, process.total_steps,
                         'a rebuild keeps the total of the first bound')
        self.assertEqual(2, process.done_steps,
                         'the 10 files of the bound minus the 8 still waiting '
                         'are reconciled to the 2 committed unreported')


class ImportProgressLoadTest(ProgressMixin, TestCase):
    """the scenario of job #40 of the load test, at the scale of the acceptance
    criteria: 2500 stored files, chord published, chunks consumed - and the
    progress of the process must leave 0% during the import and land exactly
    on the total when the harvest completes (#958).

    The write frequency is asserted next to the numbers: a coalesced report of
    200 steps per write answers this run in dozens of row updates for 2500
    files, not 2500 - at the full 411k of the load test the same math answers
    about two thousand updates for a backlog which takes hours to drain.
    """

    def setUp(self):
        super().setUp()
        self.job = self._job(total_records=2500)
        self.files = self._store_many(self.job, 2500)

    def test_progress_advances_during_import_and_completes_at_the_total(self):
        with patch("registry.tasks.harvest.chord") as mocked_chord:
            with patch.object(HarvestingJob, '_http_request',
                              return_value=HTTP_REQUEST), \
                    self.captureOnCommitCallbacks(execute=True):
                call_chord_md_metadata_file_to_db.run(
                    harvesting_job_id=self.job.pk, http_request=HTTP_REQUEST)

        header, _callback = mocked_chord.call_args.args
        self.assertEqual(10, len(header),
                         '2500 files answer 10 chunks of 250')

        process = self._process(self.job)
        self.assertEqual(2501, process.total_steps)
        self.assertEqual(0, process.done_steps)

        with patch.object(TemporaryMdMetadataFile, 'md_metadata_file_to_db',
                          imports_a_record), \
                CaptureQueriesContext(connection) as queries:
            for chunk in header:
                call_md_metadata_files_to_db.run(**chunk.kwargs)
            writes = [
                query for query in queries.captured_queries
                if query["sql"].startswith('UPDATE "notify_backgroundprocess"')]

        process = BackgroundProcess.objects.process_info().get(
            pk=self.job.background_process_id)
        self.assertEqual(2500, process.done_steps,
                         'every imported file is accounted for')
        self.assertGreater(process.progress, 0.0)
        self.assertLess(process.progress, 100.0)
        # one update coalesces ~120 files: 12 threshold reports of 200 plus a
        # trailing flush per chunk; assert the order of magnitude of the
        # coalescing, not the exact interleaving
        self.assertLessEqual(len(writes), 25,
                             'progress is reported coalesced, not per file')
        self.assertGreaterEqual(len(writes), 13)

        # the surface the background activity renders is the serializer over
        # exactly these numbers - the issue saw it frozen at 0 %
        from notify.serializers import BackgroundProcessSerializer
        from rest_framework.test import APIRequestFactory
        payload = BackgroundProcessSerializer(
            instance=process,
            context={"request": APIRequestFactory().get('/')}
        ).data
        self.assertGreater(float(payload['progress']), 0.0)

        complete_harvest(self.job.pk)
        process = BackgroundProcess.objects.process_info().get(
            pk=self.job.background_process_id)
        self.assertEqual(2501, process.done_steps,
                         'completion reaches the total exactly')
        self.assertEqual(100.0, process.progress)
