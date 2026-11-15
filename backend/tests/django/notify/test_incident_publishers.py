"""Tests of the retry/failure incident publishers (#1320).

These tests call the seams the publishers are connected to - the
``task_retry`` and ``task_success`` signal handlers and the terminal
failure report - with the same shapes celery dispatches, and answer the
acceptance criteria of #1320 against the persisted incidents: ten retries
are one active incident with a moving count, exhaustion is the same
incident turning error, an authoritative success resolves, credentials
never reach the stored payload, and races of one problem keep one row.

The signals are called as functions on purpose: the celery machinery
around ``apply()`` would run the whole trace, while what is under test is
what the receivers write, from what the dispatch hands them.
"""
import threading
import uuid
from datetime import timedelta
from types import SimpleNamespace

from celery.exceptions import MaxRetriesExceededError
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase, TransactionTestCase
from django.utils.timezone import now
from notify.enums import (IncidentSeverityEnum, IncidentStatusEnum,
                          ProcessStatusEnum)
from notify.incident_reporting import (operation_code,
                                       publish_terminal_failure,
                                       publish_task_retry,
                                       resolve_on_task_success,
                                       scrub_secret_text)
from notify.models import BackgroundProcess, OperationalIncident
from registry.models.service import CatalogueService, WebMapService

#: the catalogue of ``test_csw.json``
CSW_PK = "9cc4889d-0cd4-4c3b-8975-58de6d30db41"

TASK_NAME = "registry.tasks.harvest.fetch_md_metadata"


class FakeTask:
    """The sender shape of the celery task signals.

    A signal sends the task class; the publishers read only its ``name``
    and, through ``retry_scheduled_at`` of #1207, its backoff attributes
    when a reason carries no explicit moment. The backoff attributes are
    the ones of ``BackgroundProcessBased`` so the fallback path sees the
    real shape too.
    """
    name = TASK_NAME
    retry_backoff = 30
    retry_backoff_max = 5 * 60
    retry_jitter = False


class FakeRequest:
    """The request shape: the process kwarg and the retries counter."""

    def __init__(self, process_pk, retries=0):
        self.kwargs = {"background_process_pk": str(process_pk)}
        self.retries = retries


def retry_reason(message="the service did not answer", when=None):
    """The ``Retry`` shape of #1207: safe repr text and a due moment."""
    return SimpleNamespace(
        excs=message, message=message,
        when=when if when is not None else now() + timedelta(minutes=1))


class PublisherTestMixin:
    """The process one publisher test reports about."""

    def build_process(self, process_type="harvesting", related=None):
        content_type = None
        related_id = None
        if related is not None:
            content_type = ContentType.objects.get_for_model(related)
            related_id = related.pk
        return BackgroundProcess.objects.create(
            process_type=process_type, phase="working",
            description="a process which the publishers report about",
            related_resource_type=content_type, related_id=related_id)

    def retry(self, process, retries=0, **reason_kwargs):
        publish_task_retry(
            sender=FakeTask(), request=FakeRequest(process.pk, retries),
            reason=retry_reason(**reason_kwargs))

    def succeed(self, process):
        resolve_on_task_success(
            sender=FakeTask(),
            kwargs={"background_process_pk": str(process.pk)})

    def active(self):
        return OperationalIncident.objects.filter(
            status=IncidentStatusEnum.ACTIVE.value)


class RetryIncidentTests(PublisherTestMixin, TestCase):
    """Retries of one operation are one incident whose count moves."""

    fixtures = ["test_users.json", "test_keywords.json", "test_crs.json",
                "test_wms.json", "test_csw.json"]

    def setUp(self):
        self.catalogue = CatalogueService.objects.get(pk=CSW_PK)
        self.process = self.build_process(related=self.catalogue)

    def test_ten_retries_are_one_active_incident_with_a_moving_count(self):
        """The epic's own test case for #1320, on the real signal path."""
        for attempt in range(10):
            self.retry(self.process, retries=attempt)

        incidents = OperationalIncident.objects.all()
        self.assertEqual(incidents.count(), 1,
                         "ten retries created more than one incident")
        incident = incidents.first()
        self.assertEqual(incident.occurrence_count, 10)
        self.assertEqual(incident.status, IncidentStatusEnum.ACTIVE.value)
        self.assertEqual(incident.severity, IncidentSeverityEnum.WARNING.value)
        self.assertEqual(incident.retry_count, 10)
        self.assertIsNotNone(incident.retry_scheduled_until)
        self.assertEqual(incident.code, operation_code("harvesting", TASK_NAME))
        self.assertEqual(incident.catalogue_service_id, self.catalogue.pk)
        self.assertEqual(incident.scope, "resource")

    def test_a_moved_retry_window_updates_the_standing_incident(self):
        first = now() + timedelta(minutes=1)
        self.retry(self.process, retries=0, when=first)
        later = now() + timedelta(minutes=9)
        self.retry(self.process, retries=1, when=later)

        incident = OperationalIncident.objects.get()
        self.assertEqual(incident.retry_scheduled_until, later)
        self.assertEqual(incident.occurrence_count, 2)

    def test_a_task_without_a_process_publishes_nothing(self):
        """A task without a process stays invisible, as in #1207."""
        publish_task_retry(
            sender=FakeTask(),
            request=SimpleNamespace(
                kwargs={"background_process_pk": None}, retries=0),
            reason=retry_reason())
        publish_task_retry(
            sender=FakeTask(),
            request=SimpleNamespace(kwargs={}, retries=1),
            reason=retry_reason())
        self.assertEqual(OperationalIncident.objects.count(), 0)

    def test_a_registering_operation_publishes_nothing(self):
        """#1319 has no incident source for registering - no guessing."""
        process = self.build_process(
            process_type="registering", related=self.catalogue)
        self.retry(process, retries=0)
        publish_terminal_failure(process.pk, TASK_NAME, ValueError("x"))
        self.assertEqual(OperationalIncident.objects.count(), 0)

    def test_a_process_without_a_typed_resource_stays_system_scoped(self):
        process = self.build_process()  # no related resource at all
        self.retry(process, retries=0)
        incident = OperationalIncident.objects.get()
        self.assertEqual(incident.scope, "system")

    def test_the_reason_loses_its_credentials(self):
        self.retry(
            self.process, retries=0,
            message=("GET https://editor:sup3rsecret@geosrv:8080/wfs "
                     "?service=WFS&token=eyJhbGciOi.sig&maxFeatures=100 "
                     "failed with Authorization: Bearer abc.def.ghi"))
        details = OperationalIncident.objects.get().details
        reason = details["reason"]
        for secret in ("sup3rsecret", "eyJhbGciOi.sig", "abc.def.ghi"):
            self.assertNotIn(secret, reason, reason)
        self.assertIn("***", reason)
        # the shape of the failure stays readable - redaction is not
        # amnesia: the host and the parameter names still stand
        self.assertIn("geosrv", reason)
        self.assertIn("token=***", reason)

    def test_scrub_secret_text_keeps_the_shape(self):
        self.assertEqual(scrub_secret_text(None), "")
        self.assertIn("key=***", scrub_secret_text("https://x/y?key=1234"))


class TerminalFailureTests(PublisherTestMixin, TestCase):
    """Exhaustion and giving up are the standing incident turning error."""

    fixtures = ["test_users.json", "test_keywords.json", "test_csw.json"]

    def setUp(self):
        self.catalogue = CatalogueService.objects.get(pk=CSW_PK)
        self.process = self.build_process(related=self.catalogue)

    def test_retry_exhaustion_is_the_same_incident_as_error(self):
        for attempt in range(3):
            self.retry(self.process, retries=attempt)
        standing = OperationalIncident.objects.get()

        publish_terminal_failure(
            self.process.pk, TASK_NAME,
            MaxRetriesExceededError("the retry budget is spent"),
            retries=3)

        incidents = OperationalIncident.objects.all()
        self.assertEqual(incidents.count(), 1)
        incident = incidents.first()
        self.assertEqual(incident.pk, standing.pk)
        self.assertEqual(incident.dedup_key, standing.dedup_key)
        self.assertEqual(incident.severity, IncidentSeverityEnum.ERROR.value)
        self.assertEqual(incident.occurrence_count, 4)
        self.assertTrue(incident.details["exhausted"])

    def test_a_failure_without_retries_opens_an_error_incident(self):
        from requests.exceptions import ConnectTimeout

        publish_terminal_failure(
            self.process.pk, TASK_NAME, ConnectTimeout("no route"),
            retries=0)
        incident = OperationalIncident.objects.get()
        self.assertEqual(incident.severity, IncidentSeverityEnum.ERROR.value)
        self.assertEqual(incident.occurrence_count, 1)
        self.assertFalse(incident.details["exhausted"])

    def test_a_terminal_failure_without_a_process_publishes_nothing(self):
        publish_terminal_failure(None, TASK_NAME, ValueError("x"))
        self.assertEqual(OperationalIncident.objects.count(), 0)


class RecoveryTests(PublisherTestMixin, TestCase):
    """Authoritative success is what resolves; a failure is not."""

    fixtures = ["test_users.json", "test_keywords.json", "test_csw.json"]

    def setUp(self):
        self.catalogue = CatalogueService.objects.get(pk=CSW_PK)
        self.process = self.build_process(related=self.catalogue)

    def test_the_success_of_the_task_resolves_the_standing_incident(self):
        """Recovery resolves it (#1320 AC 1), on the task's own seam."""
        self.retry(self.process, retries=0)
        self.retry(self.process, retries=1)

        self.succeed(self.process)

        incident = OperationalIncident.objects.get()
        self.assertEqual(incident.status, IncidentStatusEnum.RESOLVED.value)
        self.assertIsNotNone(incident.resolved_at)

    def test_a_resolve_without_a_standing_incident_moves_nothing(self):
        self.succeed(self.process)  # idempotent, the common case
        self.assertEqual(OperationalIncident.objects.count(), 0)

    def test_a_problem_returning_after_recovery_opens_a_new_incident(self):
        self.retry(self.process, retries=0)
        self.succeed(self.process)
        self.retry(self.process, retries=0)

        self.assertEqual(OperationalIncident.objects.count(), 2)
        self.assertEqual(self.active().count(), 1)
        self.assertEqual(
            {i.dedup_key for i in OperationalIncident.objects.all()},
            {OperationalIncident.objects.first().dedup_key})

    def test_a_completed_process_resolves_the_incidents_of_its_resource(self):
        self.retry(self.process, retries=0)
        # a watchdog verdict of the same resource, standing beside it
        OperationalIncident.objects.report(
            code="operational_retry_window_expired",
            source="harvesting", severity="warning",
            summary="a verdict of the watchdog",
            resource={"catalogue_service": self.catalogue})
        # a system-scoped verdict of the same code stays standing: its key
        # is the code over no resource, not the key of this resource
        OperationalIncident.objects.report(
            code="operational_retry_window_expired",
            source="harvesting", severity="warning",
            summary="a verdict about nothing",
            resource=None)

        BackgroundProcess.objects.report(
            self.process.pk, ProcessStatusEnum.COMPLETED)

        self.assertEqual(self.active().count(), 1)
        resolved = OperationalIncident.objects.filter(
            status=IncidentStatusEnum.RESOLVED.value)
        self.assertEqual(resolved.count(), 2)
        self.assertTrue(all(
            i.catalogue_service_id == self.catalogue.pk
            for i in resolved))

    def test_a_failed_process_keeps_its_incidents_active(self):
        """A run which failed recovered nothing - nothing resolves."""
        self.retry(self.process, retries=0)
        BackgroundProcess.objects.report(
            self.process.pk, ProcessStatusEnum.FAILED)
        self.assertEqual(self.active().count(), 1)

    def test_an_aborted_process_keeps_its_incidents_active(self):
        """#690 aborts what gave up; an abort is not a recovery."""
        self.retry(self.process, retries=0)
        self.process.phase = "abort"
        self.process.save(update_fields=["phase"])
        self.assertEqual(self.active().count(), 1)


class PublisherRaceTests(PublisherTestMixin, TransactionTestCase):
    """The dedup invariant holds against concurrent reports (#1320 AC)."""

    fixtures = ["test_users.json", "test_keywords.json", "test_csw.json"]

    def setUp(self):
        self.catalogue = CatalogueService.objects.get(pk=CSW_PK)
        self.process = self.build_process(related=self.catalogue)

    def test_concurrent_reports_keep_one_active_incident(self):
        from django.db import connection

        gate = threading.Barrier(3)

        def report():
            try:
                gate.wait()
                self.retry(self.process, retries=1)
            finally:
                connection.close()

        threads = [threading.Thread(target=report) for _ in range(2)]
        for thread in threads:
            thread.start()
        gate.wait()
        for thread in threads:
            thread.join()

        active = self.active()
        self.assertEqual(
            active.count(), 1,
            "the partial unique key must keep one active row per problem")
        self.assertGreaterEqual(
            OperationalIncident.objects.count(), 1)


class WatchdogBeatRowTests(TestCase):
    """The watchdog of #1320 runs on beat, like every periodic look."""

    def test_the_watchdog_has_its_row_in_the_schedule(self):
        from django_celery_beat.models import PeriodicTask
        from notify.apps import OPERATIONAL_INCIDENT_WATCH_TASK_NAME

        row = PeriodicTask.objects.get(
            name=OPERATIONAL_INCIDENT_WATCH_TASK_NAME)
        self.assertEqual(
            row.task, "notify.tasks.watch_operational_incidents")
        self.assertIsNotNone(row.interval)


class CodeBuildingTests(TestCase):
    """The codes are stable per meaning and bounded per storage."""

    def test_the_code_of_a_task_is_its_proper_name_under_its_domain(self):
        code = operation_code("harvesting", TASK_NAME)
        self.assertEqual(code, "harvesting_harvest_fetch_md_metadata")
        self.assertEqual(
            code, operation_code("harvesting", TASK_NAME))  # stable

    def test_a_long_dotted_name_is_bounded_to_the_model_limit(self):
        long_name = ".".join(["a", "registry", "tasks", "deeply",
                              "nested_task_" + "x" * 40])
        code = operation_code("monitoring", long_name)
        self.assertLessEqual(len(code), 64)
        self.assertTrue(code.startswith("monitoring_"))

    def test_a_task_without_segments_still_names_something(self):
        self.assertTrue(operation_code("update", "  "))

    def test_uuid_resources_share_the_key_of_their_pk(self):
        """The key is per resource identity, whatever python shape it came in."""
        pk = uuid.uuid4()
        by_model = OperationalIncident.objects.build_dedup_key(
            "some_code", web_map_service=WebMapService(pk=pk))
        by_pk = OperationalIncident.objects.build_dedup_key(
            "some_code", web_map_service=pk)
        self.assertEqual(by_model, by_pk)
