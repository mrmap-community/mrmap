from unittest.mock import patch
from uuid import uuid4

from django.test import TestCase
from django_celery_beat.models import IntervalSchedule
from notify.enums import ProcessNameEnum, ProcessStatusEnum
from notify.models import BackgroundProcess, BackgroundProcessLog
from registry.enums.harvesting import HarvestingPhaseEnum
from registry.enums.update import UpdateJobStatusEnum
from registry.models.harvest import HarvestingJob
from registry.models.monitoring import (WebFeatureServiceMonitoringRun,
                                        WebFeatureServiceMonitoringSetting)
from registry.models.service import (CatalogueService, WebFeatureService,
                                     WebMapService)
from registry.models.update import WebMapServiceUpdateJob
from registry.querys.harvest_history import complete_harvest
from registry.tasks.harvest import call_fetch_records
from requests.exceptions import Timeout

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


class HarvestingJobBackgroundProcessTests(TestCase):
    """Tests how a harvesting job reports itself in the background activity.

    A harvest is long running work which is done by workers without a request
    to attach a process to, so the job creates its process while it is created
    and the phases the job runs through keep it up to date until the job
    decided about itself. Without that the overview of the background activity
    would only show the registrations of the deployment while whole catalogues
    are being harvested next to them (#809).
    """

    fixtures = ["test_users.json", "test_keywords.json", "test_crs.json",
                "test_csw.json"]

    CSW_PK = "9cc4889d-0cd4-4c3b-8975-58de6d30db41"

    def setUp(self):
        self.service = CatalogueService.objects.get(pk=self.CSW_PK)

    def create_job(self, **kwargs):
        with patch('celery.canvas.Signature.apply_async'):
            return HarvestingJob.objects.create(service=self.service, **kwargs)

    def process(self, job):
        return BackgroundProcess.objects.process_info().get(
            pk=job.background_process_id)

    def test_creating_a_job_creates_the_process_which_reports_it(self):
        job = self.create_job()

        process = self.process(job)

        self.assertEqual(1, BackgroundProcess.objects.count())
        self.assertEqual(ProcessNameEnum.HARVESTING.value, process.process_type)
        self.assertEqual(ProcessStatusEnum.PENDING, process.status)
        self.assertEqual(self.service, process.service)

    def test_a_job_keeps_the_process_which_was_given_to_it(self):
        given = BackgroundProcess.objects.create(
            phase="records to db",
            process_type=ProcessNameEnum.HARVESTING.value,
            description="the import which scheduled the files made a process")
        job = HarvestingJob.objects.create(total_records=3,
                                           background_process=given)

        self.assertEqual(given.pk, job.background_process_id)
        self.assertEqual(1, BackgroundProcess.objects.count())

    def test_the_download_phase_of_a_job_reports_a_running_process(self):
        job = self.create_job()
        job.total_records = 10

        with patch('registry.models.harvest.chord'):
            job.handle_total_records_defined()

        process = self.process(job)

        self.assertEqual(ProcessStatusEnum.RUNNING, process.status)
        self.assertEqual("download records", process.phase)
        self.assertEqual(12, process.total_steps)

    def test_a_job_without_records_reports_a_completed_process(self):
        job = self.create_job()
        job.total_records = 0

        job.save()

        process = self.process(job)

        self.assertEqual(ProcessStatusEnum.COMPLETED, process.status)
        self.assertIsNotNone(process.done_at)
        self.assertEqual(100.0, process.progress)

    def test_a_completed_harvest_reports_a_completed_process(self):
        job = self.create_job()
        HarvestingJob.objects.filter(pk=job.pk).update(
            phase=HarvestingPhaseEnum.RECORDS_TO_DB.value, total_records=5)
        job.refresh_from_db()

        complete_harvest(job.pk)

        process = self.process(job)

        self.assertEqual(ProcessStatusEnum.COMPLETED, process.status)
        self.assertIsNotNone(process.done_at)
        self.assertEqual(100.0, process.progress)

    def test_an_aborted_job_reports_an_aborted_process(self):
        job = self.create_job()

        with patch('celery.app.control.Control.revoke'):
            job.phase = HarvestingPhaseEnum.ABORT.value
            job.save()

        process = self.process(job)

        self.assertEqual(ProcessStatusEnum.ABORTED, process.status)
        self.assertIsNotNone(process.done_at)

    def test_a_task_which_gave_up_reports_a_failed_process_with_a_log(self):
        job = self.create_job()
        HarvestingJob.objects.filter(pk=job.pk).update(
            phase=HarvestingPhaseEnum.DOWNLOAD_RECORDS.value)
        call_fetch_records.push_request(retries=3)
        self.addCleanup(call_fetch_records.pop_request)

        with patch('celery.app.control.Control.revoke'):
            call_fetch_records.on_failure(
                Timeout('the catalogue is offline'), str(uuid4()), (),
                {'harvesting_job_id': job.pk, 'start_position': 51}, None)

        process = self.process(job)

        self.assertEqual(ProcessStatusEnum.FAILED, process.status)
        self.assertIsNotNone(process.done_at)
        self.assertIn("Timeout: the catalogue is offline", process.phase)
        self.assertIn(
            "An error occurred: Timeout: the catalogue is offline",
            BackgroundProcessLog.objects.get(
                background_process=process).description)

    def test_the_process_of_a_decided_job_is_not_moved_anymore(self):
        job = self.create_job()
        HarvestingJob.objects.filter(pk=job.pk).update(
            phase=HarvestingPhaseEnum.RECORDS_TO_DB.value, total_records=5)
        job.refresh_from_db()
        complete_harvest(job.pk)

        job.refresh_from_db()
        job.phase = HarvestingPhaseEnum.ABORT.value
        with patch('celery.app.control.Control.revoke'):
            job.save()

        self.assertEqual(
            ProcessStatusEnum.COMPLETED, self.process(job).status)
