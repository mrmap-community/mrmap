"""Tests of the independent operational watchdog (#1320).

The watchdog decides from broker- and row-evidence only, and these tests
answer that promise: the inspection of ``celery.app.control.Control`` is
patched exactly as the cancellation tests of #1232 patch it (the class,
not the cached app-level control instance), processes are driven through
the same manager reports a running deployment writes, and the assertions
name both directions - the credible verdict and, just as loudly, the
silence where a naive elapsed-time check would false-positive.

The AC 2 case of #1320 is `test_a_stalled_import_chord_becomes_one_credible_verdict`:
the synthetic fixture of a harvest whose import chord gave up inside
celery's unlock, standing open with an expired retry window and no trace
on the broker - and the job behind it answering exactly what it answered
before the watchdog looked at it.
"""
from datetime import timedelta
from unittest.mock import patch

from django.contrib.contenttypes.models import ContentType
from django.test import TestCase, override_settings
from django.utils.timezone import now
from notify.enums import (IncidentSeverityEnum, IncidentStatusEnum,
                          ProcessStatusEnum)
from notify.incident_watchdog import (CONSUMER_CODE_PREFIX, RETRY_WINDOW_CODE,
                                      declared_queues,
                                      watch_operational_work)
from notify.models import BackgroundProcess, OperationalIncident
from registry.models.harvest import HarvestingJob
from registry.models.service import CatalogueService, WebMapService

CSW_PK = "639cb553-8c30-4e72-a38d-10351ce81cf1"
WMS_PK = "cd16cc1f-3abb-4625-bb96-fbe80dbe23e3"
OTHER_WMS_PK = "1b195589-dcfa-403f-9e66-e7e1c0a67024"

# the inspection is patched on the class, like #1232: `Control.inspect` is
# a cached_property, so an instance-path patch never reaches it
INSPECT = "celery.app.control.Control.inspect"


def broker(inspect, active=None, reserved=None, scheduled=None,
           active_queues=None, dark=False):
    """The answers one fire of the watchdog reads from the broker.

    ``dark`` is the honest case of a broker which reaches no worker at
    all; otherwise every view answers its empty shape unless named, and
    ``active_queues`` defaults to a worker consuming every declared queue
    - the normal state a verdict must never interrupt.
    """
    views = inspect.return_value
    if dark:
        for name in ("active", "reserved", "scheduled", "active_queues"):
            getattr(views, name).return_value = None
        return
    answers = {
        "active": active if active is not None else {},
        "reserved": reserved if reserved is not None else {},
        "scheduled": scheduled if scheduled is not None else {},
        "active_queues": active_queues if active_queues is not None else {
            "worker-1": [{"name": queue} for queue in declared_queues()],
        },
    }
    for name, value in answers.items():
        getattr(views, name).return_value = value


def working_entry(process_pk, task_id):
    """One inspected worker entry which reports a task of the process."""
    return {"kwargs": {"background_process_pk": str(process_pk)},
            "request": {"id": str(task_id)}}


class WatchdogTestMixin:
    """The row-side fixtures of the watchdog."""

    def build_process(self, process_type="harvesting", related=None,
                      window_minutes_ago=30):
        content_type = None
        related_id = None
        if related is not None:
            content_type = ContentType.objects.get_for_model(related)
            related_id = related.pk
        process = BackgroundProcess.objects.create(
            process_type=process_type, phase="records to db",
            description="an operation which stands",
            related_resource_type=content_type, related_id=related_id,
            status=ProcessStatusEnum.RUNNING.value)
        if window_minutes_ago is not None:
            # the real seam of #1207: a reported retry, written back into
            # the past so the window stands expired past the grace
            BackgroundProcess.objects.report_retry(
                process.pk, reason="the service did not answer",
                until=now() - timedelta(minutes=window_minutes_ago))
        return process

    def active(self, code=None):
        query = OperationalIncident.objects.filter(
            status=IncidentStatusEnum.ACTIVE.value)
        return query.filter(code=code) if code else query


class StalledRetryWindowTests(WatchdogTestMixin, TestCase):
    """The #1038 shape: a window which expired with nothing behind it."""

    fixtures = ["test_csw.json", "test_wms.json"]

    def setUp(self):
        self.catalogue = CatalogueService.objects.get(pk=CSW_PK)
        self.wms = WebMapService.objects.get(pk=WMS_PK)

    def test_a_stalled_import_chord_becomes_one_credible_verdict(self):
        """AC 2 of #1320, and nothing of the job's own state moves."""
        job = HarvestingJob.objects.create(
            service=self.catalogue, phase="records to db",
            date_created=now())
        process = job.background_process
        # the sequence a real run leaves behind: work started, a task
        # reported its retry, the attempt never came (#1038)
        BackgroundProcess.objects.report(
            process.pk, ProcessStatusEnum.RUNNING)
        BackgroundProcess.objects.report_retry(
            process.pk, reason="the import did not drain",
            until=now() - timedelta(minutes=40))
        job.refresh_from_db()
        phase_before, done_before = job.phase, job.done_at
        process.refresh_from_db()
        revision_before, status_before = (
            process.revision, process.status)

        with patch(INSPECT) as inspect:
            broker(inspect)
            verdicts = watch_operational_work()

        self.assertEqual(len(verdicts), 1)
        incident = self.active(RETRY_WINDOW_CODE).get()
        self.assertEqual(incident.severity, IncidentSeverityEnum.WARNING.value)
        self.assertEqual(incident.source, "harvesting")
        self.assertEqual(incident.catalogue_service_id, self.catalogue.pk)
        self.assertEqual(incident.scope, "resource")
        self.assertEqual(
            incident.details["background_process"], str(process.pk))

        # the watchdog watched; it did not touch (AC 2)
        job.refresh_from_db()
        self.assertEqual(job.phase, phase_before)
        self.assertEqual(job.done_at, done_before)
        process.refresh_from_db()
        self.assertEqual(process.revision, revision_before)
        self.assertEqual(process.status, status_before)

    def test_a_window_within_the_grace_is_no_verdict(self):
        self.build_process(related=self.catalogue, window_minutes_ago=2)
        with patch(INSPECT) as inspect:
            broker(inspect)
            self.assertEqual(watch_operational_work(), [])
        self.assertEqual(self.active().count(), 0)

    def test_work_an_inspected_worker_reports_is_never_stalled(self):
        process = self.build_process(related=self.catalogue)
        task_id = "11111111-1111-1111-1111-111111111111"
        with patch(INSPECT) as inspect:
            broker(inspect, active={
                "worker-1": [working_entry(process.pk, task_id)]})
            self.assertEqual(watch_operational_work(), [])
        self.assertEqual(self.active().count(), 0)

    def test_a_dark_broker_answers_silence_not_incidents(self):
        self.build_process(related=self.catalogue)
        with patch(INSPECT) as inspect:
            broker(inspect, dark=True)
            self.assertEqual(watch_operational_work(), [])
        self.assertEqual(OperationalIncident.objects.count(), 0)

    def test_slow_legitimate_work_is_never_flagged(self):
        """Normal slow work: no window, only elapsed time stands.

        A long-running import which reports its steps has no open retry
        window at all - the watchdog scans none of its evidence, because
        elapsed runtime alone is not a signal (#1320).
        """
        BackgroundProcess.objects.create(
            process_type="harvesting", phase="records to db",
            description="a big harvest which simply takes hours",
            status=ProcessStatusEnum.RUNNING.value,
            total_steps=500000, done_steps=400,
            related_resource_type=ContentType.objects.get_for_model(self.wms),
            related_id=self.wms.pk,
            date_created=now() - timedelta(hours=30))
        with patch(INSPECT) as inspect:
            broker(inspect)
            self.assertEqual(watch_operational_work(), [])
        self.assertEqual(OperationalIncident.objects.count(), 0)

    def test_two_fires_of_one_standing_stall_are_one_incident(self):
        self.build_process(related=self.catalogue)
        for _ in range(2):
            with patch(INSPECT) as inspect:
                broker(inspect)
                watch_operational_work()
        self.assertEqual(self.active().count(), 1)
        self.assertEqual(
            self.active(RETRY_WINDOW_CODE).get().occurrence_count, 2)

    def test_a_resource_less_stall_publishes_no_verdict(self):
        """Merging every resource-less stall into one system key lies."""
        self.build_process(window_minutes_ago=60)  # no related resource
        with patch(INSPECT) as inspect:
            broker(inspect)
            self.assertEqual(watch_operational_work(), [])
        self.assertEqual(OperationalIncident.objects.count(), 0)

    def test_the_scan_is_bounded_per_fire(self):
        other = WebMapService.objects.get(pk=OTHER_WMS_PK)
        for i, related in enumerate((self.catalogue, self.wms, other)):
            self.build_process(
                related=related, window_minutes_ago=40 + i)
        with override_settings(OPERATIONAL_WATCH_MAX_VERDICTS=2), \
                patch(INSPECT) as inspect:
            broker(inspect)
            verdicts = watch_operational_work()
        self.assertEqual(len(verdicts), 2)
        self.assertEqual(self.active().count(), 2)


class VerdictResolutionTests(WatchdogTestMixin, TestCase):
    """The verdicts of the watchdog resolve when their evidence moves."""

    fixtures = ["test_csw.json"]

    def setUp(self):
        self.catalogue = CatalogueService.objects.get(pk=CSW_PK)
        self.process = self.build_process(related=self.catalogue)
        with patch(INSPECT) as inspect:
            broker(inspect)
            watch_operational_work()
        self.assertEqual(self.active(RETRY_WINDOW_CODE).count(), 1)

    def fire(self, **broker_kwargs):
        with patch(INSPECT) as inspect:
            broker(inspect, **broker_kwargs)
            watch_operational_work()

    def test_a_rescheduled_attempt_resolves_the_standing_verdict(self):
        BackgroundProcess.objects.report_retry(
            self.process.pk, reason="a new attempt was scheduled",
            until=now() + timedelta(minutes=5))
        self.fire()
        self.assertEqual(self.active().count(), 0)
        self.assertEqual(
            OperationalIncident.objects.get().status,
            IncidentStatusEnum.RESOLVED.value)

    def test_work_reporting_again_resolves_the_standing_verdict(self):
        """A RUNNING report closes the retry window (#1207) - and the
        verdict of that closed window resolves with it."""
        BackgroundProcess.objects.report(
            self.process.pk, ProcessStatusEnum.RUNNING)
        self.fire()
        self.assertEqual(self.active().count(), 0)

    def test_a_failed_process_resolves_the_verdict_through_the_sweep(self):
        BackgroundProcess.objects.report(
            self.process.pk, ProcessStatusEnum.FAILED)
        self.fire()
        self.assertEqual(self.active().count(), 0)

    def test_a_still_standing_stall_stays_one_incident(self):
        self.fire()
        standing = self.active(RETRY_WINDOW_CODE).get()
        self.assertEqual(standing.occurrence_count, 2)


class MissingConsumerTests(WatchdogTestMixin, TestCase):
    """The queue-without-consumer evidence belongs to the admins."""

    fixtures = ["test_csw.json"]

    def setUp(self):
        self.catalogue = CatalogueService.objects.get(pk=CSW_PK)

    def consume_only(self, *queues):
        return {"worker-1": [{"name": queue} for queue in queues]}

    def test_a_queue_without_consumer_becomes_system_incidents(self):
        self.build_process(related=self.catalogue, window_minutes_ago=None)
        unwatched = declared_queues() - {"default"}
        with patch(INSPECT) as inspect:
            broker(inspect, active_queues=self.consume_only("default"))
            verdicts = watch_operational_work()
        self.assertEqual(len(verdicts), len(unwatched))
        incidents = self.active()
        self.assertEqual(incidents.count(), len(unwatched))
        for incident in incidents:
            self.assertEqual(incident.scope, "system")
            self.assertEqual(incident.source, "system")
            self.assertEqual(
                incident.severity, IncidentSeverityEnum.ERROR.value)
            self.assertTrue(incident.code.startswith(CONSUMER_CODE_PREFIX))
        self.assertTrue(any(
            incident.code == f"{CONSUMER_CODE_PREFIX}harvest-import"
            for incident in incidents))

    def test_a_consumer_which_came_back_resolves_the_queue_incidents(self):
        self.build_process(related=self.catalogue, window_minutes_ago=None)
        with patch(INSPECT) as inspect:
            broker(inspect, active_queues=self.consume_only("default"))
            watch_operational_work()
        self.assertTrue(self.active().count() >= 1)

        with patch(INSPECT) as inspect:
            broker(inspect)  # every queue consumed again
            watch_operational_work()
        self.assertEqual(self.active().count(), 0)

    def test_without_open_work_an_unwatched_queue_stays_quiet(self):
        """No open operation, no observable starvation (#1320)."""
        with patch(INSPECT) as inspect:
            broker(inspect, active_queues=self.consume_only("default"))
            self.assertEqual(watch_operational_work(), [])
        self.assertEqual(OperationalIncident.objects.count(), 0)
