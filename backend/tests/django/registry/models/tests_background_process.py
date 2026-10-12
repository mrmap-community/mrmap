from unittest.mock import patch

from django.test import TestCase
from django_celery_beat.models import IntervalSchedule
from notify.enums import ProcessNameEnum, ProcessStatusEnum
from notify.models import BackgroundProcess, BackgroundProcessLog
from registry.enums.update import UpdateJobStatusEnum
from registry.models.monitoring import (WebFeatureServiceMonitoringRun,
                                        WebFeatureServiceMonitoringSetting)
from registry.models.service import WebFeatureService, WebMapService
from registry.models.update import WebMapServiceUpdateJob

WFS_PK = "9cc4889d-0cd4-4c3b-8975-58de6d30db41"
WMS_PK = "cd16cc1f-3abb-4625-bb96-fbe80dbe23e3"


class MonitoringRunBackgroundProcessTests(TestCase):
    """Tests how a monitoring run reports itself in the background activity.

    A monitoring run is work which is done by workers without a request to
    attach a process to, so the run creates its process while it is created and
    the tasks of the run keep it up to date until the run ended.
    """

    fixtures = ["test_users.json", "test_keywords.json", "test_crs.json",
                "test_wfs.json"]

    def setUp(self):
        self.service = WebFeatureService.objects.get(pk=WFS_PK)
        self.setting = WebFeatureServiceMonitoringSetting.objects.create(
            service=self.service,
            interval=IntervalSchedule.objects.create(every=1, period="days"))
        self.run = WebFeatureServiceMonitoringRun.objects.create(
            setting=self.setting)

    def process(self):
        return BackgroundProcess.objects.process_info().get(
            pk=self.run.background_process_id)

    def test_creating_a_run_creates_the_process_which_reports_it(self):
        process = self.process()

        self.assertEqual(1, BackgroundProcess.objects.count())
        self.assertEqual(ProcessNameEnum.MONITORING.value, process.process_type)
        self.assertEqual(ProcessStatusEnum.PENDING, process.status)
        self.assertIsNone(process.total_steps)
        self.assertEqual(self.service, process.service)

    def test_a_run_keeps_the_process_which_was_given_to_it(self):
        given = BackgroundProcess.objects.create(
            phase="given by the task",
            process_type=ProcessNameEnum.MONITORING.value,
            description="the task which schedules the run made a process")
        run = WebFeatureServiceMonitoringRun.objects.create(
            setting=self.setting, background_process=given)

        self.assertEqual(given.pk, run.background_process_id)
        self.assertEqual(2, BackgroundProcess.objects.count())

    def test_the_process_of_a_run_counts_the_checks_it_ran(self):
        self.run.report_process(
            ProcessStatusEnum.RUNNING, phase="Running 2 checks", total_steps=2)
        for _ in range(2):
            self.run.report_process(ProcessStatusEnum.RUNNING, step_done=True)

        process = self.process()
        self.assertEqual(ProcessStatusEnum.RUNNING, process.status)
        self.assertEqual("Running 2 checks", process.phase)
        self.assertEqual(2, process.done_steps)
        self.assertEqual(100.0, process.progress)

    def test_a_run_which_cannot_run_reports_a_failed_process_with_a_log(self):
        self.run.fail_process(ConnectionError("the remote did not answer"))

        process = self.process()
        self.assertEqual(ProcessStatusEnum.FAILED, process.status)
        self.assertIsNotNone(process.done_at)
        self.assertIn(
            "the remote did not answer",
            BackgroundProcessLog.objects.get(
                background_process=process).description)

    @patch.object(BackgroundProcess, "get_related_task_ids", return_value=[])
    def test_the_process_of_a_run_stays_aborted_while_the_run_finishes(
            self, related_tasks):
        process = BackgroundProcess.objects.get(pk=self.run.background_process_id)
        process.phase = "abort"
        process.save()

        self.run.report_process(ProcessStatusEnum.COMPLETED)

        self.assertEqual(ProcessStatusEnum.ABORTED, self.process().status)

    @patch.object(BackgroundProcess, "get_related_task_ids", return_value=[])
    def test_a_run_still_creates_its_process_when_the_broker_is_unreachable(
            self, related_tasks):
        self.assertEqual(1, BackgroundProcess.objects.count())


class UpdateJobBackgroundProcessTests(TestCase):
    """Tests how an update job reports itself in the background activity.

    An update job is queued while it still waits for a worker, so its process is
    what makes the job distinguishable in the overview of the background
    activity. A job which waits for a review is not finished, therefore its
    process keeps running until the mapping is confirmed.
    """

    fixtures = ["test_users.json", "test_keywords.json", "test_crs.json",
                "test_wms.json"]

    def setUp(self):
        self.service = WebMapService.objects.get(pk=WMS_PK)
        self.job = WebMapServiceUpdateJob.objects.create(service=self.service)

    def process(self):
        return BackgroundProcess.objects.process_info().get(
            pk=self.job.background_process_id)

    def decide(self, status):
        self.job.status = status
        self.job.save()
        return self.process()

    def test_creating_a_job_creates_the_process_which_reports_it(self):
        process = self.process()

        self.assertEqual(1, BackgroundProcess.objects.count())
        self.assertEqual(ProcessNameEnum.UPDATE.value, process.process_type)
        self.assertEqual(ProcessStatusEnum.PENDING, process.status)
        self.assertEqual(self.service, process.service)

    def test_a_job_which_is_taken_reports_a_running_process(self):
        self.assertEqual(
            ProcessStatusEnum.RUNNING,
            self.decide(UpdateJobStatusEnum.UPDATING).status)

    def test_a_job_which_waits_for_a_review_still_reports_a_running_process(
            self):
        process = self.decide(UpdateJobStatusEnum.REVIEW_REQUIRED)

        self.assertEqual(ProcessStatusEnum.RUNNING, process.status)
        self.assertIsNone(process.done_at)

    def test_a_job_with_an_error_reports_a_failed_process(self):
        process = self.decide(UpdateJobStatusEnum.ERROR)

        self.assertEqual(ProcessStatusEnum.FAILED, process.status)
        self.assertIsNotNone(process.done_at)
        self.assertIn(
            str(UpdateJobStatusEnum.ERROR.label), process.phase)

    def test_a_finished_job_reports_a_completed_process(self):
        self.assertEqual(
            ProcessStatusEnum.COMPLETED,
            self.decide(UpdateJobStatusEnum.NO_UPDATE_NEEDED).status)

    def test_the_process_of_a_finished_job_is_not_moved_anymore(self):
        self.decide(UpdateJobStatusEnum.UPDATED)

        process = self.decide(UpdateJobStatusEnum.ERROR)

        self.assertEqual(ProcessStatusEnum.COMPLETED, process.status)
