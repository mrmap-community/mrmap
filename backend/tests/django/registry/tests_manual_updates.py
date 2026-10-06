from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.db import IntegrityError
from django.test import TestCase
from django.urls import reverse
from django_celery_beat.models import IntervalSchedule
from guardian.shortcuts import assign_perm
from registry.enums.update import UpdateJobStatusEnum
from registry.models import (
    CatalogueService, CatalogueServiceUpdateJob, CatalogueServiceUpdateSetting,
    WebFeatureService, WebFeatureServiceUpdateJob, WebFeatureServiceUpdateSetting,
    WebMapService, WebMapServiceUpdateJob, WebMapServiceUpdateSetting,
)
from registry.serializers.update import WebMapServiceUpdateJobSerializer
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIClient


class ManualUpdateTests(TestCase):
    fixtures = ["test_users.json", "test_keywords.json", "test_crs.json",
                "test_wms.json", "test_wfs.json", "test_datasetmetadata.json", "test_csw.json"]

    def setUp(self):
        self.user = get_user_model().objects.create_superuser(
            username="manual-updates", password="test")
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.service = WebMapService.objects.first()
        self.url = reverse("registry:webmapserviceupdatejob-list")

    def payload(self, service):
        return {"data": {
            "type": f"{type(service).__name__}UpdateJob",
            "relationships": {"service": {"data": {
                "type": type(service).__name__, "id": str(service.pk),
            }}},
        }}

    def post(self, service=None, url=None):
        return self.client.post(url or self.url, self.payload(service or self.service),
                                format="vnd.api+json")

    def test_manual_updates_without_settings_and_with_disabled_settings(self):
        for service_model, job_model, setting_model, runner in (
            (WebMapService, WebMapServiceUpdateJob, WebMapServiceUpdateSetting, "wms"),
            (WebFeatureService, WebFeatureServiceUpdateJob, WebFeatureServiceUpdateSetting, "wfs"),
            (CatalogueService, CatalogueServiceUpdateJob, CatalogueServiceUpdateSetting, "csw"),
        ):
            with self.subTest(service=service_model.__name__):
                service = service_model.objects.first()
                url = reverse(f"registry:{job_model._meta.model_name}-list")
                setting_model.objects.filter(service=service).delete()
                for disabled_setting in (False, True):
                    if disabled_setting:
                        interval = IntervalSchedule.objects.create(every=1, period="days")
                        setting = setting_model.objects.create(
                            service=service, interval=interval, enabled=False)
                        original = setting_model.objects.filter(pk=setting.pk).values().get()
                    with patch(f"registry.tasks.update.run_{runner}_update.apply_async") as enqueue:
                        with self.captureOnCommitCallbacks(execute=True):
                            response = self.post(service, url)
                            self.assertEqual(response.status_code, 201, response.data)
                            enqueue.assert_not_called()
                        job = job_model.objects.get(service=service, done_at__isnull=True)
                        enqueue.assert_called_once_with(kwargs={"update_job_id": job.pk})
                    if disabled_setting:
                        self.assertEqual(setting_model.objects.filter(pk=setting.pk).values().get(), original)
                    else:
                        self.assertFalse(setting_model.objects.filter(service=service).exists())
                    job.finish()

    def test_unfinished_jobs_including_review_block_creation(self):
        finished = WebMapServiceUpdateJob.objects.create(service=self.service)
        finished.finish()
        job = WebMapServiceUpdateJob.objects.create(service=self.service)
        for status in (UpdateJobStatusEnum.WAITING_FOR_PROCESSING, UpdateJobStatusEnum.REVIEW_REQUIRED):
            job.status = status.value
            job.save()
            response = self.post()
            self.assertEqual(response.status_code, 400, response.data)
        self.assertEqual(WebMapServiceUpdateJob.objects.filter(service=self.service, done_at__isnull=True).count(), 1)
        response = self.client.get(self.url, {"filter[doneAt.isnull]": "true"})
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(len(response.data["results"]), 1)

    def test_race_after_validation_returns_validation_error(self):
        serializer = WebMapServiceUpdateJobSerializer()
        WebMapServiceUpdateJob.objects.create(service=self.service)
        with self.assertRaises(ValidationError):
            serializer.create({"service": self.service})

    def test_unrelated_integrity_errors_are_not_hidden(self):
        with patch.object(WebMapServiceUpdateJob.objects, "create", side_effect=IntegrityError("other")):
            with self.assertRaises(IntegrityError):
                WebMapServiceUpdateJobSerializer().create({"service": self.service})

    def test_permissions_require_job_creation_and_service_change(self):
        self.client.force_authenticate(user=None)
        self.assertEqual(self.post().status_code, 403)
        user = get_user_model().objects.create_user(username="manual-operator")
        self.client.force_authenticate(user)
        self.assertEqual(self.post().status_code, 403)
        user.user_permissions.add(Permission.objects.get(codename="add_webmapserviceupdatejob"))
        self.client.force_authenticate(get_user_model().objects.get(pk=user.pk))
        self.assertEqual(self.post().status_code, 403)
        assign_perm("registry.change_webmapservice", user, self.service)
        self.client.force_authenticate(get_user_model().objects.get(pk=user.pk))
        self.assertEqual(self.post().status_code, 201)
