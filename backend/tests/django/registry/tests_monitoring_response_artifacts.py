"""Tests for the response artifacts of monitoring probe results (#682).

The Monitoring Result Inspector reads what a probe answered at execution
time: the body is kept as an artifact where it is safe and small enough, the
json:api answers of the results stay free of binary payloads and the stored
body is answered by a dedicated authenticated endpoint only. These tests
cover the three paths of #682: the capture within `Probe.run_checks`, the
answers of the result serializers and of the artifact endpoint, and the
retention sweep which takes the bodies back.
"""

import os
import tempfile
from datetime import timedelta
from pathlib import Path
from shutil import rmtree
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from django.utils.timezone import now
from django_celery_beat.models import CrontabSchedule, IntervalSchedule, PeriodicTask
from guardian.shortcuts import assign_perm
from MrMap.settings import BASE_DIR
from registry.apps import (
    PROBE_RESPONSE_ARTIFACT_CLEANUP_TASK_NAME,
    create_probe_response_artifact_cleanup_task)
from registry.models.monitoring import (
    GetCapabilitiesProbe, GetCapabilitiesProbeResult, GetMapProbe,
    GetMapProbeResult, WebMapServiceMonitoringRun,
    WebMapServiceMonitoringSetting,
    purge_expired_probe_response_artifacts)
from registry.models.service import WebMapService
from registry.ows_lib.client.core import OgcClient
from registry.tasks.monitoring import (
    delete_expired_probe_response_artifacts)
from requests.exceptions import ConnectTimeout, RequestException
from rest_framework.test import APIClient
from tests.django.utils import MockResponse

JSONAPI = "application/vnd.api+json"
WMS_PK = "cd16cc1f-3abb-4625-bb96-fbe80dbe23e3"

PNG_FILE = Path(f"{BASE_DIR}/tests/django/test_data/karte_rp.fcgi.png")
EXCEPTION_FILE = Path(
    f"{BASE_DIR}/tests/django/test_data/wms_service_exception.xml")

PNG_BYTES = PNG_FILE.read_bytes()
EXCEPTION_BYTES = EXCEPTION_FILE.read_bytes()

ARTIFACT_URL = "registry:probe-result-response"


def artifact_path(result):
    return reverse(
        ARTIFACT_URL,
        kwargs={"probe_result_type": result._meta.model_name,
                "pk": result.pk})


class MonitoringArtifactTestMixin:
    """A wms with a monitoring run and the media root of the test."""

    fixtures = ["test_users.json", "test_keywords.json", "test_wms.json"]

    def setUp(self):
        super().setUp()
        media = tempfile.mkdtemp()
        self.addCleanup(rmtree, media, True)
        self.override_media(media)
        get_user_model().objects.get_or_create(username="AnonymousUser")
        self.wms = WebMapService.objects.get(pk=WMS_PK)
        self.setup_capabilities()
        self.interval = IntervalSchedule.objects.create(
            every=1, period="days")
        self.setting = WebMapServiceMonitoringSetting.objects.create(
            service=self.wms, interval=self.interval)
        self.run = WebMapServiceMonitoringRun.objects.create(
            setting=self.setting)

    def override_media(self, media):
        # enabled for the whole test and disabled on cleanup: an enabled
        # override which is never disabled leaves MEDIA_ROOT at the deleted
        # temp dir for every test running later in the same process
        override = override_settings(MEDIA_ROOT=media)
        override.enable()
        self.addCleanup(override.disable)

    def setup_capabilities(self):
        """Give the service the capabilities document its client is built of."""
        cap_file = open(
            f"{BASE_DIR}/tests/django/test_data/capabilities/wms/1.1.1.xml",
            mode="rb")
        self.wms.xml_backup_file = ContentFile(
            cap_file.read(), name="capabilities.xml")
        self.wms.save()

    def create_result(self, response, probe=None):
        """Run one get map probe against a mocked response of the service."""
        probe = probe or GetMapProbe.objects.create(setting=self.setting)
        if not probe.layers.exists():
            probe.layers.set(self.wms.layers.all())
        with patch.object(
                OgcClient, "send_request", return_value=response):
            return probe.run_checks(run=self.run)


class ProbeArtifactCaptureTest(MonitoringArtifactTestMixin, TestCase):
    """What `Probe.run_checks` keeps of the response of a probe."""

    def test_get_map_body_is_stored_as_it_was_answered(self):
        result = self.create_result(MockResponse(
            content=PNG_FILE,
            headers={"Content-Type": "image/png"}))

        self.assertTrue(result.has_response_artifact)
        self.assertEqual(result.response_size, len(PNG_BYTES))
        self.assertEqual(result.response_content_type, "image/png")
        with result.response_body.open("rb") as stored:
            self.assertEqual(stored.read(), PNG_BYTES)
        # the name is built from the result, not from the response
        self.assertIn(
            f"probe_responses/registry.getmapproberesult/{result.pk}/",
            result.response_body.name)

    def test_content_type_parameters_do_not_reach_the_record(self):
        result = self.create_result(MockResponse(
            content=EXCEPTION_FILE,
            status_code=400,
            headers={"Content-Type": "application/xml; charset=UTF-8"}))

        self.assertEqual(result.response_content_type, "application/xml")
        self.assertTrue(result.has_response_artifact)

    def test_html_response_is_not_stored_but_recorded(self):
        body = "<html><body>a service error page</body></html>"
        result = self.create_result(MockResponse(
            content=body,
            status_code=500,
            headers={"Content-Type": "text/html; charset=utf-8"}))

        self.assertFalse(result.has_response_artifact)
        self.assertEqual(result.response_size, len(body))
        self.assertEqual(result.response_content_type, "text/html")
        # the failure itself is still readable without the stored body
        self.assertEqual(result.error_detail, body)

    def test_body_over_the_maximum_size_is_not_stored_but_recorded(self):
        with self.settings(MONITORING_PROBE_RESPONSE_MAX_SIZE=10):
            result = self.create_result(MockResponse(
                content=EXCEPTION_FILE,
                headers={"Content-Type": "application/xml"}))

        self.assertFalse(result.has_response_artifact)
        self.assertEqual(result.response_size, len(EXCEPTION_BYTES))
        self.assertEqual(result.response_content_type, "application/xml")

    def test_timeout_is_recorded_as_the_request_error(self):
        probe = GetMapProbe.objects.create(setting=self.setting)
        probe.layers.set(self.wms.layers.all())

        with patch.object(
                OgcClient, "send_request",
                side_effect=ConnectTimeout("connect timed out")):
            result = probe.run_checks(run=self.run)

        self.assertFalse(result.has_response_artifact)
        self.assertIsNone(result.status_code)
        self.assertIn("timed out", result.request_error)

    def test_unreachable_service_is_recorded_as_the_request_error(self):
        probe = GetMapProbe.objects.create(setting=self.setting)
        probe.layers.set(self.wms.layers.all())

        with patch.object(
                OgcClient, "send_request",
                side_effect=RequestException(
                    "HTTPSConnectionPool: Max retries exceeded")):
            result = probe.run_checks(run=self.run)

        self.assertFalse(result.has_response_artifact)
        self.assertIn("Max retries exceeded", result.request_error)

    def test_error_detail_stays_an_excerpt(self):
        long_body = "x" * 5000
        result = self.create_result(MockResponse(
            content=long_body,
            status_code=503,
            headers={"Content-Type": "text/plain"}))

        self.assertEqual(
            len(result.error_detail),
            GetMapProbe.ERROR_DETAIL_MAX_LENGTH)

    def test_get_capabilities_body_is_stored_as_it_was_answered(self):
        probe = GetCapabilitiesProbe.objects.create(setting=self.setting)
        response = MockResponse(
            content=Path(
                f"{BASE_DIR}/tests/django/test_data/dwd_wms_1.3.0.xml"),
            headers={"Content-Type": "text/xml"})

        with patch.object(OgcClient, "send_request", return_value=response):
            result = probe.run_checks(run=self.run)

        self.assertTrue(result.has_response_artifact)
        self.assertEqual(result.response_content_type, "text/xml")
        self.assertIsInstance(result, GetCapabilitiesProbeResult)


class MonitoredUriRedactionTest(SimpleTestCase):
    """The uri of a probe is answered without the values which name a caller."""

    def test_password_in_the_authority_and_token_in_the_query_go(self):
        result = GetMapProbeResult(monitored_uri=(
            "https://user:s3cret@example.de/wms"
            "?token=abc123&width=255&api_key=k4y"))

        redacted = result.redacted_monitored_uri

        self.assertNotIn("s3cret", redacted)
        self.assertNotIn("abc123", redacted)
        self.assertNotIn("k4y", redacted)
        self.assertIn("user:***@example.de", redacted)
        self.assertIn("width=255", redacted)

    def test_authority_without_a_password_keeps_the_user(self):
        result = GetMapProbeResult(
            monitored_uri="https://onlyuser@example.de/wms")

        self.assertEqual(
            result.redacted_monitored_uri,
            "https://onlyuser@example.de/wms")

    def test_ordinary_request_parameters_are_kept(self):
        result = GetMapProbeResult(monitored_uri=(
            "https://example.de/wms?SERVICE=WMS&REQUEST=GetMap"
            "&LAYERS=1&WIDTH=256"))

        self.assertEqual(
            result.redacted_monitored_uri,
            "https://example.de/wms?SERVICE=WMS&REQUEST=GetMap"
            "&LAYERS=1&WIDTH=256")


class ProbeResponseContentEndpointTest(MonitoringArtifactTestMixin,
                                       TestCase):
    """The authenticated endpoint which answers the stored response body."""

    def setUp(self):
        super().setUp()
        self.user = get_user_model().objects.create_superuser(
            username="artifact-admin", password="test")
        self.reader = get_user_model().objects.create_user(
            username="artifact-reader", password="test")
        assign_perm("view_webmapservice", self.reader, self.wms)
        self.api = APIClient()
        self.api.credentials(HTTP_ACCEPT=JSONAPI)

    def stored_result(self):
        result = GetMapProbeResult.objects.create(
            run=self.run,
            monitored_uri="https://example.de/wms",
            status_code=200,
            response_content_type="image/png",
            response_size=len(PNG_BYTES),
            check_response_image_success=True)
        result.response_body = ContentFile(PNG_BYTES, name="response")
        result.save()
        return result

    def test_the_stored_body_is_answered_to_the_authorized(self):
        result = self.stored_result()
        self.api.force_authenticate(self.reader)

        response = self.api.get(artifact_path(result))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "image/png")
        self.assertEqual(response["X-Content-Type-Options"], "nosniff")
        self.assertEqual(response["Cache-Control"], "no-store")
        self.assertIn("inline", response["Content-Disposition"])
        self.assertEqual(b"".join(response.streaming_content), PNG_BYTES)

    def test_the_superuser_without_an_assigned_permission_reads_the_body(self):
        result = self.stored_result()
        self.api.force_authenticate(self.user)

        self.assertEqual(self.api.get(artifact_path(result)).status_code, 200)

    def test_an_authenticated_user_without_permission_is_refused(self):
        result = self.stored_result()
        stranger = get_user_model().objects.create_user(
            username="artifact-stranger", password="test")
        self.api.force_authenticate(stranger)

        self.assertEqual(self.api.get(artifact_path(result)).status_code, 403)

    def test_an_anonymous_request_is_refused(self):
        result = self.stored_result()

        response = self.api.get(artifact_path(result))

        self.assertIn(response.status_code, (401, 403))

    def test_a_result_without_an_artifact_is_no_resource(self):
        result = GetMapProbeResult.objects.create(
            run=self.run,
            monitored_uri="https://example.de/wms",
            status_code=200)
        self.api.force_authenticate(self.user)

        self.assertEqual(self.api.get(artifact_path(result)).status_code, 404)

    def test_a_body_the_storage_does_not_hold_is_no_resource(self):
        result = self.stored_result()
        os.remove(result.response_body.path)
        self.api.force_authenticate(self.user)

        self.assertEqual(self.api.get(artifact_path(result)).status_code, 404)

    def test_an_expired_artifact_is_answered_as_gone(self):
        result = self.stored_result()
        self.api.force_authenticate(self.user)
        with self.settings(MONITORING_PROBE_RESPONSE_RETENTION_DAYS=1):
            response = self.api.get(artifact_path(result))
            self.assertEqual(response.status_code, 200)

            result.date_created = now() - timedelta(days=2)
            result.save()

            gone = self.api.get(artifact_path(result))

        self.assertEqual(gone.status_code, 410)

    def test_an_unknown_result_kind_is_no_resource(self):
        result = self.stored_result()
        self.api.force_authenticate(self.user)

        response = self.api.get(
            f"/api/registry/monitoring/probe-results/nonsense/{result.pk}"
            "/response")

        self.assertEqual(response.status_code, 404)

    def test_the_head_verb_is_answered_like_the_get(self):
        result = self.stored_result()
        self.api.force_authenticate(self.user)

        response = self.api.head(artifact_path(result))

        self.assertEqual(response.status_code, 200)


class ProbeResultSerializerArtifactAnswersTest(MonitoringArtifactTestMixin,
                                               TestCase):
    """The json:api answers carry the execution summary and never the body."""

    def setUp(self):
        super().setUp()
        self.user = get_user_model().objects.create_superuser(
            username="summary-admin", password="test")
        self.api = APIClient()
        self.api.force_authenticate(self.user)
        self.api.credentials(HTTP_ACCEPT=JSONAPI)

    def test_detail_and_list_answer_the_execution_summary(self):
        result = self.create_result(MockResponse(
            content=PNG_FILE,
            headers={"Content-Type": "image/png"}))

        detail = self.api.get(reverse(
            "registry:webmapservicemonitoring-getmap-probe-result-detail",
            kwargs={"pk": result.pk}))

        self.assertEqual(detail.status_code, 200)
        attributes = detail.json()["data"]["attributes"]
        self.assertTrue(attributes["hasResponseArtifact"])
        self.assertEqual(
            attributes["responseArtifactUrl"], artifact_path(result))
        self.assertEqual(attributes["responseContentType"], "image/png")
        self.assertEqual(attributes["responseSize"], len(PNG_BYTES))
        self.assertEqual(attributes["statusCode"], 200)
        self.assertIn("monitoredUri", attributes)
        # the body itself belongs to the artifact endpoint alone
        self.assertNotIn("responseBody", attributes)

        listing = self.api.get(reverse(
            "registry:webmapservicemonitoring-getmap-probe-result-list"))

        self.assertEqual(listing.status_code, 200)
        listed = listing.json()["data"][0]["attributes"]
        self.assertTrue(listed["hasResponseArtifact"])
        # no binary payload of any stored body reaches the list answer
        for resource in listing.json()["data"]:
            self.assertNotIn("responseBody", resource["attributes"])

    def test_a_result_without_an_artifact_answers_no_artifact_url(self):
        result = GetMapProbeResult.objects.create(
            run=self.run, monitored_uri="https://example.de/wms")

        detail = self.api.get(reverse(
            "registry:webmapservicemonitoring-getmap-probe-result-detail",
            kwargs={"pk": result.pk}))

        self.assertEqual(detail.status_code, 200)
        attributes = detail.json()["data"]["attributes"]
        self.assertFalse(attributes["hasResponseArtifact"])
        self.assertIsNone(attributes["responseArtifactUrl"])

    def test_the_answered_uri_hides_the_credentials_of_the_service(self):
        result = GetMapProbeResult.objects.create(
            run=self.run,
            monitored_uri="https://user:pw@example.de/wms?token=abc")

        detail = self.api.get(reverse(
            "registry:webmapservicemonitoring-getmap-probe-result-detail",
            kwargs={"pk": result.pk}))

        attributes = detail.json()["data"]["attributes"]
        self.assertNotIn("pw", attributes["monitoredUri"])
        self.assertNotIn("abc", attributes["monitoredUri"])


class ProbeResponseArtifactRetentionTest(MonitoringArtifactTestMixin,
                                         TestCase):
    """The sweep which takes the stored response bodies back."""

    def stored_result(self, age_days=0):
        result = GetMapProbeResult.objects.create(
            run=self.run,
            monitored_uri="https://example.de/wms",
            status_code=200,
            response_content_type="image/png",
            response_size=len(PNG_BYTES),
            check_response_image_success=True)
        result.response_body = ContentFile(PNG_BYTES, name="response")
        if age_days:
            result.date_created = now() - timedelta(days=age_days)
        result.save()
        return result

    def test_only_the_expired_bodies_are_taken_back(self):
        old = self.stored_result(age_days=40)
        fresh = self.stored_result()
        old_name = old.response_body.name

        with self.settings(MONITORING_PROBE_RESPONSE_RETENTION_DAYS=30):
            summary = purge_expired_probe_response_artifacts()

        self.assertEqual(summary["purged"], 1)
        self.assertFalse(default_storage.exists(old_name))

        old.refresh_from_db()
        self.assertFalse(old.has_response_artifact)
        # the row and its answers stay - only the body went
        self.assertEqual(old.response_content_type, "image/png")
        self.assertEqual(old.response_size, len(PNG_BYTES))
        self.assertTrue(old.check_response_image_success)

        fresh.refresh_from_db()
        self.assertTrue(fresh.has_response_artifact)

    def test_a_retention_of_zero_keeps_every_body(self):
        self.stored_result(age_days=9999)

        with self.settings(MONITORING_PROBE_RESPONSE_RETENTION_DAYS=0):
            summary = purge_expired_probe_response_artifacts()

        self.assertEqual(summary["purged"], 0)
        self.assertEqual(GetMapProbeResult.objects.count(), 1)

    def test_a_body_the_storage_lost_is_cleared_as_well(self):
        old = self.stored_result(age_days=40)
        os.remove(old.response_body.path)

        with self.settings(MONITORING_PROBE_RESPONSE_RETENTION_DAYS=30):
            summary = purge_expired_probe_response_artifacts()

        self.assertEqual(summary["purged"], 1)
        old.refresh_from_db()
        self.assertFalse(old.has_response_artifact)


class ProbeResponseArtifactCleanupTaskTest(MonitoringArtifactTestMixin,
                                           TestCase):
    """The body behind the beat task and what it reports.

    The task is not fired over ``apply()``: its singleton lock is an advisory
    lock of a dedicated database session and the celery run closes its
    connections when it ends (``MrMap/celery.py``), so the fire belongs to no
    ``TestCase`` atomic block - and a ``TransactionTestCase`` would flush all
    tables and take the rows which ``post_migrate`` created for every test
    running later in the same process. The lock itself is the subject of the
    singleton tests of the system app; what belongs to this sweep is the body,
    called here as ``celery`` would have called it.
    """

    def stored_result(self, age_days=0):
        result = GetMapProbeResult.objects.create(
            run=self.run,
            monitored_uri="https://example.de/wms",
            status_code=200,
            response_content_type="image/png",
            response_size=len(PNG_BYTES),
            check_response_image_success=True)
        result.response_body = ContentFile(PNG_BYTES, name="response")
        if age_days:
            result.date_created = now() - timedelta(days=age_days)
        result.save()
        return result

    def test_the_task_reports_what_it_purged(self):
        old = self.stored_result(age_days=40)
        old_name = old.response_body.name

        with self.settings(MONITORING_PROBE_RESPONSE_RETENTION_DAYS=30):
            # the task is bound, so its body receives the task as self
            summary = delete_expired_probe_response_artifacts.run(
                delete_expired_probe_response_artifacts)

        self.assertEqual(summary["purged"], 1)
        self.assertEqual(summary["retention_days"], 30)
        self.assertFalse(default_storage.exists(old_name))


class ProbeResponseArtifactCleanupScheduleTest(TestCase):
    """The schedule beat needs, which the application creates while migrating.

    The row is what makes the sweep run at all - the same contract the slow
    request dump sweep of the system app is tested for.
    """

    @staticmethod
    def scheduled():
        create_probe_response_artifact_cleanup_task(sender=None)
        return PeriodicTask.objects.filter(
            name=PROBE_RESPONSE_ARTIFACT_CLEANUP_TASK_NAME)

    def test_the_sweep_is_scheduled_hourly(self):
        tasks = self.scheduled()

        self.assertEqual(tasks.count(), 1)
        self.assertEqual(
            tasks.get().task,
            "registry.tasks.monitoring."
            "delete_expired_probe_response_artifacts")
        self.assertEqual(tasks.get().crontab.minute, "20")
        self.assertEqual(tasks.get().crontab.hour, "*")
        self.assertTrue(tasks.get().enabled)

    def test_migrating_again_keeps_one_schedule(self):
        """A deployment migrating repeatedly does not sweep twice an hour."""
        tasks = self.scheduled()

        self.assertEqual(tasks.count(), 1)

    def test_a_re_scheduled_sweep_keeps_its_schedule(self):
        """The row is keyed by its name: a schedule chosen over the api of a
        deployment belongs to the deployment and is not overruled."""
        every_minute, _ = CrontabSchedule.objects.get_or_create(minute="*")
        self.scheduled().update(crontab=every_minute)

        tasks = self.scheduled()

        self.assertEqual(tasks.count(), 1)
        self.assertEqual(tasks.get().crontab_id, every_minute.pk)

    def test_a_staggered_row_on_the_same_minute_does_not_break_the_hook(self):
        """A deployment which staggers per-service tasks over the minute grid
        (system/fields.py) legitimately holds a row at twenty past with any
        hour. The hook asks its schedule by the whole shape and finds its own
        hourly row; the bare minute lookup answered all of those rows and
        django_celery_beat raised MultipleObjectsReturned, which took the
        whole migrate down (#1273)."""
        CrontabSchedule.objects.create(minute="20", hour="3")

        tasks = self.scheduled()

        self.assertEqual(tasks.count(), 1)
        self.assertEqual(tasks.get().crontab.minute, "20")
        self.assertEqual(tasks.get().crontab.hour, "*")
