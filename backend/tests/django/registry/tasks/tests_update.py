from unittest.mock import patch

from django.db import IntegrityError, transaction
from django.test import TestCase
from django_celery_beat.models import IntervalSchedule
from notify.models import BackgroundProcess
from registry.enums.update import UpdateJobStatusEnum
from registry.models.service import CatalogueService, WebFeatureService
from registry.models.update import (
    CatalogueServiceUpdateJob, CatalogueServiceUpdateSetting,
    WebFeatureServiceUpdateJob, WebFeatureServiceUpdateSetting,
)
from registry.tasks.update import create_csw_update_job, create_wfs_update_job


class PeriodicUpdateJobTest(TestCase):
    fixtures = [
        "test_users.json", "test_keywords.json", "test_crs.json",
        "test_wfs.json", "test_csw.json",
    ]
    cases = (
        (WebFeatureService, WebFeatureServiceUpdateJob,
         WebFeatureServiceUpdateSetting, create_wfs_update_job, "run_wfs_update"),
        (CatalogueService, CatalogueServiceUpdateJob,
         CatalogueServiceUpdateSetting, create_csw_update_job, "run_csw_update"),
    )

    def setUp(self):
        self.interval = IntervalSchedule.objects.create(every=1, period="days")

    def test_reuses_unfinished_jobs_without_enqueueing(self):
        for service_model, job_model, setting_model, create_job, runner in self.cases:
            service = service_model.objects.first()
            setting = setting_model.objects.create(service=service, interval=self.interval)
            for status in (
                UpdateJobStatusEnum.WAITING_FOR_PROCESSING,
                UpdateJobStatusEnum.UPDATING,
                UpdateJobStatusEnum.REVIEW_REQUIRED,
                UpdateJobStatusEnum.RESUME,
            ):
                with self.subTest(service=service_model.__name__, status=status):
                    job = job_model.objects.create(service=service, status=status.value)
                    process_count = BackgroundProcess.objects.count()
                    with patch(f"registry.tasks.update.{runner}.apply_async") as enqueue:
                        with self.captureOnCommitCallbacks(execute=True):
                            for _ in range(2):
                                self.assertEqual(create_job(name=setting.name), job.pk)
                        enqueue.assert_not_called()
                    job.refresh_from_db()
                    self.assertEqual(job.status, status.value)
                    self.assertIsNone(job.done_at)
                    self.assertEqual(service.update_jobs.filter(done_at__isnull=True).count(), 1)
                    self.assertEqual(BackgroundProcess.objects.count(), process_count)
                    job.finish()

    def test_creates_and_enqueues_after_previous_job_finished(self):
        for service_model, job_model, setting_model, create_job, runner in self.cases:
            with self.subTest(service=service_model.__name__):
                service = service_model.objects.first()
                setting = setting_model.objects.create(service=service, interval=self.interval)
                for status in (
                    UpdateJobStatusEnum.UPDATED,
                    UpdateJobStatusEnum.NO_UPDATE_NEEDED,
                    UpdateJobStatusEnum.ERROR,
                ):
                    job_model.objects.create(service=service).finish(status)
                with patch(f"registry.tasks.update.{runner}.apply_async") as enqueue:
                    with self.captureOnCommitCallbacks(execute=True):
                        job_id = create_job(name=setting.name)
                        enqueue.assert_not_called()
                    enqueue.assert_called_once_with(kwargs={"update_job_id": job_id})
                self.assertEqual(service.update_jobs.count(), 4)
                self.assertEqual(service.update_jobs.filter(done_at__isnull=True).get().pk, job_id)

    def test_different_services_have_independent_jobs(self):
        for service_model, job_model, setting_model, create_job, runner in self.cases:
            with self.subTest(service=service_model.__name__):
                first, second = list(service_model.objects.all()[:2])
                existing = job_model.objects.create(service=first)
                setting = setting_model.objects.create(service=second, interval=self.interval)
                with patch(f"registry.tasks.update.{runner}.apply_async") as enqueue:
                    with self.captureOnCommitCallbacks(execute=True):
                        job_id = create_job(name=setting.name)
                    enqueue.assert_called_once_with(kwargs={"update_job_id": job_id})
                self.assertNotEqual(job_id, existing.pk)
                self.assertEqual(job_model.objects.get(pk=job_id).service_id, second.pk)

    def test_multiple_schedules_for_same_service_reuse_job(self):
        for service_model, job_model, setting_model, create_job, runner in self.cases:
            with self.subTest(service=service_model.__name__):
                service = service_model.objects.first()
                settings = [setting_model.objects.create(service=service, interval=self.interval)
                            for _ in range(2)]
                with patch(f"registry.tasks.update.{runner}.apply_async") as enqueue:
                    with self.captureOnCommitCallbacks(execute=True):
                        job_ids = [create_job(name=setting.name) for setting in settings]
                    enqueue.assert_called_once_with(kwargs={"update_job_id": job_ids[0]})
                self.assertEqual(job_ids[0], job_ids[1])
                self.assertEqual(service.update_jobs.count(), 1)

    def test_database_rejects_duplicate_unfinished_jobs(self):
        for service_model, job_model, _, _, _ in self.cases:
            with self.subTest(service=service_model.__name__):
                service = service_model.objects.first()
                job_model.objects.create(service=service)
                with self.assertRaises(IntegrityError), transaction.atomic():
                    job_model.objects.create(service=service)
