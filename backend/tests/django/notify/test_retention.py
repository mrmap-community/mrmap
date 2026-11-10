import uuid
from datetime import timedelta

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.test import TestCase, override_settings
from django.utils.timezone import now
from django_celery_beat.models import PeriodicTask
from django_celery_results.models import TaskResult
from notify.apps import BACKGROUND_PROCESS_CLEANUP_TASK_NAME, \
    create_background_process_cleanup_task
from notify.enums import LogTypeEnum, ProcessNameEnum, ProcessStatusEnum
from notify.models import BackgroundProcess, BackgroundProcessLog, \
    purge_expired_background_processes
from notify.tasks import delete_expired_background_processes


class BackgroundProcessRetentionTests(TestCase):
    """Tests the sweep which bounds the job history (#1208).

    Every background operation leaves a process row behind, so the history of
    the job drawer would grow without bound if nothing took the decided
    processes back. Only processes which decided about themselves are of that
    kind, only after the retention window, and the log entries of a purged
    process - their stored files included - go with it.
    """

    def create(self, status, created_days_ago=0, decided_days_ago=None,
               with_log=False):
        """A process which ended ``decided_days_ago`` days ago.

        Without a decision moment the process is terminal only if its status
        says so - which is the shape a worker leaves behind when it died
        before stamping the completion.
        """
        process = BackgroundProcess.objects.create(
            phase="a phase",
            process_type=ProcessNameEnum.MONITORING.value,
            description="a process",
            status=status,
            date_created=now() - timedelta(days=created_days_ago),
            done_at=now() - timedelta(
                days=decided_days_ago) if decided_days_ago is not None else None)
        if with_log:
            log = BackgroundProcessLog.objects.create(
                background_process=process,
                log_type=LogTypeEnum.ERROR,
                description="an error")
            log.extented_description = ContentFile(
                b"the response which failed", name="response.txt")
            log.save()
        return process

    def test_takes_back_only_the_decided_processes_of_the_expired_window(self):
        gone = self.create(ProcessStatusEnum.FAILED,
                           created_days_ago=40, decided_days_ago=40,
                           with_log=True)
        gone_log = gone.logs.get()
        stored_file = gone_log.extented_description.name
        # the same retention answers a process which completed long ago, while
        # it was created even longer ago
        self.create(ProcessStatusEnum.COMPLETED, created_days_ago=200,
                    decided_days_ago=40)
        too_young = self.create(ProcessStatusEnum.COMPLETED,
                                created_days_ago=10, decided_days_ago=10)

        summary = purge_expired_background_processes(retention_days=30)

        self.assertEqual(summary["retention_days"], 30)
        self.assertEqual(summary["purged"], 2)
        self.assertEqual(summary["logs"], 1)
        self.assertEqual(summary["files"], 1)
        self.assertFalse(BackgroundProcess.objects.filter(pk=gone.pk).exists())
        self.assertFalse(
            BackgroundProcessLog.objects.filter(pk=gone_log.pk).exists())
        self.assertFalse(default_storage.exists(stored_file))
        self.assertTrue(BackgroundProcess.objects.filter(
            pk=too_young.pk).exists())

    def test_a_terminal_process_without_a_decision_falls_back_on_creation(self):
        # done_at is the moment of the decision; a terminal row which names
        # none cannot stay in the history forever only because a stamp is
        # missing
        abandoned = self.create(ProcessStatusEnum.FAILED,
                                created_days_ago=40, decided_days_ago=None)

        summary = purge_expired_background_processes(retention_days=30)

        self.assertEqual(summary["purged"], 1)
        self.assertFalse(
            BackgroundProcess.objects.filter(pk=abandoned.pk).exists())

    def test_a_process_which_did_not_end_is_never_purged(self):
        for status in (ProcessStatusEnum.PENDING, ProcessStatusEnum.RUNNING):
            self.create(status, created_days_ago=400, decided_days_ago=None)

        summary = purge_expired_background_processes(retention_days=30)

        self.assertEqual(summary["purged"], 0)
        self.assertEqual(BackgroundProcess.objects.count(), 2)

    def test_the_retention_of_the_deployment_decides_by_default(self):
        decided = self.create(ProcessStatusEnum.ABORTED, created_days_ago=8,
                              decided_days_ago=8)

        with self.settings(BACKGROUND_PROCESS_RETENTION_DAYS=7):
            summary = purge_expired_background_processes()

        self.assertEqual(summary["retention_days"], 7)
        self.assertEqual(summary["purged"], 1)
        self.assertFalse(
            BackgroundProcess.objects.filter(pk=decided.pk).exists())

    @override_settings(BACKGROUND_PROCESS_RETENTION_DAYS=0)
    def test_a_retention_of_zero_keeps_every_process(self):
        # an operator who wants to look at the past of a deployment keeps it
        # until he removes it himself
        self.create(ProcessStatusEnum.COMPLETED, created_days_ago=9999,
                    decided_days_ago=9999, with_log=True)

        summary = purge_expired_background_processes()

        self.assertEqual(summary, {
            "retention_days": 0, "purged": 0, "logs": 0, "files": 0})
        self.assertEqual(BackgroundProcess.objects.count(), 1)

    def test_the_thread_rows_of_a_purged_process_survive(self):
        # a TaskResult row belongs to the api which published it (#1176), not
        # to the history which reports it
        decided = self.create(ProcessStatusEnum.COMPLETED,
                              created_days_ago=40, decided_days_ago=40)
        thread = TaskResult.objects.create(task_id=str(uuid.uuid4()))
        decided.threads.add(thread)

        purge_expired_background_processes(retention_days=30)

        self.assertTrue(TaskResult.objects.filter(pk=thread.pk).exists())

    def test_the_task_reports_what_it_purged(self):
        gone = self.create(ProcessStatusEnum.FAILED, created_days_ago=40,
                           decided_days_ago=40, with_log=True)
        gone_log = gone.logs.get()
        stored_file = gone_log.extented_description.name

        with self.settings(BACKGROUND_PROCESS_RETENTION_DAYS=30):
            # the task is bound, so its body receives the task as self
            summary = delete_expired_background_processes.run(
                delete_expired_background_processes)

        self.assertEqual(summary["purged"], 1)
        self.assertEqual(summary["logs"], 1)
        self.assertEqual(summary["retention_days"], 30)
        self.assertFalse(default_storage.exists(stored_file))


class BackgroundProcessCleanupScheduleTest(TestCase):
    """The schedule beat needs, which the application creates while migrating.

    The row is what makes the sweep run at all - the same contract the slow
    request dump sweep and the probe artifact sweep are tested for.
    """

    @staticmethod
    def scheduled():
        create_background_process_cleanup_task(sender=None)
        return PeriodicTask.objects.filter(
            name=BACKGROUND_PROCESS_CLEANUP_TASK_NAME)

    def test_the_sweep_is_scheduled_hourly(self):
        tasks = self.scheduled()

        self.assertEqual(tasks.count(), 1)
        self.assertEqual(
            tasks.get().task,
            "notify.tasks.delete_expired_background_processes")
        self.assertEqual(tasks.get().crontab.minute, "30")
        self.assertEqual(tasks.get().crontab.hour, "*")
        self.assertTrue(tasks.get().enabled)

    def test_migrating_again_keeps_one_schedule(self):
        """A deployment migrating repeatedly does not sweep twice an hour."""
        tasks = self.scheduled()

        self.assertEqual(tasks.count(), 1)
