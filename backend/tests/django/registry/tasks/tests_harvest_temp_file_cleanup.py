"""The cleanup of the stored records of harvests which ended (#1237).

Every run stores the records it downloaded as rows and files below
``MEDIA_ROOT/temporary_md_metadata_file/``; the import deletes what it consumed
and #1237 takes the rest back once the run reached COMPLETED or ABORTED. These
tests answer the questions that deletion must keep its promises at: only ended
runs, rows before files, bounded and repeatable, and nothing outside the
temporary tree of the run it was called for.

How long a run which ended keeps its records is the retention window #1295 made
configurable: inside it a run is retry material and stays, and the periodic
sweep is what meets it once the window passed. The default of the window is the
immediate reclaim of #1237, so these promises of #1237 are kept unchanged.
"""

import os
from datetime import timedelta
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.conf import settings
from django.core.files.base import ContentFile
from django.db import transaction
from django.test import TestCase, override_settings
from django.utils.timezone import now
from django_celery_beat.models import PeriodicTask

from registry.apps import (HARVEST_TEMP_FILE_CLEANUP_TASK_NAME,
                           create_harvest_temp_file_cleanup_task)
from registry.enums.harvesting import (HarvestingPhaseEnum as Phase,
                                       LogLevelEnum)
from registry.models.harvest import (HarvestingJob, HarvestingLog,
                                     TEMPORARY_MD_METADATA_FILE_SUBDIR,
                                     TemporaryMdMetadataFile)
from registry.tasks.harvest import (
    TEMP_FILE_CLEANUP_LOG_PREFIX, TEMP_FILE_CLEANUP_MAX_CONTINUATIONS,
    _delete_temp_files, cleanup_harvesting_job_temp_files,
    cleanup_harvesting_job_temp_files_task,
    dispatch_cleanup_of_ended_harvest_backlogs,
    recover_harvesting_jobs, schedule_cleanup_of_harvest_temp_files,
    sweep_ended_harvest_temp_files, temp_file_retention_days)


class TempFileCleanupTest(TestCase):
    """The deletion itself: what it takes, what it must leave alone."""

    def setUp(self):
        self.media = TemporaryDirectory()
        self.addCleanup(self.media.cleanup)
        media = override_settings(MEDIA_ROOT=self.media.name)
        media.enable()
        self.addCleanup(media.disable)

    def job(self, phase=Phase.COMPLETED, **overrides):
        job = HarvestingJob(total_records=0, phase=phase, done_at=now())
        for key, value in overrides.items():
            setattr(job, key, value)
        HarvestingJob.objects.bulk_create([job])
        return job

    def stored(self, job, name, is_error=False):
        """A stored record of the run: a row and the file it references."""
        record = TemporaryMdMetadataFile(job=job, has_import_error=is_error)
        record.md_metadata_file.save(
            name, ContentFile(b'<record/>'), save=False)
        TemporaryMdMetadataFile.objects.bulk_create([record])
        return record

    def storage(self):
        return TemporaryMdMetadataFile._meta.get_field(
            'md_metadata_file').storage

    def test_a_completed_run_loses_rows_and_files_but_not_its_ledger(self):
        job = self.job()
        good = self.stored(job, 'good.xml')
        bad = self.stored(job, 'bad.xml', is_error=True)
        running = self.job(phase=Phase.RECORDS_TO_DB)
        keep = self.stored(running, 'waiting.xml')

        summary = cleanup_harvesting_job_temp_files(job.pk)

        self.assertFalse(summary['skipped'])
        self.assertEqual(summary['rows'], 2)
        self.assertEqual(summary['files'], 2)
        self.assertFalse(summary['remaining_rows'])
        self.assertFalse(summary['failed'])
        self.assertFalse(TemporaryMdMetadataFile.objects.filter(
            job_id=job.pk).exists())
        for name in (good.md_metadata_file.name, bad.md_metadata_file.name):
            self.assertFalse(self.storage().exists(name))
        # the job row itself stays: only its stored records are taken back
        self.assertTrue(HarvestingJob.objects.filter(pk=job.pk).exists())
        # a run which may consume its backlog again keeps every row and file
        self.assertTrue(TemporaryMdMetadataFile.objects.filter(
            job_id=running.pk).exists())
        self.assertTrue(self.storage().exists(keep.md_metadata_file.name))
        # the import errors of a completed run are taken with their rows, so
        # the cleanup leaves their count on the log of the run (#1237)
        logs = HarvestingLog.objects.filter(
            harvesting_job=job,
            description__startswith=TEMP_FILE_CLEANUP_LOG_PREFIX)
        self.assertEqual(logs.count(), 1)
        self.assertEqual(logs.get().level, LogLevelEnum.ERROR.value)
        self.assertIn('1 stored records', logs.get().description)

        # a second run over the same job is the no-op this cleanup signs off
        again = cleanup_harvesting_job_temp_files(job.pk)
        self.assertEqual(again['rows'], 0)
        self.assertEqual(again['files'], 0)
        self.assertFalse(again['remaining_rows'])
        self.assertEqual(logs.count(), 1)

    def test_a_completed_run_without_import_errors_is_written_no_log(self):
        job = self.job()
        self.stored(job, 'good.xml')
        cleanup_harvesting_job_temp_files(job.pk)
        self.assertFalse(HarvestingLog.objects.filter(
            harvesting_job=job).exists())

    def test_an_aborted_run_is_taken_back_without_a_log(self):
        """an aborted run never enters the snapshot math, so nothing has to
        outlive its rows - and its backlog goes the same way (#1237)"""
        job = self.job(phase=Phase.ABORTED)
        record = self.stored(job, 'never-imported.xml', is_error=True)

        summary = cleanup_harvesting_job_temp_files(job.pk)

        self.assertEqual(summary['rows'], 1)
        self.assertEqual(summary['files'], 1)
        self.assertFalse(self.storage().exists(record.md_metadata_file.name))
        self.assertFalse(HarvestingLog.objects.filter(
            harvesting_job=job).exists())

    def test_a_run_which_is_not_terminal_keeps_everything(self):
        for phase in (Phase.PENDING, Phase.GET_TOTAL_RECORDS_COUNT,
                      Phase.DOWNLOAD_RECORDS, Phase.RECORDS_TO_DB,
                      Phase.ABORT):
            with self.subTest(phase=phase):
                job = self.job(phase=phase)
                record = self.stored(job, 'backlog.xml')
                summary = cleanup_harvesting_job_temp_files(job.pk)
                self.assertTrue(summary['skipped'])
                self.assertEqual(summary['rows'], 0)
                self.assertTrue(TemporaryMdMetadataFile.objects.filter(
                    pk=record.pk).exists())
                self.assertTrue(self.storage().exists(
                    record.md_metadata_file.name))

    @override_settings(HARVEST_TEMP_FILE_RETENTION_DAYS=3)
    def test_a_run_which_ended_inside_the_retention_window_keeps_its_records(self):
        """while the window of #1295 is open, the stored records of the run are
        still retry material: the reschedule action of the admin re-publishes
        their import and has to find the document"""
        job = self.job(done_at=now() - timedelta(days=1))
        record = self.stored(job, 'retry-me.xml', is_error=True)

        summary = cleanup_harvesting_job_temp_files(job.pk)

        self.assertTrue(summary['deferred'])
        self.assertFalse(summary['skipped'])
        self.assertEqual(summary['rows'], 0)
        self.assertEqual(summary['files'], 0)
        self.assertTrue(TemporaryMdMetadataFile.objects.filter(
            pk=record.pk).exists())
        self.assertTrue(self.storage().exists(record.md_metadata_file.name))
        # the ledger entry of a completed run belongs to the moment its error
        # rows actually go, not to a fire which deleted nothing
        self.assertFalse(HarvestingLog.objects.filter(
            harvesting_job=job).exists())

    @override_settings(HARVEST_TEMP_FILE_RETENTION_DAYS=3)
    def test_the_records_go_when_the_retention_window_passed(self):
        job = self.job(done_at=now() - timedelta(days=4))
        record = self.stored(job, 'stale.xml', is_error=True)

        summary = cleanup_harvesting_job_temp_files(job.pk)

        self.assertFalse(summary['deferred'])
        self.assertEqual(summary['rows'], 1)
        self.assertEqual(summary['files'], 1)
        self.assertFalse(TemporaryMdMetadataFile.objects.filter(
            job_id=job.pk).exists())
        self.assertFalse(self.storage().exists(record.md_metadata_file.name))
        self.assertEqual(HarvestingLog.objects.filter(
            harvesting_job=job,
            description__startswith=TEMP_FILE_CLEANUP_LOG_PREFIX).count(), 1)

    def test_the_shipped_window_is_the_immediate_reclaim(self):
        """the default of the knob is 0, so a deployment which sets nothing
        behaves exactly as #1237 shipped it and the window is only ever
        something an operator raises for a retry (#1295)"""
        self.assertEqual(settings.HARVEST_TEMP_FILE_RETENTION_DAYS, 0)
        self.assertEqual(temp_file_retention_days(), 0)

    @override_settings(HARVEST_TEMP_FILE_RETENTION_DAYS=0)
    def test_the_default_window_takes_the_records_with_the_terminal_run(self):
        """0 is the minimum of the window and the default of a deployment which
        sets nothing: a run which ended is answered by the immediate reclaim of
        #1237, and the knob only ever delays that (#1295)"""
        self.assertEqual(temp_file_retention_days(), 0)
        job = self.job(done_at=now())
        self.stored(job, 'at-once.xml')

        summary = cleanup_harvesting_job_temp_files(job.pk)

        self.assertFalse(summary['deferred'])
        self.assertEqual(summary['rows'], 1)

    @override_settings(HARVEST_TEMP_FILE_RETENTION_DAYS=-1)
    def test_a_negative_window_is_the_immediate_reclaim(self):
        job = self.job()
        self.stored(job, 'negative.xml')
        self.assertEqual(temp_file_retention_days(), 0)
        self.assertFalse(
            cleanup_harvesting_job_temp_files(job.pk)['deferred'])

    @override_settings(HARVEST_TEMP_FILE_RETENTION_DAYS=3)
    def test_a_terminal_run_without_an_end_is_not_shielded(self):
        """every terminal transition writes done_at; a row without one is a row
        somebody edited by hand, and an unknown end must not shield its records
        for ever - that is the unbounded pile of the issue"""
        job = self.job(done_at=None)
        self.stored(job, 'no-end.xml')

        summary = cleanup_harvesting_job_temp_files(job.pk)

        self.assertFalse(summary['deferred'])
        self.assertEqual(summary['rows'], 1)

    def test_a_file_which_is_already_gone_is_not_a_failure(self):
        """a file which is not there is the state this cleanup wants: the row
        goes and the run is not told a failure happened (#1237)"""
        job = self.job()
        record = self.stored(job, 'gone.xml')
        self.storage().delete(record.md_metadata_file.name)

        summary = cleanup_harvesting_job_temp_files(job.pk)

        self.assertEqual(summary['rows'], 1)
        self.assertEqual(summary['failed'], 0)
        self.assertFalse(summary['remaining_rows'])

    def test_a_storage_which_refuses_counts_the_file_and_stays_alive(self):
        """the counters of the summary are what the continuation and the
        operator read - they are answered per kind of answer the storage gives"""
        class RefusingStorage:
            def __init__(self):
                self.gone = []

            def delete(self, name):
                if name == 'a':
                    raise FileNotFoundError(name)
                if name == 'b':
                    raise OSError('read-only device')
                self.gone.append(name)

        storage = RefusingStorage()
        deleted, missing, failed = _delete_temp_files(
            storage, ['a', 'b', 'c'])
        self.assertEqual((deleted, missing, failed), (1, 1, 1))
        self.assertEqual(storage.gone, ['c'])

    def test_a_name_outside_the_temporary_tree_of_the_run_is_refused(self):
        """a row pointing at media of somewhere else keeps its row: the
        cleanup may never reach the file of a permanent record or the backlog
        of a running job (#1237)"""
        job = self.job()
        foreign = 'registry/dataset-media/permanent-record.xml'
        self.storage().save(foreign, ContentFile(b'<permanent/>'))
        refused = TemporaryMdMetadataFile(job=job)
        refused.md_metadata_file.name = foreign
        TemporaryMdMetadataFile.objects.bulk_create([refused])
        own = self.stored(job, 'own.xml')

        summary = cleanup_harvesting_job_temp_files(job.pk)

        self.assertEqual(summary['rejected'], 1)
        self.assertEqual(summary['rows'], 1)
        self.assertTrue(summary['remaining_rows'])
        self.assertTrue(TemporaryMdMetadataFile.objects.filter(
            pk=refused.pk).exists())
        self.assertTrue(self.storage().exists(foreign))
        self.assertFalse(self.storage().exists(own.md_metadata_file.name))

    def test_a_row_of_the_legacy_none_directory_goes_with_its_row(self):
        """the layout which upload_to answered while the instance was unsaved
        puts many runs into one literal "None" directory; a row still names
        its own file inside it and is deleted like any other (#1237)"""
        job = self.job()
        name = self.storage().save(
            f'{TEMPORARY_MD_METADATA_FILE_SUBDIR}/None/legacy.xml',
            ContentFile(b'<record/>'))
        record = TemporaryMdMetadataFile(job=job)
        record.md_metadata_file.name = name
        TemporaryMdMetadataFile.objects.bulk_create([record])

        summary = cleanup_harvesting_job_temp_files(job.pk)

        self.assertEqual(summary['rejected'], 0)
        self.assertEqual(summary['rows'], 1)
        self.assertEqual(summary['files'], 1)
        self.assertFalse(self.storage().exists(name))
        # the shared directory itself is nobody's to remove here
        self.assertTrue(os.path.isdir(os.path.join(
            self.storage().location,
            TEMPORARY_MD_METADATA_FILE_SUBDIR, 'None')))

    @override_settings(HARVEST_TEMP_FILE_CLEANUP_BATCH_SIZE=2,
                       HARVEST_TEMP_FILE_CLEANUP_ROWS_PER_RUN=3)
    def test_a_run_is_bounded_and_the_next_run_continues_where_it_stopped(self):
        job = self.job()
        records = [self.stored(job, f'r{n}.xml') for n in range(4)]

        first = cleanup_harvesting_job_temp_files(job.pk)
        self.assertEqual(first['rows'], 3)
        self.assertTrue(first['capped'])
        self.assertTrue(first['remaining_rows'])
        self.assertEqual(TemporaryMdMetadataFile.objects.filter(
            job_id=job.pk).count(), 1)

        second = cleanup_harvesting_job_temp_files(job.pk)
        self.assertEqual(second['rows'], 1)
        self.assertFalse(second['capped'])
        self.assertFalse(second['remaining_rows'])
        self.assertFalse(TemporaryMdMetadataFile.objects.filter(
            job_id=job.pk).exists())
        for record in records:
            self.assertFalse(self.storage().exists(
                record.md_metadata_file.name))

    def test_the_sweep_takes_what_no_row_references_anymore(self):
        """a cleanup which died between the row delete and the file deletes,
        or a job deleted around its leftovers, leaves files the database
        cannot point at - only the sweep of the run's own directory can (#1237)"""
        job = self.job()
        orphan = self.stored(job, 'orphan.xml')
        TemporaryMdMetadataFile.objects.filter(pk=orphan.pk).delete()
        extra = self.storage().save(
            f'{TEMPORARY_MD_METADATA_FILE_SUBDIR}/{job.pk}/unreferenced.xml',
            ContentFile(b'<record/>'))

        summary = cleanup_harvesting_job_temp_files(job.pk)

        self.assertEqual(summary['rows'], 0)
        self.assertEqual(summary['swept_files'], 2)
        self.assertFalse(summary['sweep_remaining'])
        self.assertFalse(self.storage().exists(extra))
        self.assertFalse(self.storage().exists(orphan.md_metadata_file.name))
        # the empty directory of the run is removed with the last file
        self.assertFalse(os.path.isdir(os.path.join(
            self.storage().location,
            TEMPORARY_MD_METADATA_FILE_SUBDIR, str(job.pk))))

    def test_the_task_hands_itself_over_when_the_bound_was_hit(self):
        with override_settings(HARVEST_TEMP_FILE_CLEANUP_BATCH_SIZE=2,
                               HARVEST_TEMP_FILE_CLEANUP_ROWS_PER_RUN=3):
            job = self.job()
            for n in range(4):
                self.stored(job, f'r{n}.xml')
            with patch('registry.tasks.harvest.'
                       'cleanup_harvesting_job_temp_files_task.apply_async'
                       ) as later:
                summary = cleanup_harvesting_job_temp_files_task(job.pk)
        self.assertTrue(summary['capped'])
        later.assert_called_once()
        self.assertEqual(
            later.call_args.kwargs['kwargs']['harvesting_job_id'], job.pk)
        self.assertEqual(
            later.call_args.kwargs['kwargs']['continuation'], 1)
        # the bound was hit: the next run is due at once, not in a minute
        self.assertEqual(later.call_args.kwargs['countdown'], 5)

    def test_the_task_waits_a_minute_when_the_storage_stalled(self):
        job = self.job()
        refused = TemporaryMdMetadataFile(job=job)
        refused.md_metadata_file.name = 'registry/elsewhere/foreign.xml'
        TemporaryMdMetadataFile.objects.bulk_create([refused])
        with patch('registry.tasks.harvest.'
                   'cleanup_harvesting_job_temp_files_task.apply_async'
                   ) as later:
            summary = cleanup_harvesting_job_temp_files_task(job.pk)
        self.assertTrue(summary['remaining_rows'])
        self.assertFalse(summary['capped'])
        later.assert_called_once()
        self.assertEqual(later.call_args.kwargs['countdown'], 60)

    def test_the_task_leaves_a_run_inside_its_window_alone_without_continuing(
            self):
        """a deferred run is not work for the next fire of this task: the hourly
        sweep is what meets it after the window, so the task must not hand
        itself over for a run which is simply not due yet (#1295)"""
        with override_settings(HARVEST_TEMP_FILE_RETENTION_DAYS=3):
            job = self.job(done_at=now() - timedelta(hours=6))
            record = self.stored(job, 'held.xml')
            with patch('registry.tasks.harvest.'
                       'cleanup_harvesting_job_temp_files_task.apply_async'
                       ) as later, \
                    self.assertLogs('registry.tasks.harvest', level='INFO') as logs:
                summary = cleanup_harvesting_job_temp_files_task(job.pk)
        self.assertTrue(summary['deferred'])
        later.assert_not_called()
        self.assertTrue(TemporaryMdMetadataFile.objects.filter(
            pk=record.pk).exists())
        self.assertTrue(self.storage().exists(record.md_metadata_file.name))
        self.assertIn('retention window', '\n'.join(logs.output))

    def test_the_continuation_chain_is_bounded(self):
        """a cleanup which cannot finish hands over a bounded number of times;
        what outlives the chain is told, and the worker start and the hourly
        sweep keep trying (#1237)"""
        job = self.job()
        refused = TemporaryMdMetadataFile(job=job)
        refused.md_metadata_file.name = 'registry/elsewhere/foreign.xml'
        TemporaryMdMetadataFile.objects.bulk_create([refused])
        with patch('registry.tasks.harvest.'
                   'cleanup_harvesting_job_temp_files_task.apply_async'
                   ) as later, \
                self.assertLogs('registry.tasks.harvest', level='WARNING'):
            cleanup_harvesting_job_temp_files_task(
                job.pk, continuation=TEMP_FILE_CLEANUP_MAX_CONTINUATIONS)
        later.assert_not_called()


class EndedHarvestDiscoveryTest(TestCase):
    """What the sweep and the worker start hand over, and what they must not."""

    def setUp(self):
        self.media = TemporaryDirectory()
        self.addCleanup(self.media.cleanup)
        media = override_settings(MEDIA_ROOT=self.media.name)
        media.enable()
        self.addCleanup(media.disable)

    def job(self, phase=Phase.COMPLETED, **overrides):
        job = HarvestingJob(total_records=0, phase=phase, done_at=now())
        for key, value in overrides.items():
            setattr(job, key, value)
        HarvestingJob.objects.bulk_create([job])
        return job

    def stored(self, job, name):
        record = TemporaryMdMetadataFile(job=job)
        record.md_metadata_file.save(name, ContentFile(b'<record/>'),
                                     save=False)
        TemporaryMdMetadataFile.objects.bulk_create([record])
        return record

    def storage(self):
        return TemporaryMdMetadataFile._meta.get_field(
            'md_metadata_file').storage

    def test_only_ended_backlogs_are_handed_over(self):
        ended = self.job()
        self.stored(ended, 'held.xml')
        rowless = self.job()
        left = self.stored(rowless, 'orphan.xml')
        # the rows of this one are gone but its file stayed behind: exactly
        # what only the storage directory can answer
        TemporaryMdMetadataFile.objects.filter(pk=left.pk).delete()
        running = self.job(phase=Phase.RECORDS_TO_DB)
        self.stored(running, 'in-progress.xml')
        clean = self.job()
        # a directory of a job which is gone with its rows cascaded
        phantom = 999999
        self.storage().save(
            f'{TEMPORARY_MD_METADATA_FILE_SUBDIR}/{phantom}/x.xml',
            ContentFile(b'<record/>'))
        # the shared "None" directory holds open and ended files side by
        # side - only a row may point at a file inside it
        self.storage().save(
            f'{TEMPORARY_MD_METADATA_FILE_SUBDIR}/None/mixed.xml',
            ContentFile(b'<record/>'))

        with patch('registry.tasks.harvest.'
                   'cleanup_harvesting_job_temp_files_task.delay') as publish:
            dispatched = sweep_ended_harvest_temp_files.run()

        self.assertEqual(dispatched, sorted([ended.pk, rowless.pk, phantom]))
        self.assertNotIn(running.pk, dispatched)
        self.assertNotIn(clean.pk, dispatched)
        self.assertEqual(
            [call.kwargs['harvesting_job_id'] for call in publish.call_args_list],
            dispatched)

    @override_settings(HARVEST_TEMP_FILE_RETENTION_DAYS=3)
    def test_a_run_inside_its_window_waits_for_the_fire_after_it(self):
        """the sweep is the periodic half of the retention of #1295: it is what
        meets a run once its window passed, and it does not publish a task every
        hour for a run which is not due yet"""
        inside = self.job(done_at=now() - timedelta(days=1))
        self.stored(inside, 'retryable.xml')
        due = self.job(done_at=now() - timedelta(days=4))
        self.stored(due, 'due.xml')
        no_end = self.job(done_at=None)
        self.stored(no_end, 'no-end.xml')

        with patch('registry.tasks.harvest.'
                   'cleanup_harvesting_job_temp_files_task.delay') as publish:
            dispatched = dispatch_cleanup_of_ended_harvest_backlogs()

        self.assertEqual(dispatched, sorted([due.pk, no_end.pk]))
        self.assertNotIn(inside.pk, dispatched)
        self.assertEqual(
            [call.kwargs['harvesting_job_id'] for call in publish.call_args_list],
            dispatched)

    @override_settings(HARVEST_TEMP_FILE_RETENTION_DAYS=3)
    def test_the_leftovers_of_a_run_inside_its_window_wait_with_it(self):
        """the directory half of the discovery cannot ask the rows, but the run
        behind the directory can: its files are the same retention material and
        must not be swept a day before its rows are"""
        inside = self.job(done_at=now() - timedelta(days=1))
        left = self.stored(inside, 'orphan.xml')
        TemporaryMdMetadataFile.objects.filter(pk=left.pk).delete()

        with patch('registry.tasks.harvest.'
                   'cleanup_harvesting_job_temp_files_task.delay') as publish:
            dispatched = dispatch_cleanup_of_ended_harvest_backlogs()

        self.assertEqual(dispatched, [])
        publish.assert_not_called()

    @override_settings(HARVEST_TEMP_FILE_RETENTION_DAYS=3)
    def test_a_directory_whose_run_is_gone_waits_for_no_window(self):
        """a run which is not there anymore shields nothing: nothing can retry
        an import of a run nobody can name, so only its files are left and the
        sweep takes them at once (#1237)"""
        gone = self.job(done_at=now())
        self.stored(gone, 'cascade-me.xml')
        phantom = gone.pk
        HarvestingJob.objects.filter(pk=phantom).delete()

        with patch('registry.tasks.harvest.'
                   'cleanup_harvesting_job_temp_files_task.delay') as publish:
            dispatched = dispatch_cleanup_of_ended_harvest_backlogs()

        self.assertEqual(dispatched, [phantom])
        self.assertEqual(
            [call.kwargs['harvesting_job_id'] for call in publish.call_args_list],
            [phantom])

    def test_a_publish_the_broker_refuses_does_not_stop_the_sweep(self):
        first = self.job()
        self.stored(first, 'a.xml')
        second = self.job()
        self.stored(second, 'b.xml')
        with patch('registry.tasks.harvest.'
                   'cleanup_harvesting_job_temp_files_task.delay',
                   side_effect=[Exception('broker down'), None]) as publish, \
                self.assertLogs('registry.tasks.harvest', level='WARNING'):
            dispatched = dispatch_cleanup_of_ended_harvest_backlogs()
        self.assertEqual(dispatched, sorted([first.pk, second.pk]))
        self.assertEqual(publish.call_count, 2)

    def test_the_worker_start_dispatches_the_cleanup_of_ended_backlogs(self):
        """the recovery of the open harvests is the second chance of a cleanup
        whose publish or worker was lost with the restart (#1237)"""
        ended = self.job()
        self.stored(ended, 'held.xml')
        with patch('registry.tasks.harvest.'
                   'cleanup_harvesting_job_temp_files_task.delay') as publish:
            recover_harvesting_jobs.run()
        self.assertEqual(
            [call.kwargs['harvesting_job_id'] for call in publish.call_args_list],
            [ended.pk])

    def test_the_sweep_has_its_row_in_the_beat_schedule(self):
        # a TransactionTestCase earlier in the run may have truncated the
        # tables without re-firing post_migrate -- calling the receiver is the
        # idempotent way the row is created
        create_harvest_temp_file_cleanup_task(sender=None)
        row = PeriodicTask.objects.get(
            name=HARVEST_TEMP_FILE_CLEANUP_TASK_NAME)
        self.assertEqual(
            row.task, 'registry.tasks.harvest.sweep_ended_harvest_temp_files')
        self.assertEqual(row.crontab.minute, '40')


class CleanupSchedulingTest(TestCase):
    """The publish of a cleanup must never precede the commit it rides on."""

    def job(self, phase=Phase.COMPLETED):
        job = HarvestingJob(total_records=0, phase=phase, done_at=now())
        HarvestingJob.objects.bulk_create([job])
        return job

    def test_the_cleanup_is_published_only_after_the_commit(self):
        job = self.job()
        with patch('registry.tasks.harvest.'
                   'cleanup_harvesting_job_temp_files_task.delay') as publish:
            with self.captureOnCommitCallbacks(execute=True):
                with transaction.atomic():
                    schedule_cleanup_of_harvest_temp_files(job.pk)
                    publish.assert_not_called()
            publish.assert_called_once_with(harvesting_job_id=job.pk)

    def test_an_abort_schedules_the_cleanup_of_its_backlog(self):
        job = self.job(phase=Phase.RECORDS_TO_DB)
        with patch('registry.tasks.harvest.'
                   'cleanup_harvesting_job_temp_files_task.delay') as publish:
            with self.captureOnCommitCallbacks(execute=True):
                with transaction.atomic():
                    job.abort()
                    publish.assert_not_called()
            publish.assert_called_once_with(harvesting_job_id=job.pk)

    def test_a_refused_publish_does_not_break_the_terminal_transition(self):
        """the harvest whose commit the publish rides on must not fail over a
        broker which is briefly dark - the sweep is the backstop (#1237)"""
        job = self.job()
        # the assertLogs must be entered before the capture: the publish is
        # refused when the capture block runs the callbacks on its way out
        with patch('registry.tasks.harvest.'
                   'cleanup_harvesting_job_temp_files_task.delay',
                   side_effect=Exception('broker down')) as publish, \
                self.assertLogs('registry.tasks.harvest', level='WARNING'), \
                self.captureOnCommitCallbacks(execute=True):
            schedule_cleanup_of_harvest_temp_files(job.pk)
        publish.assert_called_once()
