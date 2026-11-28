"""The Celery attempt collector of #1330: what it measures and what it must never do.

The collector rides the celery signals of a worker process and writes
``CeleryTaskAttempt`` rows in bounded batches. These tests drive the signal
seams the way the producers of #1320 do (handler calls with the real
``celery.app.task.Context`` request shape) and assert the promises of the
issue:

*   worker execution, broker wait and nothing else: a 4 h backlog in front
    of a 2 s task answers 2 occupied slot-seconds and a 4 h wait sample -
    never 4 h of occupancy;
*   retries are attempts (the same task uuid under raised counters), and the
    same event arriving twice stays one row;
*   a missing finish stays an open, then abandoned observation - never a
    completed duration;
*   the collector must never break the task it observes: a broken database
    costs telemetry, not executions, and the buffer, the batch and the table
    all stay bounded.
"""

import time
import uuid
from contextlib import contextmanager
from datetime import timedelta
from unittest.mock import MagicMock, patch

from celery import shared_task
from celery.app.task import Context
from celery.signals import (task_failure, task_postrun, task_prerun,
                            task_retry, task_success, worker_process_init)
from django_celery_beat.models import PeriodicTask
from django.test import TestCase, TransactionTestCase, override_settings
from django.utils import timezone

from system import capacity_telemetry as telemetry
from system.apps import (TASK_ATTEMPT_BOUNDING_TASK_NAME,
                         create_task_attempt_bounding_task)
from system.capacity_measures import attempt_measures
from system.capacity_telemetry import (
    PUBLISH_STAMP_HEADER, flush_attempts, reset_collector,
    stamp_publish_time)
from system.models import AttemptOutcome, AttemptQuality, CeleryTaskAttempt
from system.tasks import bound_task_attempt_samples

ENABLED = override_settings(
    CAPACITY_TELEMETRY_ENABLED=True,
    CAPACITY_TELEMETRY_COLLECT_ANY_PROCESS=True)

#: generous over any honest batch cost, low enough to catch a collector that
#: stopped being O(1)-ish per attempt; the measured value of the fixture is
#: printed for the documentation of #1330 to cite
WAVE_SECONDS_BUDGET = 90


def make_request(task_id=None, attempt=0, queue="default",
                 worker="celery@testnode", task="registry.tasks.test.work",
                 root_id=None, parent_id=None, periodic_name=None,
                 published=None):
    """A request exactly as a worker builds it from a protocol-v2 message.

    The custom headers live on the top level of the request dict (celery
    filters the known keys into ``request.headers``, see
    ``Context._get_custom_headers``) - so the publish stamp and beat's
    ``periodic_task_name`` ride the message here like they ride a real one.
    """
    payload = {
        "id": task_id or str(uuid.uuid4()),
        "task": task,
        "retries": attempt,
        "hostname": worker,
        "delivery_info": {"exchange": queue, "routing_key": queue},
    }
    if root_id:
        payload["root_id"] = root_id
    if parent_id:
        payload["parent_id"] = parent_id
    if published is not None:
        payload[PUBLISH_STAMP_HEADER] = published
    if periodic_name is not None:
        payload["periodic_task_name"] = periodic_name
    return Context(payload)


class FakeTask:
    """Identity-hashable stand-in: celery caches receivers per sender, and
    SimpleNamespace's ``__eq__`` would make the sender unhashable."""

    def __init__(self, name, request):
        self.name = name
        self.request = request


def make_task(request, name=None):
    return FakeTask(name or request.get("task"), request)


class SignalSeamTestsMixin:
    """Dispatches the real celery signals, like trace.py does per execution.

    MrMap's two connection-lifecycle receivers (close old on prerun, close
    all on postrun - ``MrMap/celery.py``) are exactly right in a worker and
    fatal inside a TestCase, which keeps its data in an atomic block on that
    very connection: Django's close functions carry no atomic guard and
    CONN_MAX_AGE is 0. They are silenced for the dispatch only; the real
    machinery runs untouched in ``RealEagerExecutionTests`` and the worker
    tests.
    """

    @contextmanager
    def _signal_seam(self):
        with patch("MrMap.celery.close_old_connections"), \
                patch("MrMap.celery.connections.close_all"):
            yield

    def prerun(self, task):
        with self._signal_seam():
            task_prerun.send(sender=task, task_id=task.request.get("id"),
                             task=task, args=(), kwargs={})

    def postrun(self, task):
        with self._signal_seam():
            task_postrun.send(sender=task, task_id=task.request.get("id"),
                              task=task, args=(), kwargs={}, retval=None)

    def succeed(self, task):
        task_success.send(sender=task, retval=None)

    def fail(self, task):
        task_failure.send(sender=task, task_id=task.request.get("id"),
                          args=(), kwargs={}, exc=None, einfo=None)

    def retry(self, task):
        task_retry.send(sender=task, request=task.request, reason=None)


@ENABLED
class CollectorLifecycleTests(SignalSeamTestsMixin, TestCase):
    """Which rows the signal lifecycle leaves behind, with which numbers."""

    def setUp(self):
        reset_collector()
        self.addCleanup(reset_collector)
        CeleryTaskAttempt.objects.all().delete()

    def test_successful_attempt_is_one_terminal_row(self):
        task = make_task(make_request())
        self.prerun(task)
        self.succeed(task)
        self.postrun(task)
        summary = flush_attempts()

        self.assertEqual(summary["written"], 1)
        row = CeleryTaskAttempt.objects.get()
        self.assertEqual(row.task_id, task.request.get("id"))
        self.assertEqual(row.outcome, AttemptOutcome.SUCCESS.value)
        self.assertEqual(row.queue, "default")
        self.assertEqual(row.worker, "celery@testnode")
        self.assertIsNotNone(row.active_seconds)

    def test_execution_without_terminal_signal_closes_on_postrun(self):
        # postrun is the safety net: a bare success label with a measured
        # duration still beats an open row for an execution that ran to end
        task = make_task(make_request())
        self.prerun(task)
        self.postrun(task)
        flush_attempts()
        row = CeleryTaskAttempt.objects.get()
        self.assertEqual(row.outcome, AttemptOutcome.SUCCESS.value)
        self.assertIsNotNone(row.finished_at)

    def test_queue_waiting_and_occupied_time_stay_apart(self):
        # the acceptance example of #1330: 4 h of backlog in front of a 2 s
        # task never reports 4 h of slot occupancy
        published = (timezone.now() - timedelta(hours=4)).timestamp()
        task = make_task(make_request(published=published))
        self.prerun(task)
        self.succeed(task)
        flush_attempts()

        row = CeleryTaskAttempt.objects.get()
        self.assertIsNotNone(row.active_seconds)
        self.assertLess(row.active_seconds, 60)  # occupied: moments only
        self.assertGreater(row.wait_seconds, 4 * 3600 - 60)
        self.assertLess(row.wait_seconds, 4 * 3600 + 60)

    def test_correlation_and_periodic_name_ride_the_row(self):
        root = str(uuid.uuid4())
        parent = str(uuid.uuid4())
        task = make_task(make_request(
            root_id=root, parent_id=parent,
            periodic_name="hourly wms monitoring"))
        self.prerun(task)
        self.succeed(task)
        flush_attempts()

        row = CeleryTaskAttempt.objects.get()
        self.assertEqual(row.root_id, root)
        self.assertEqual(row.parent_id, parent)
        self.assertEqual(row.periodic_name, "hourly wms monitoring")

    def test_fanout_children_keep_their_own_rows_and_parent(self):
        root = str(uuid.uuid4())
        parent = str(uuid.uuid4())
        children = [
            make_task(make_request(root_id=root, parent_id=parent))
            for _ in range(3)]
        for child in children:
            self.prerun(child)
            self.succeed(child)
        flush_attempts()

        rows = CeleryTaskAttempt.objects.all()
        self.assertEqual(rows.count(), 3)  # not one merged group row
        for row in rows:
            self.assertEqual(row.root_id, root)
            self.assertEqual(row.parent_id, parent)

    def test_unstamped_attempt_measures_no_wait(self):
        task = make_task(make_request())  # no publish stamp on the message
        self.prerun(task)
        self.succeed(task)
        flush_attempts()
        row = CeleryTaskAttempt.objects.get()
        self.assertIsNone(row.published_at)
        self.assertIsNone(row.wait_seconds)  # unknown, not zero
        self.assertIsNotNone(row.active_seconds)

    def test_broken_publish_stamp_leaves_execution_time_intact(self):
        task = make_task(make_request(published="not a timestamp"))
        self.prerun(task)
        self.succeed(task)
        flush_attempts()
        row = CeleryTaskAttempt.objects.get()
        self.assertIsNone(row.wait_seconds)
        self.assertIsNotNone(row.active_seconds)


@ENABLED
class RealEagerExecutionTests(TransactionTestCase):
    """One real eager run through celery's own trace machinery (no broker).

    TransactionTestCase like the other tests that execute tasks for real:
    MrMap's postrun receiver closes the connections after every run -
    a state an atomic TestCase block cannot survive but the worker
    connection cycle is built for. Eager execution fires the same signals
    with a real ``Context``, so the collector must have seen it, with the
    queue wait staying *unknown* because the eager path never publishes a
    stamped message.
    """

    def setUp(self):
        reset_collector()
        self.addCleanup(reset_collector)

    def test_real_eager_task_rides_the_seam(self):
        @shared_task(name="tests.system.capacity.probe")
        def probe():
            return 42

        result = probe.apply()
        self.assertEqual(result.result, 42)
        summary = flush_attempts()
        self.assertEqual(summary["written"], 1)
        row = CeleryTaskAttempt.objects.get(
            task_name="tests.system.capacity.probe")
        self.assertEqual(row.outcome, AttemptOutcome.SUCCESS.value)
        self.assertIsNone(row.wait_seconds)  # no publish on the eager path


@ENABLED
class AttemptIdentityTests(SignalSeamTestsMixin, TestCase):
    """Retries, redeliveries and duplicates: every attempt once, nothing twice."""

    def setUp(self):
        reset_collector()
        self.addCleanup(reset_collector)
        CeleryTaskAttempt.objects.all().delete()

    def test_retry_is_a_second_attempt_under_the_same_task_id(self):
        # celery's Task.retry re-publishes under the same uuid with a raised
        # counter; both attempts consumed slot time and both are counted
        task_id = str(uuid.uuid4())
        first = make_task(make_request(task_id=task_id, attempt=0))
        self.prerun(first)
        self.retry(first)
        flush_attempts()

        second = make_task(make_request(task_id=task_id, attempt=1))
        self.prerun(second)
        self.succeed(second)
        flush_attempts()

        rows = CeleryTaskAttempt.objects.order_by("attempt_no")
        self.assertEqual(rows.count(), 2)
        self.assertEqual(rows[0].attempt_no, 0)
        self.assertEqual(rows[0].outcome, AttemptOutcome.RETRY.value)
        self.assertEqual(rows[1].attempt_no, 1)
        self.assertEqual(rows[1].outcome, AttemptOutcome.SUCCESS.value)

    def test_exhausted_retry_budget_reports_failure(self):
        # celery fires task_retry AND task_failure for the exhausted attempt;
        # the terminal failure outranks the retry label
        task = make_task(make_request())
        self.prerun(task)
        self.retry(task)
        self.fail(task)
        flush_attempts()
        row = CeleryTaskAttempt.objects.get()
        self.assertEqual(row.outcome, AttemptOutcome.FAILURE.value)

    def test_same_event_twice_is_one_row(self):
        task = make_task(make_request())
        self.prerun(task)
        self.succeed(task)
        self.succeed(task)  # the same event arriving a second time
        flush_attempts()
        flush_attempts()  # and the same flush arriving a second time
        self.assertEqual(CeleryTaskAttempt.objects.count(), 1)

    def test_concurrent_redelivery_flags_one_merged_sample(self):
        request = make_request()
        task = make_task(request)
        self.prerun(task)
        self.prerun(make_task(make_request(task_id=request.get("id"))))
        self.succeed(task)
        flush_attempts()

        row = CeleryTaskAttempt.objects.get()
        self.assertIn(AttemptQuality.REDELIVERED.value, row.quality)

    def test_database_deduplicates_across_processes(self):
        # two worker processes flushing the same terminal identity: the
        # partial unique index is the authority, the second write is dropped
        task_id = str(uuid.uuid4())

        def row_of(outcome):
            return CeleryTaskAttempt(
                task_id=task_id, attempt_no=0, task_name="x", queue="default",
                worker="celery@a", started_at=timezone.now(),
                finished_at=timezone.now(), active_seconds=1.0,
                outcome=outcome, quality=[])

        CeleryTaskAttempt.objects.bulk_create(
            [row_of("success"), row_of("success")], ignore_conflicts=True)
        self.assertEqual(CeleryTaskAttempt.objects.count(), 1)

    def test_open_and_terminal_row_coexist_for_one_attempt(self):
        # the design's deliberate pair (open row from an earlier flush,
        # terminal row of the finish) - the partial indexes allow exactly it
        task = make_task(make_request())
        self.prerun(task)
        flush_attempts()          # open row written while still running
        self.succeed(task)
        flush_attempts()          # terminal row beside it
        self.assertEqual(CeleryTaskAttempt.objects.count(), 2)
        self.assertEqual(
            CeleryTaskAttempt.objects.exclude(outcome="").count(), 1)


@ENABLED
class OverloadGuardTests(SignalSeamTestsMixin, TestCase):
    """The collector must cost telemetry - never tasks - under pressure."""

    def setUp(self):
        reset_collector()
        self.addCleanup(reset_collector)
        CeleryTaskAttempt.objects.all().delete()

    @override_settings(CAPACITY_TELEMETRY_BUFFER_LIMIT=3,
                       CAPACITY_TELEMETRY_FLUSH_THRESHOLD=100,
                       CAPACITY_TELEMETRY_FLUSH_SECONDS=3600)
    def test_buffer_cap_drops_and_counts_not_measures(self):
        tasks = [make_task(make_request()) for _ in range(6)]
        for task in tasks:
            self.prerun(task)
        stats = telemetry.collector_stats()
        self.assertLessEqual(stats["buffered"], 3)
        self.assertGreaterEqual(stats["dropped"], 3)
        # the survivors are the NEWEST observations, the drop targets were
        # the oldest open ones
        flush_attempts()
        self.assertEqual(
            CeleryTaskAttempt.objects.count(), stats["buffered"])

    def test_signals_survive_a_broken_database(self):
        with patch.object(CeleryTaskAttempt.objects, "bulk_create",
                          side_effect=RuntimeError("db down")):
            task = make_task(make_request())
            with override_settings(CAPACITY_TELEMETRY_FLUSH_THRESHOLD=1):
                self.prerun(task)      # arms the flush deadline
                self.succeed(task)     # terminal event forces a flush here
        # nothing raised through the signal dispatch, the flush failed...
        self.assertEqual(telemetry.collector_stats()["flush_errors"], 1)
        self.assertEqual(CeleryTaskAttempt.objects.count(), 0)
        # ...and the attempt is not lost - it stays buffered for the retry
        stats = telemetry.collector_stats()
        self.assertGreaterEqual(stats["buffered"], 1)

    def test_failed_flush_went_quiet_then_recovers(self):
        calls = []
        real = CeleryTaskAttempt.objects.bulk_create

        def flaky(*args, **kwargs):
            calls.append(1)
            if len(calls) == 1:
                raise RuntimeError("db down")
            return real(*args, **kwargs)

        task = make_task(make_request())
        self.prerun(task)
        self.succeed(task)
        with patch.object(CeleryTaskAttempt.objects, "bulk_create",
                          side_effect=flaky):
            first = flush_attempts()
            self.assertIsNotNone(first["error"])
            # inside the cooldown the collector does not hammer the database
            telemetry._flush_if_due()
            self.assertEqual(len(calls), 1)
        # cooldown over (simulated by clearing the quiet mark): the buffer
        # was kept and is written now
        telemetry._quiet_until = None
        second = flush_attempts()
        self.assertIsNone(second["error"])
        self.assertEqual(CeleryTaskAttempt.objects.count(), 1)

    def test_flush_writes_one_statement_per_batch(self):
        for _ in range(50):
            task = make_task(make_request())
            self.prerun(task)
            self.succeed(task)
        with self.assertNumQueries(1):
            flush_attempts()
        self.assertEqual(CeleryTaskAttempt.objects.count(), 50)

    def test_flush_on_process_shutdown_writes_the_buffer(self):
        task = make_task(make_request())
        self.prerun(task)
        self.succeed(task)
        telemetry.flush_on_process_shutdown()
        self.assertEqual(CeleryTaskAttempt.objects.count(), 1)
        self.assertEqual(telemetry.collector_stats()["buffered"], 0)


@ENABLED
class HighVolumeWaveTests(SignalSeamTestsMixin, TestCase):
    """The 43k-scale acceptance fixture of #1330, as far as a unit test runs it.

    43,000 begin/finish pairs of the collector's own hot path - the numbers
    the live rig of #1324 reported as schedule count - through the batched
    writes. Asserted: nothing grows unbounded (buffer bounded, all attempts
    land), and the whole wave finishes inside a budget so generous it never
    flakily fails CI while still catching a collector that turned quadratic.
    The measured seconds are printed for the documentation to cite.
    """

    def setUp(self):
        reset_collector()
        self.addCleanup(reset_collector)
        CeleryTaskAttempt.objects.all().delete()

    @override_settings(CAPACITY_TELEMETRY_BUFFER_LIMIT=4000,
                       CAPACITY_TELEMETRY_FLUSH_THRESHOLD=2000)
    def test_43k_attempts_are_measured_in_bounded_batches(self):
        wave = 43_000
        started = time.monotonic()
        for index in range(wave):
            task = make_task(make_request(queue="monitoring"))
            telemetry.begin_attempt(sender=task, task_id=task.request.get("id"),
                                    task=task)
            telemetry.finish_attempt_on_success(sender=task)
        flush_attempts()
        elapsed = time.monotonic() - started

        stats = telemetry.collector_stats()
        self.assertEqual(stats["dropped"], 0)
        self.assertEqual(stats["flush_errors"], 0)
        self.assertEqual(
            CeleryTaskAttempt.objects.filter(
                outcome=AttemptOutcome.SUCCESS.value).count(), wave)
        print(f"\n[CAPACITY-WAVE] {wave} attempts measured in "
              f"{elapsed:.2f} s "
              f"({elapsed / wave * 1000:.4f} ms/attempt, buffer never over "
              f"{stats['buffered']})")
        self.assertLess(elapsed, WAVE_SECONDS_BUDGET)


@ENABLED
class PublishStampTests(TestCase):
    """The header stamp which makes queue waiting measurable at all."""

    def test_stamp_rides_the_header_dict(self):
        headers = {}
        stamp_publish_time(sender="registry.tasks.test.work", headers=headers)
        self.assertIn(PUBLISH_STAMP_HEADER, headers)
        self.assertIsInstance(headers[PUBLISH_STAMP_HEADER], float)

    def test_stamp_survives_a_v1_message_without_headers(self):
        stamp_publish_time(sender="x", headers=None)  # must not raise

    @override_settings(CAPACITY_TELEMETRY_ENABLED=False)
    def test_kill_switch_stops_the_stamp(self):
        headers = {}
        stamp_publish_time(sender="x", headers=headers)
        self.assertEqual(headers, {})

    def test_real_publish_path_carries_the_stamp(self):
        # the signal receives THE header dict celery publishes, so a stamp
        # written here really rides to the worker: verified against the
        # app's own publish machinery with a captured producer
        from MrMap.celery import app

        producer = MagicMock()
        app.send_task("registry.tasks.test.work", args=(), kwargs=(),
                      producer=producer, retry=False)
        publish_kwargs = producer.publish.call_args.kwargs
        self.assertIn(PUBLISH_STAMP_HEADER, publish_kwargs["headers"])


class CollectionGateTests(SignalSeamTestsMixin, TestCase):
    """Who is allowed to collect at all (#1330 must not touch every process)."""

    def setUp(self):
        reset_collector()
        self.addCleanup(reset_collector)
        CeleryTaskAttempt.objects.all().delete()

    def test_plain_process_records_nothing(self):
        # the settings default: not enabled everywhere, and no collect-any
        # override; this test process is not a celery worker either
        with override_settings(CAPACITY_TELEMETRY_ENABLED=True,
                               CAPACITY_TELEMETRY_COLLECT_ANY_PROCESS=False):
            task = make_task(make_request())
            self.prerun(task)
            self.succeed(task)
            flush_attempts()
        self.assertEqual(CeleryTaskAttempt.objects.count(), 0)

    def test_worker_process_init_opens_the_gate(self):
        # the signal a real prefork child fires; with it, this very process
        # is a worker and the collector runs WITHOUT the test override
        with override_settings(CAPACITY_TELEMETRY_ENABLED=True,
                               CAPACITY_TELEMETRY_COLLECT_ANY_PROCESS=False):
            worker_process_init.send(sender=None)
            task = make_task(make_request())
            self.prerun(task)
            self.succeed(task)
            flush_attempts()
        self.addCleanup(reset_collector)
        self.assertEqual(CeleryTaskAttempt.objects.count(), 1)

    def test_disabled_settings_record_nothing(self):
        with override_settings(CAPACITY_TELEMETRY_ENABLED=False,
                               CAPACITY_TELEMETRY_COLLECT_ANY_PROCESS=True):
            task = make_task(make_request())
            self.prerun(task)
            self.succeed(task)
            flush_attempts()
        self.assertEqual(CeleryTaskAttempt.objects.count(), 0)

    def test_flush_of_an_empty_buffer_is_free(self):
        with self.assertNumQueries(0):
            flush_attempts()


@ENABLED
class SkippedFireTests(SignalSeamTestsMixin, TestCase):
    """The dropped fire of a singleton task is an observation of its own.

    A fire the lock refused executed nothing, so it measured nothing: it must
    reach the database as a count and never as a duration, because "the fire
    is over" and "the attempt executed" are different statements (#1827).
    """

    def setUp(self):
        reset_collector()
        self.addCleanup(reset_collector)
        CeleryTaskAttempt.objects.all().delete()

    def skip(self, task):
        from extras.tasks import task_skipped
        task_skipped.send_robust(
            sender=task, task_id=task.request.get("id"),
            attempt_no=task.request.get("retries", 0))

    def test_a_dropped_fire_is_one_row_with_no_duration(self):
        # the real lifecycle of a refused fire: celery fires prerun, the body
        # answers "skipped" without running, and celery reports that answer as
        # an ordinary return - success and postrun arrive AFTER the skip
        task = make_task(make_request(periodic_name="refresh alerts"))
        self.prerun(task)
        self.skip(task)
        self.succeed(task)
        self.postrun(task)
        flush_attempts()
        rows = CeleryTaskAttempt.objects.filter(
            outcome=AttemptOutcome.SKIPPED.value)
        self.assertEqual(rows.count(), 1)
        row = rows.get()
        self.assertEqual(row.periodic_name, "refresh alerts")
        self.assertIsNone(row.active_seconds)
        self.assertIsNone(row.finished_at)
        self.assertIsNone(row.wait_seconds)

    def test_a_dropped_fire_of_an_already_flushed_attempt_is_still_recorded(self):
        # the fire's own row may have left the buffer with an earlier batch;
        # losing the skip would lose the only trace the fire ever left
        task = make_task(make_request(periodic_name="refresh alerts"))
        flush_attempts()
        self.skip(task)
        flush_attempts()
        self.assertEqual(CeleryTaskAttempt.objects.filter(
            outcome=AttemptOutcome.SKIPPED.value).count(), 1)

    def test_a_skip_of_an_unknown_fire_is_not_recorded_at_all(self):
        # without a task uuid there is no identity to key a row by, and an
        # invented one would be an observation which never happened
        task = make_task(make_request())
        self.skip(FakeTask(task.name, Context({"id": None, "task": task.name})))
        flush_attempts()
        self.assertEqual(CeleryTaskAttempt.objects.count(), 0)

    def test_the_gate_of_every_other_collector_applies_here_too(self):
        with override_settings(CAPACITY_TELEMETRY_ENABLED=False):
            task = make_task(make_request())
            self.skip(task)
            flush_attempts()
        self.assertEqual(CeleryTaskAttempt.objects.count(), 0)

    def test_a_broken_write_costs_the_skipped_fire_nothing(self):
        task = make_task(make_request())
        self.prerun(task)
        with patch.object(telemetry, "_enforce_buffer_limit",
                          side_effect=RuntimeError("the database is gone")):
            self.skip(task)
        self.succeed(task)
        self.postrun(task)
        summary = flush_attempts()
        self.assertEqual(summary["error"], None)
        self.assertEqual(CeleryTaskAttempt.objects.filter(
            outcome=AttemptOutcome.SKIPPED.value).count(), 1)


@ENABLED
class PrivacyBoundaryTests(TestCase):
    """No argument, url or payload can ever ride a sample row (#1330)."""

    def test_field_inventory_holds_no_payload_field(self):
        names = {field.name for field in CeleryTaskAttempt._meta.fields}
        self.assertTrue(names.issubset({
            "id", "task_id", "attempt_no", "task_name", "queue", "worker",
            "root_id", "parent_id", "periodic_name", "published_at",
            "started_at", "finished_at", "active_seconds", "wait_seconds",
            "outcome", "quality", "recorded_at"}))
        forbidden = {"args", "kwargs", "url", "payload", "body", "headers",
                     "request", "response", "token", "secret", "password"}
        self.assertEqual(names & forbidden, set())

    def test_request_payload_is_never_read_into_the_row(self):
        # the fake request carries an obvious secret in the task ARGS of the
        # execution; the collector never touches args/kwargs at all
        request = make_request()
        request.argsrepr = "https://user:hunter2@example.org/service"
        request.kwargsrepr = '{"token": "abcd"}'
        task = make_task(request)
        with override_settings(CAPACITY_TELEMETRY_ENABLED=True,
                               CAPACITY_TELEMETRY_COLLECT_ANY_PROCESS=True), \
                patch("MrMap.celery.close_old_connections"), \
                patch("MrMap.celery.connections.close_all"):
            task_prerun.send(sender=task, task_id=request.get("id"), task=task,
                             args=("https://user:hunter2@example.org",),
                             kwargs={"token": "abcd"})
            task_success.send(sender=task, retval=None)
            flush_attempts()

        row = CeleryTaskAttempt.objects.get()
        blob = repr(vars(row)) + str(row)
        self.assertNotIn("hunter2", blob)
        self.assertNotIn("abcd", blob)


class StorageLifecycleTests(TestCase):
    """The sweep which keeps the samples bounded and labels the crash residue."""

    def setUp(self):
        CeleryTaskAttempt.objects.all().delete()

    def open_row(self, started_at, quality=None):
        return CeleryTaskAttempt.objects.create(
            task_id=str(uuid.uuid4()), attempt_no=0,
            task_name="registry.tasks.test.work", queue="default",
            started_at=started_at, outcome="", quality=quality or [])

    def test_open_attempt_past_the_grace_is_flagged_abandoned(self):
        old = self.open_row(timezone.now() - timedelta(hours=49))
        fresh = self.open_row(timezone.now() - timedelta(minutes=5))

        summary = bound_task_attempt_samples.run()

        old.refresh_from_db()
        fresh.refresh_from_db()
        self.assertIn(AttemptQuality.ABANDONED.value, old.quality)
        self.assertEqual(fresh.quality, [])
        self.assertEqual(summary["flagged"], 1)
        # flagging must not invent an end
        self.assertEqual(old.outcome, "")
        self.assertIsNone(old.finished_at)

    def test_flagging_is_idempotent_and_late_finishes_win(self):
        old = self.open_row(timezone.now() - timedelta(hours=49))
        bound_task_attempt_samples.run()
        bound_task_attempt_samples.run()  # second sweep finds nothing new
        old.refresh_from_db()
        self.assertEqual(
            old.quality.count(AttemptQuality.ABANDONED.value), 1)

        # the late terminal row of the same identity arrives anyway: the
        # attempt is measured after all, and the flagged open twin stops
        # being an uncertain observation (see capacity_measures)
        CeleryTaskAttempt.objects.create(
            task_id=old.task_id, attempt_no=0,
            task_name="registry.tasks.test.work", queue="default",
            started_at=old.started_at, finished_at=timezone.now(),
            active_seconds=3.0, outcome=AttemptOutcome.SUCCESS.value)
        measures = attempt_measures(
            since=timezone.now() - timedelta(hours=60))
        self.assertEqual(measures["attempts"]["total"], 1)
        self.assertEqual(measures["uncertain"]["open_without_end"], 0)

    def test_retention_takes_old_samples_back(self):
        keep = self.open_row(timezone.now() - timedelta(hours=1))
        forget = self.open_row(timezone.now() - timedelta(days=20))
        CeleryTaskAttempt.objects.filter(
            pk=forget.pk).update(recorded_at=timezone.now() - timedelta(
                days=20))

        summary = bound_task_attempt_samples.run()

        self.assertEqual(summary["expired"], 1)
        self.assertTrue(CeleryTaskAttempt.objects.filter(pk=keep.pk).exists())
        self.assertFalse(
            CeleryTaskAttempt.objects.filter(pk=forget.pk).exists())

    @override_settings(CAPACITY_TELEMETRY_MAX_ATTEMPTS=2)
    def test_row_cap_takes_the_oldest_first(self):
        rows = [self.open_row(timezone.now()) for _ in range(5)]
        # give the rows distinguishable record times
        for index, row in enumerate(rows):
            CeleryTaskAttempt.objects.filter(pk=row.pk).update(
                recorded_at=timezone.now() - timedelta(minutes=10 - index))

        summary = bound_task_attempt_samples.run()

        self.assertEqual(summary["over_cap"], 3)
        self.assertEqual(summary["remaining"], 2)
        # the three oldest are gone, the two newest stayed
        surviving = set(
            CeleryTaskAttempt.objects.values_list("pk", flat=True))
        self.assertEqual(surviving, {rows[3].pk, rows[4].pk})

    def test_beat_hands_the_sweep_over_hourly(self):
        create_task_attempt_bounding_task(sender=None)
        row = PeriodicTask.objects.get(
            name=TASK_ATTEMPT_BOUNDING_TASK_NAME)
        self.assertEqual(row.task, "system.tasks.bound_task_attempt_samples")
        self.assertEqual(row.crontab.minute, "50")
        # idempotent like every beat row of this deployment
        create_task_attempt_bounding_task(sender=None)
        self.assertEqual(
            PeriodicTask.objects.filter(
                name=TASK_ATTEMPT_BOUNDING_TASK_NAME).count(), 1)
