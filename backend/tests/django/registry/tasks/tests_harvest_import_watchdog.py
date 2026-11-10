"""The watchdog which bounds the wait of a stranded import backlog (#1038).

The wait of an import chord is bounded by the retry budget this project hands
celery (``max_retries=300, interval=1``), and when that budget runs out, celery
raises inside its own builtin ``chord_unlock``: the chord's callback - the one
which sets ``done_at`` and raises the catalogue's alert - is dropped and no
mrmap code can observe it. Job 42 of the issue stood ten hours in "records to
db" over 50 untouched records with empty queues, and the api answered nothing
about it.

These tests hold the watchdog which replaced the quiet wait:

* a backlog which moves is never asked about the broker, and a first look only
  measures it;
* a backlog which stands still for a whole watchdog interval is decided with
  the broker: gone from it -> out again as one fresh chord through the resume
  path of #972; still queued on it -> reported on the job and never published
  over (#891); unaskable -> reported and the operator path named (#972's);
* the report happens once per stall and is cleared when the backlog drains;
* only the stall reaches the api, the watchdog's memory stays private.

The two broker probes are the seam the staleness module tests against real
fakes, so this module patches them and holds what the watchdog decides with
their answers.
"""

from tempfile import TemporaryDirectory
from unittest.mock import patch
from uuid import uuid4

from django.conf import settings
from django.core.files.base import ContentFile
from django.test import TestCase, override_settings
from django.utils import timezone
from django_celery_beat.models import IntervalSchedule, PeriodicTask
from notify.enums import OperationStateEnum, ProcessStatusEnum
from notify.models import BackgroundProcess
from registry.apps import IMPORT_WATCH_TASK_NAME
from registry.enums.harvesting import HarvestingPhaseEnum as Phase
from registry.enums.harvesting import LogLevelEnum
from registry.models.harvest import (HarvestingJob, HarvestingJobTaskId,
                                     TemporaryMdMetadataFile)
from registry.serializers.harvesting import HarvestingJobSerializer
from registry.tasks.harvest import (HARVEST_IMPORT_WATCH_ORIGIN,
                                    call_chord_md_metadata_file_to_db,
                                    import_watch_interval,
                                    watch_import_backlog,
                                    watch_import_backlogs)
from rest_framework.test import APIRequestFactory

INTERVAL = timezone.timedelta(minutes=5)


class WatchImportBacklogTest(TestCase):
    """The per-job decision: measure, report, resume - and never pile up."""

    def setUp(self):
        self.media = TemporaryDirectory()
        self.addCleanup(self.media.cleanup)
        media_settings = override_settings(MEDIA_ROOT=self.media.name)
        media_settings.enable()
        self.addCleanup(media_settings.disable)
        self.job = HarvestingJob(total_records=2, phase=Phase.RECORDS_TO_DB)
        HarvestingJob.objects.bulk_create([self.job])
        self.records = []
        for _ in range(2):
            record = TemporaryMdMetadataFile(job=self.job)
            record.md_metadata_file.save('record.xml', ContentFile(b'<record/>'),
                                         save=False)
            self.records.append(record)
        TemporaryMdMetadataFile.objects.bulk_create(self.records)

    def remember(self, waiting, at):
        """the memory of an earlier look, as the watchdog itself wrote it"""
        HarvestingJob.objects.filter(pk=self.job.pk).update(
            import_backlog_seen=waiting, import_backlog_seen_at=at)

    def test_a_first_look_only_measures_the_backlog(self):
        """nothing is overdue before anything was seen - and a measuring look
        does not bother the broker at all"""
        at = timezone.now()
        with patch('registry.tasks.harvest.import_run_message_state') as ask, \
                patch('registry.tasks.harvest.chord_publish_message_state') as publish_ask, \
                patch.object(call_chord_md_metadata_file_to_db, 'delay') as publish:
            watch_import_backlog(self.job.pk, at=at)

        ask.assert_not_called()
        publish_ask.assert_not_called()
        publish.assert_not_called()
        self.job.refresh_from_db()
        self.assertEqual(self.job.import_backlog_seen, 2)
        self.assertEqual(self.job.import_backlog_seen_at, at)
        self.assertIsNone(self.job.import_stalled_at)

    def test_a_moving_backlog_is_never_asked_about_the_broker(self):
        """an import which works commits and deletes one row per record, so its
        count moves between two looks - and a moving backlog is no stall, even
        when the last look lies a whole interval back"""
        self.records[0].delete()
        self.remember(2, timezone.now() - 2 * INTERVAL)

        at = timezone.now()
        with patch('registry.tasks.harvest.import_run_message_state') as ask, \
                patch.object(call_chord_md_metadata_file_to_db, 'delay') as publish:
            watch_import_backlog(self.job.pk, at=at)

        ask.assert_not_called()
        publish.assert_not_called()
        self.job.refresh_from_db()
        self.assertEqual(self.job.import_backlog_seen, 1)
        self.assertEqual(self.job.import_backlog_seen_at, at)

    def test_an_untouched_backlog_the_broker_holds_nothing_goes_out_again(self):
        """the issue's ending with an empty queue: nothing of the run is on the
        broker anymore, so the backlog is stranded and the resume path of #972
        takes it - which drops the rows of the ids which outlived their
        messages and names the watchdog as the decider on the job"""
        lost = uuid4()
        HarvestingJobTaskId.objects.create(job=self.job, task_id=lost)
        self.remember(2, timezone.now() - INTERVAL - timezone.timedelta(minutes=1))

        with patch('registry.tasks.harvest.import_run_message_state',
                   return_value=False) as ask, \
                patch('registry.tasks.harvest.chord_publish_message_state',
                      return_value=False), \
                patch.object(call_chord_md_metadata_file_to_db, 'delay') as publish:
            watch_import_backlog(self.job.pk, at=timezone.now())

        ask.assert_called_once_with({str(lost)})
        publish.assert_called_once_with(harvesting_job_id=self.job.pk)
        self.assertFalse(HarvestingJobTaskId.objects.filter(creation=False).exists())
        self.job.refresh_from_db()
        self.assertIsNone(
            self.job.import_backlog_seen,
            'the re-published chord is measured from now on')
        self.assertIsNone(self.job.import_stalled_at)
        watchdog_log = self.job.logs.filter(
            description__contains='goes out again as one chord').get()
        self.assertEqual(watchdog_log.level, LogLevelEnum.WARNING.value)
        self.assertIn(HARVEST_IMPORT_WATCH_ORIGIN, watchdog_log.description)
        # the resume of #972 tells its own half on the log as always
        self.assertTrue(self.job.logs.filter(
            description__contains='name no message on the broker').exists())

    def test_a_stall_the_broker_still_holds_is_reported_but_never_published(self):
        """the issue's proximate cause: the messages sit queued on
        ``harvest-import`` and no worker consumes them. Publishing over them is
        #891's pile-up, so the only act is the state the api could not answer:
        the job says on itself that its import does not move - once per stall"""
        HarvestingJobTaskId.objects.create(job=self.job, task_id=uuid4())
        first = timezone.now()
        watch_import_backlog(self.job.pk, at=first)

        with patch('registry.tasks.harvest.import_run_message_state',
                   return_value=True), \
                patch('registry.tasks.harvest.chord_publish_message_state',
                      return_value=False), \
                patch.object(call_chord_md_metadata_file_to_db, 'delay') as publish:
            watch_import_backlog(self.job.pk, at=first + INTERVAL)

            publish.assert_not_called()
            self.job.refresh_from_db()
            self.assertEqual(self.job.import_stalled_at, first,
                             'the stall is stamped from the last look which measured it')
            self.assertTrue(HarvestingJobTaskId.objects.filter(creation=False).exists(),
                            'a live run keeps its ids registered for the abort')
            log = self.job.logs.get()
            self.assertEqual(log.level, LogLevelEnum.WARNING.value)
            self.assertIn('harvest-import', log.description)
            self.assertIn('nothing was published', log.description)

            # the stall stays reported on the job, but it is told once - a beat
            # fire per interval must not shout per fire
            watch_import_backlog(self.job.pk, at=first + 2 * INTERVAL)
            self.assertEqual(self.job.logs.count(), 1)
            self.job.refresh_from_db()
            self.assertEqual(self.job.import_stalled_at, first)

    def test_an_unaskable_broker_reports_and_names_the_operator_path(self):
        """without the broker the two causes are not tellable apart, so the
        safe side of #891 stays: nothing published, the standstill reported,
        and the one supported repair named on the job"""
        first = timezone.now()
        watch_import_backlog(self.job.pk, at=first)

        with patch('registry.tasks.harvest.import_run_message_state',
                   return_value=None), \
                patch('registry.tasks.harvest.chord_publish_message_state',
                      return_value=False), \
                patch.object(call_chord_md_metadata_file_to_db, 'delay') as publish:
            watch_import_backlog(self.job.pk, at=first + INTERVAL)

        publish.assert_not_called()
        self.job.refresh_from_db()
        self.assertIsNotNone(self.job.import_stalled_at)
        log = self.job.logs.get()
        self.assertEqual(log.level, LogLevelEnum.WARNING.value)
        self.assertIn(f'resume_harvesting_job {self.job.pk}', log.description)

    def test_a_stall_which_drains_again_is_cleared_and_said(self):
        """the state on the job means "untouched since"; the first look which
        finds fewer waiting files ends the stall - and says so once, because
        an operator who saw the report wants to see its end too"""
        HarvestingJob.objects.filter(pk=self.job.pk).update(
            import_backlog_seen=2,
            import_backlog_seen_at=timezone.now() - 2 * INTERVAL,
            import_stalled_at=timezone.now() - INTERVAL)
        self.records[0].delete()

        with patch('registry.tasks.harvest.import_run_message_state') as ask, \
                patch.object(call_chord_md_metadata_file_to_db, 'delay') as publish:
            watch_import_backlog(self.job.pk, at=timezone.now())

        ask.assert_not_called()
        publish.assert_not_called()
        self.job.refresh_from_db()
        self.assertIsNone(self.job.import_stalled_at)
        self.assertEqual(self.job.import_backlog_seen, 1)
        log = self.job.logs.get()
        self.assertIn('drains again', log.description)

    def test_a_run_which_ended_or_moved_on_is_not_watched(self):
        """the watchdog bounds the wait of an import phase: a finished job and
        a job still downloading have no import backlog to strand - and its
        bookkeeping of a closed run stays untouched by a watchdog fire"""
        closed = HarvestingJob(total_records=2, phase=Phase.RECORDS_TO_DB,
                               done_at=timezone.now(),
                               import_backlog_seen=2,
                               import_backlog_seen_at=timezone.now() - 2 * INTERVAL)
        HarvestingJob.objects.bulk_create([closed])
        downloading = HarvestingJob(total_records=2, phase=Phase.DOWNLOAD_RECORDS)
        HarvestingJob.objects.bulk_create([downloading])

        with patch('registry.tasks.harvest.import_run_message_state') as ask, \
                patch.object(call_chord_md_metadata_file_to_db, 'delay') as publish:
            watch_import_backlog(closed.pk, at=timezone.now())
            watch_import_backlog(downloading.pk, at=timezone.now())

        ask.assert_not_called()
        publish.assert_not_called()
        closed.refresh_from_db()
        self.assertEqual(closed.import_backlog_seen, 2,
                         'the memory of a closed run is not for the watchdog to clear')
        self.assertEqual(self.job.logs.count() + downloading.logs.count(), 0)


class ImportStallReportsTheOperationTest(TestCase):
    """The stall decision reaches the operation which reports the run (#1207).

    The watchdog answers a standstill on the job - that is the gap #1038
    closed - while the background job center asks the process which reports
    that run. Both answers have to come from the one decision, so the watchdog
    is the only writer of the flag for a harvest: it sets it with the stall,
    clears it when the backlog drains again, and a run whose process was never
    made (the beats of a job which came into being by a bulk write) survives
    every one of those decisions.
    """

    def setUp(self):
        self.media = TemporaryDirectory()
        self.addCleanup(self.media.cleanup)
        media_settings = override_settings(MEDIA_ROOT=self.media.name)
        media_settings.enable()
        self.addCleanup(media_settings.disable)
        with patch('celery.canvas.Signature.apply_async'):
            self.job = HarvestingJob.objects.create(
                total_records=2, phase=Phase.RECORDS_TO_DB)
        self.records = []
        for _ in range(2):
            record = TemporaryMdMetadataFile(job=self.job)
            record.md_metadata_file.save(
                'record.xml', ContentFile(b'<record/>'), save=False)
            self.records.append(record)
        TemporaryMdMetadataFile.objects.bulk_create(self.records)
        # by the moment a backlog can strand, the import reported the run as
        # working - that is the state the stall moves the operation away from
        BackgroundProcess.objects.report(
            self.job.background_process_id, ProcessStatusEnum.RUNNING,
            total_steps=2)

    def reported(self):
        return BackgroundProcess.objects.process_info().get(
            pk=self.job.background_process_id)

    def stalled(self, at=None):
        """the two looks which decide a stall: measured, then untouched for a
        whole interval while the broker still holds the work

        The broker answers the same on both looks: the baseline never asks it,
        but a repeated call of this helper must not let an unpatched look take
        the repair branch and publish the backlog again.
        """
        at = at or timezone.now()
        with patch('registry.tasks.harvest.import_run_message_state',
                   return_value=True), \
                patch('registry.tasks.harvest.chord_publish_message_state',
                      return_value=False), \
                patch.object(call_chord_md_metadata_file_to_db, 'delay'):
            watch_import_backlog(self.job.pk, at=at)
            watch_import_backlog(self.job.pk, at=at + INTERVAL)

    def test_the_stall_stands_the_operation_for_a_human(self):
        self.stalled()

        process = self.reported()
        self.assertTrue(process.action_required)
        self.assertEqual(
            OperationStateEnum.ACTION_REQUIRED.value, process.state)
        self.assertIn('import backlog stalled', process.phase)

    def test_the_stall_is_one_state_report_and_no_second_one(self):
        """the watchdog fires per beat over the same stall; the operation
        stands once and its listeners hear about it once (#1205)"""
        self.stalled()
        before = BackgroundProcess.objects.get(
            pk=self.job.background_process_id).revision

        self.stalled(at=timezone.now() + INTERVAL)

        process = self.reported()
        self.assertEqual(before, process.revision)
        self.assertEqual(
            OperationStateEnum.ACTION_REQUIRED.value, process.state)

    def test_the_drain_of_the_backlog_ends_the_stand(self):
        """the first look which finds fewer waiting files ends the stall on the
        job; the operation it reports leaves action-required with it, without
        anybody reporting the progress of a run which still does not move"""
        self.stalled()
        self.records[0].delete()

        with patch('registry.tasks.harvest.import_run_message_state') as ask:
            watch_import_backlog(self.job.pk, at=timezone.now())

        ask.assert_not_called()
        process = self.reported()
        self.assertFalse(process.action_required)
        # the run works again as far as the last report knows: back to the
        # state of a running operation which knows its steps
        self.assertEqual(OperationStateEnum.RUNNING.value, process.state)

    def test_a_run_without_a_process_survives_the_decision(self):
        """the flag of the stall is a report about a process which a job made
        by a bulk write never got - the beat must not die on the missing one"""
        job = HarvestingJob(total_records=2, phase=Phase.RECORDS_TO_DB)
        HarvestingJob.objects.bulk_create([job])
        self.assertIsNone(job.background_process_id)

        watch_import_backlog(job.pk, at=timezone.now())
        with patch('registry.tasks.harvest.import_run_message_state',
                   return_value=True), \
                patch('registry.tasks.harvest.chord_publish_message_state',
                      return_value=False), \
                patch.object(call_chord_md_metadata_file_to_db, 'delay'):
            watch_import_backlog(job.pk, at=timezone.now() + INTERVAL)

        job.refresh_from_db()
        self.assertIsNotNone(job.import_stalled_at)


class WatchImportBacklogsTest(TestCase):
    """The beat round: one fire watches every open import, never one-by-one-blind."""

    def setUp(self):
        self.open = [
            HarvestingJob(total_records=1, phase=Phase.RECORDS_TO_DB),
            HarvestingJob(total_records=1, phase=Phase.RECORDS_TO_DB)]
        HarvestingJob.objects.bulk_create(self.open)
        self.closed = HarvestingJob(total_records=1, phase=Phase.RECORDS_TO_DB,
                                    done_at=timezone.now())
        HarvestingJob.objects.bulk_create([self.closed])

    def test_one_fire_watches_every_open_import(self):
        with patch('registry.tasks.harvest.watch_import_backlog') as look:
            watch_import_backlogs.run()

        watched = {call.args[0] for call in look.call_args_list}
        self.assertEqual(watched, {job.pk for job in self.open})
        self.assertNotIn(self.closed.pk, watched)

    def test_one_unreadable_job_does_not_blind_the_others(self):
        """a job whose row cannot be read - or whose broker question threw - is
        logged and skipped; the next fire is the answer to a briefly dark
        broker, and the other open runs are watched anyway"""
        with patch('registry.tasks.harvest.watch_import_backlog') as look:
            look.side_effect = lambda job_id: (_ for _ in ()).throw(
                ConnectionError('the broker was dark')
            ) if job_id == self.open[0].pk else None
            watch_import_backlogs.run()

        self.assertEqual(look.call_count, 2)


class ImportWatchIntervalTest(TestCase):
    def test_the_watchdog_measures_with_the_settings_interval(self):
        self.assertEqual(import_watch_interval(), INTERVAL)
        with override_settings(HARVEST_IMPORT_WATCH_INTERVAL_MINUTES=13):
            self.assertEqual(
                import_watch_interval(), timezone.timedelta(minutes=13))

    def test_a_config_of_less_than_a_minute_watches_once_a_minute(self):
        """a 0 would make the beat row and the untouched-comb fire per minute
        anyway - the row is keyed per minute and the watchdog never wants to
        race a committing import"""
        with override_settings(HARVEST_IMPORT_WATCH_INTERVAL_MINUTES=0):
            self.assertEqual(import_watch_interval(), timezone.timedelta(minutes=1))


class ImportWatchBeatRowTest(TestCase):
    """Beat reads its schedule from the database, so the watchdog needs its row."""

    def test_the_watchdog_is_scheduled_on_the_watch_interval(self):
        row = PeriodicTask.objects.get(name=IMPORT_WATCH_TASK_NAME)
        self.assertEqual(row.task, 'registry.tasks.harvest.watch_import_backlogs')
        self.assertEqual(row.interval.every,
                         settings.HARVEST_IMPORT_WATCH_INTERVAL_MINUTES)
        self.assertEqual(row.interval.period, IntervalSchedule.MINUTES)

    def test_a_rescheduled_row_survives_the_next_migrate(self):
        """the row is keyed by its name: a deployment which chose its own
        interval over the api keeps it when the handler runs again"""
        from registry.apps import create_import_watch_task

        row = PeriodicTask.objects.get(name=IMPORT_WATCH_TASK_NAME)
        other, _ = IntervalSchedule.objects.get_or_create(
            every=42, period=IntervalSchedule.HOURS)
        row.interval = other
        row.save()

        create_import_watch_task(None)

        self.assertEqual(PeriodicTask.objects.filter(
            name=IMPORT_WATCH_TASK_NAME).count(), 1)
        row.refresh_from_db()
        self.assertEqual(row.interval.every, 42)

    def test_the_row_shares_its_schedule_row_with_equal_schedules(self):
        """django_celery_beat keeps schedules unique per (every, period); the
        watchdog must reuse such a row instead of failing on the unique"""
        twin, _ = IntervalSchedule.objects.get_or_create(
            every=settings.HARVEST_IMPORT_WATCH_INTERVAL_MINUTES,
            period=IntervalSchedule.MINUTES)
        row = PeriodicTask.objects.get(name=IMPORT_WATCH_TASK_NAME)
        self.assertEqual(row.interval_id, twin.id)


class WatchdogBookkeepingStaysPrivateTest(TestCase):
    """What the watchdog answers and what it remembers are different things."""

    def setUp(self):
        self.job = HarvestingJob(total_records=2, phase=Phase.RECORDS_TO_DB)
        HarvestingJob.objects.bulk_create([self.job])
        # the url field of the job is hyperlinked, so the serializer answers
        # its data against a request
        self.request = APIRequestFactory().get('/')

    def test_only_the_stall_state_reaches_the_serializer(self):
        self.job.refresh_from_db()
        serializer = HarvestingJobSerializer(self.job)
        self.assertIn('import_stalled_at', serializer.fields)
        self.assertTrue(serializer.fields['import_stalled_at'].read_only)
        for memory in ('import_backlog_seen', 'import_backlog_seen_at'):
            self.assertNotIn(
                memory, serializer.fields,
                'the watchdog memory is not a field a client hands in or reads')

    def test_a_stalled_run_answers_its_stall_and_a_working_one_nothing(self):
        stalled = HarvestingJob(total_records=2, phase=Phase.RECORDS_TO_DB,
                                import_stalled_at=timezone.now() - INTERVAL)
        HarvestingJob.objects.bulk_create([stalled])

        stalled_data = HarvestingJobSerializer(
            HarvestingJob.objects.with_run_progress().get(pk=stalled.pk),
            context={'request': self.request}).data
        self.assertTrue(stalled_data['import_stalled_at'])
        working_data = HarvestingJobSerializer(
            HarvestingJob.objects.with_run_progress().get(pk=self.job.pk),
            context={'request': self.request}).data
        self.assertIsNone(working_data['import_stalled_at'])
