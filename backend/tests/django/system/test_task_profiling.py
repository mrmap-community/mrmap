"""The opt-in root-cause profiler of #1389: what it measures, what it must never do.

The profiler shares the celery signal seams of #1330 and answers the one
question #1330 could not: *why* an attempt ran the way it did. These tests
drive the seams the way ``test_capacity_telemetry.py`` does and assert the
promises of the issue:

*   off by default, on only for the named allowlist, sampled stably per
    attempt uuid;
*   categories are process-local: enabling the mode adds no per-attempt
    database write (asserted with a query capture);
*   the split accounts for every measured second and, given the attempt's
    own active seconds, names the *unaccounted* remainder instead of
    rebalancing the categories;
*   one repeatable fixture tells slow SQL, slow external HTTP, artificial CPU
    work and a delay which happened in the queue apart from each other;
*   a retried, crashed or doubly delivered attempt reads as partial, and no
    duration is invented to make its split look complete;
*   a broken seam costs the profile, never the task; a full buffer costs a
    counter, never the task.
"""

import http.server
import io
import threading
import time
import uuid
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

from celery.app.task import Context
from celery.signals import (task_failure, task_postrun, task_prerun,
                            task_retry)
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from requests import Session

from system import task_profiling as profiling
from system.models import CeleryTaskAttempt

TASK_NAME = "registry.tasks.test.slow"

#: how far over the configured budget a fixture may make a category run -
#: small enough to keep the suite fast, large enough that a timer
#: resolution cannot make an assertion about the dominant category flip
SLOW = 0.25

ENABLED = override_settings(
    TASK_PROFILING_ENABLED=True,
    TASK_PROFILING_TASKS=[TASK_NAME],
    TASK_PROFILING_SAMPLE_RATE=1.0)

#: the four shapes with a budget they are all measured against: a quarter of
#: a second is the slow threshold, so a fixture which spends a second in one
#: category is unambiguously of that shape
FOUR_SHAPES = override_settings(
    TASK_PROFILING_ENABLED=True,
    TASK_PROFILING_TASKS=[TASK_NAME],
    TASK_PROFILING_SAMPLE_RATE=1.0,
    TASK_PROFILING_SLOW_SECONDS=SLOW,
    TASK_PROFILING_SLOW_SQL_SECONDS=SLOW,
    TASK_PROFILING_SHAPE_THRESHOLD=0.5)


@contextmanager
def signal_seam():
    """Send a celery signal without MrMap's own connection handlers.

    MrMap's connection-lifecycle receivers (``MrMap/celery.py``) are right
    in a worker and fatal inside a TestCase, which keeps its data in an
    atomic block on the very connection they close - silenced for the
    dispatch only, exactly as ``test_capacity_telemetry.py`` does.
    """
    with patch("MrMap.celery.close_old_connections"), \
            patch("MrMap.celery.connections.close_all"):
        yield


def make_task(task_id=None, attempt=0, task=TASK_NAME, root_id="",
              parent_id="", queue=""):
    """A task and request exactly as a worker hands them to the signals."""
    task_obj = MagicMock()
    task_obj.name = task
    task_obj.request = Context(
        task_id=task_id or str(uuid.uuid4()), retries=attempt, task=task,
        root_id=root_id, parent_id=parent_id,
        delivery_info={"routing_key": queue} if queue else {})
    return task_obj


def run_attempt(task_id=None, attempt=0, task=TASK_NAME, body=None,
                root_id="", parent_id="", queue="", outcome=None):
    """Drive prerun/postrun around a body; return the profile it opened.

    ``outcome`` fires the signal of an attempt which did not run to its
    end - ``"retry"`` or ``"failure"`` - from inside the body, which is
    where a worker raises them: before the postrun of the attempt.
    """
    task_obj = make_task(task_id=task_id, attempt=attempt, task=task,
                         root_id=root_id, parent_id=parent_id, queue=queue)
    with signal_seam():
        task_prerun.send(sender=task_obj, task_id=task_obj.request.task_id,
                         task=task_obj, args=(), kwargs={},
                         parent_id=parent_id, elapsed=None, retries=attempt)
    opened = profiling.active_profile()
    try:
        if body is not None:
            body()
        if outcome == "retry":
            with signal_seam():
                task_retry.send(sender=task_obj, request=task_obj.request,
                                reason="test retry", args=(), kwargs={},
                                einfo=None)
        elif outcome == "failure":
            with signal_seam():
                task_failure.send(sender=task_obj,
                                  task_id=task_obj.request.task_id,
                                  name=task, args=(), kwargs={},
                                  exc=RuntimeError("boom"), traceback=None,
                                  einfo=None)
    finally:
        with signal_seam():
            task_postrun.send(
                sender=task_obj, task_id=task_obj.request.task_id,
                task=task_obj, args=(), kwargs={}, retval=None)
    return opened


class GatingTest(TestCase):
    """What "only ever on deliberately" means in code."""

    def setUp(self):
        profiling.reset_profiling_state()

    def test_off_by_default(self):
        self.assertIsNone(run_attempt())
        self.assertEqual(profiling.drain_reports(), [])

    @ENABLED
    def test_only_the_allowlist_is_profiled(self):
        self.assertIsNone(run_attempt(task="registry.tasks.test.other"))
        self.assertIsNotNone(run_attempt())

    @override_settings(TASK_PROFILING_ENABLED=True, TASK_PROFILING_TASKS=[],
                       TASK_PROFILING_SAMPLE_RATE=1.0)
    def test_empty_allowlist_profiles_nothing_even_when_on(self):
        self.assertIsNone(run_attempt())

    @override_settings(TASK_PROFILING_ENABLED=True,
                       TASK_PROFILING_TASKS=[TASK_NAME],
                       TASK_PROFILING_SAMPLE_RATE=0.0)
    def test_zero_rate_profiles_nothing(self):
        self.assertIsNone(run_attempt())

    @override_settings(TASK_PROFILING_ENABLED=True,
                       TASK_PROFILING_TASKS=[TASK_NAME],
                       TASK_PROFILING_SAMPLE_RATE=0.5)
    def test_sampling_is_stable_for_one_task_uuid(self):
        task_id = str(uuid.uuid4())
        decisions = [run_attempt(task_id=task_id, attempt=attempt) is not None
                     for attempt in range(6)]
        self.assertTrue(all(d == decisions[0] for d in decisions))

    @ENABLED
    def test_profiling_writes_nothing_to_the_database(self):
        """The point of the bounded mode: categories stay in-process."""
        with CaptureQueriesContext(connection) as captured:
            run_attempt(body=lambda: list(CeleryTaskAttempt.objects.all()))
            reports = profiling.drain_reports()
        self.assertEqual(len(reports), 1)
        writes = [
            q for q in captured.captured_queries
            if q["sql"].lstrip().upper().startswith(("INSERT", "UPDATE"))]
        self.assertEqual(writes, [])


class CategoryTest(TestCase):
    """Where the time of a profiled attempt went."""

    def setUp(self):
        profiling.reset_profiling_state()

    @ENABLED
    def test_sql_time_is_attributed_to_the_database(self):
        run_attempt(body=lambda: list(CeleryTaskAttempt.objects.all()))
        report = profiling.drain_reports()[0]
        self.assertGreaterEqual(report["sql_queries"], 1)
        self.assertGreater(report["sql_seconds"], 0)

    @ENABLED
    def test_http_time_is_attributed_to_the_service(self):
        # a real Session.send against a closed localhost port: refused
        # fast, but through the seam - no mock in the measured path
        def call():
            try:
                Session().get("http://127.0.0.1:1/x", timeout=0.5)
            except Exception:
                pass
        run_attempt(body=call)
        report = profiling.drain_reports()[0]
        self.assertEqual(report["http_calls"], 1)
        self.assertGreaterEqual(report["http_seconds"], 0)

    @ENABLED
    def test_the_split_closes_against_active_seconds(self):
        opened = run_attempt()
        report = opened.report(active_seconds=10.0)
        self.assertAlmostEqual(
            report["accounted_seconds"] + report["unaccounted_seconds"],
            10.0, places=5)

    @ENABLED
    def test_a_broken_seam_costs_the_profile_not_the_task(self):
        with patch.object(profiling, "_record_sql",
                          side_effect=RuntimeError("seam exploded")):
            run_attempt(body=lambda: list(CeleryTaskAttempt.objects.all()))
        report = profiling.drain_reports()[0]
        self.assertEqual(report["sql_queries"], 0)


class BoundedTest(TestCase):
    """What happens when more attempts arrive than the buffer holds."""

    def setUp(self):
        profiling.reset_profiling_state()

    @ENABLED
    @override_settings(TASK_PROFILING_BUFFER_LIMIT=2)
    def test_a_full_buffer_runs_attempts_unprofiled_and_counts_them(self):
        opened = [run_attempt(attempt=attempt) for attempt in range(4)]
        self.assertIsNotNone(opened[0])
        self.assertIsNotNone(opened[1])
        self.assertIsNone(opened[2])
        self.assertIsNone(opened[3])
        self.assertEqual(len(profiling.drain_reports()), 2)
        self.assertEqual(profiling.profiling_stats()["dropped"], 2)

    @ENABLED
    def test_drained_reports_leave_the_process_empty(self):
        run_attempt()
        self.assertEqual(len(profiling.drain_reports()), 1)
        self.assertEqual(profiling.drain_reports(), [])


class SlowStatementAttributionTest(TestCase):
    """The issue's "slow statement attribution (with parameter redaction)".

    The signature of a statement is what points at a code path, so it is
    kept; the values bound into it are what a payload looks like, so they
    never are. Both halves are asserted here, and the SQL runs through the
    real cursor wrapper - no mock in the measured path.
    """

    def setUp(self):
        profiling.reset_profiling_state()

    def test_redact_sql_keeps_structure_and_drops_values(self):
        sql = ("SELECT * FROM registry_webmapservice "
               "where token = 'super-secret-token' and version in (1, 2.5)")
        signature = profiling.redact_sql(sql)
        self.assertNotIn("super-secret-token", signature)
        self.assertNotIn("2.5", signature)
        self.assertIn("registry_webmapservice", signature)
        self.assertIn("?", signature)

    def test_django_placeholders_survive_the_redaction(self):
        """The shape of the statement stays readable without its values."""
        sql = 'SELECT "x" FROM "t" WHERE "a" = %s AND "b" = %s'
        self.assertEqual(profiling.redact_sql(sql), sql)

    @override_settings(TASK_PROFILING_ENABLED=True,
                       TASK_PROFILING_TASKS=[TASK_NAME],
                       TASK_PROFILING_SAMPLE_RATE=1.0,
                       TASK_PROFILING_SLOW_SQL_SECONDS=0.05)
    def test_a_slow_statement_is_attributed_without_its_values(self):
        secret = "hunter2-token-of-the-csw-admin"

        def slow_query():
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT %s AS secret, pg_sleep(0.12)", [secret])
                cursor.fetchall()

        run_attempt(body=slow_query)
        report = profiling.drain_reports()[0]
        self.assertEqual(len(report["slow_statements"]), 1)
        statement = report["slow_statements"][0]
        self.assertGreater(statement["seconds"], 0)
        self.assertIn("pg_sleep", statement["sql"])
        self.assertNotIn(secret, statement["sql"])
        self.assertNotIn(secret, repr(report))

    @override_settings(TASK_PROFILING_ENABLED=True,
                       TASK_PROFILING_TASKS=[TASK_NAME],
                       TASK_PROFILING_SAMPLE_RATE=1.0,
                       TASK_PROFILING_SLOW_SQL_SECONDS=0.05,
                       TASK_PROFILING_MAX_SLOW_STATEMENTS=2)
    def test_the_slow_statement_list_is_bounded(self):
        def many_slow_queries():
            with connection.cursor() as cursor:
                for _ in range(5):
                    cursor.execute("SELECT pg_sleep(0.06)")
                    cursor.fetchall()

        run_attempt(body=many_slow_queries)
        report = profiling.drain_reports()[0]
        self.assertEqual(len(report["slow_statements"]), 2)
        self.assertGreater(report["slow_sql_seconds"],
                           report["slow_statements"][0]["seconds"])

    @override_settings(TASK_PROFILING_ENABLED=True,
                       TASK_PROFILING_TASKS=[TASK_NAME],
                       TASK_PROFILING_SAMPLE_RATE=1.0,
                       TASK_PROFILING_SLOW_SQL_SECONDS=0.05)
    def test_a_fast_query_is_counted_but_not_attributed(self):
        run_attempt(body=lambda: list(CeleryTaskAttempt.objects.all()))
        report = profiling.drain_reports()[0]
        self.assertGreater(report["sql_queries"], 0)
        self.assertEqual(report["slow_statements"], [])
        self.assertEqual(report["slow_sql_seconds"], 0)


class HttpAttributionTest(TestCase):
    """Remote waiting, retries of it, and the error class of it.

    A real HTTP server on loopback answers the calls, so the measured path
    is the real ``Session.send`` and the real socket - only the far end is
    local.
    """

    class _Handler(http.server.BaseHTTPRequestHandler):
        """Answers with a status the test chooses, then answers again."""

        status = 200

        def do_GET(self):  # noqa: N802 - named by http.server
            self.send_response(self.status)
            self.send_header("Content-Length", "0")
            self.end_headers()

        def log_message(self, *args):
            """Silent: the suite is not a server log."""

    def setUp(self):
        profiling.reset_profiling_state()
        # the status is class state shared with the handler thread, so it
        # goes back to a healthy answer when the test is done with it
        self.addCleanup(setattr, self._Handler, "status", 200)
        self.server = http.server.HTTPServer(("127.0.0.1", 0), self._Handler)
        self.thread = threading.Thread(target=self.server.serve_forever,
                                       daemon=True)
        self.thread.start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.url = f"http://127.0.0.1:{self.server.server_port}/csw"

    def _call(self, times=1):
        def body():
            for _ in range(times):
                Session().get(self.url, timeout=5)
        return body

    @ENABLED
    def test_a_transport_error_is_counted_as_an_error_call(self):
        """A refused catalogue is external delay, and it is an error.

        The call goes out of the way of the served URL to a closed port, so
        the seam sees the exception rather than a status code.
        """
        def refused():
            try:
                Session().get("http://127.0.0.1:1/x", timeout=0.5)
            except Exception:
                pass

        run_attempt(body=refused)
        report = profiling.drain_reports()[0]
        self.assertEqual(report["http_calls"], 1)
        self.assertEqual(report["http_errors"], 1)

    @ENABLED
    def test_http_calls_and_their_error_class_are_counted(self):
        self._Handler.status = 500
        run_attempt(body=self._call(times=2))
        report = profiling.drain_reports()[0]
        self.assertEqual(report["http_calls"], 2)
        self.assertEqual(report["http_errors"], 2)
        self.assertGreater(report["http_seconds"], 0)

    @ENABLED
    def test_a_healthy_answer_is_not_an_error_call(self):
        run_attempt(body=self._call())
        report = profiling.drain_reports()[0]
        self.assertEqual(report["http_calls"], 1)
        self.assertEqual(report["http_errors"], 0)

    @ENABLED
    def test_the_report_never_carries_the_url(self):
        run_attempt(body=self._call())
        report = profiling.drain_reports()[0]
        self.assertNotIn("127.0.0.1", repr(report))
        self.assertNotIn("csw", repr(report))


class ShapeFixtureTest(TestCase):
    """The first acceptance criterion: one fixture, four different answers.

    Four runs of the same task class, one per shape, each measured against
    its own elapsed wall clock and #1330's wait, and each named by a
    different shape. The durations are real waits, not injected numbers.
    """

    def setUp(self):
        profiling.reset_profiling_state()
        self.server = http.server.HTTPServer(("127.0.0.1", 0),
                                             self._SlowHandler)
        self.thread = threading.Thread(target=self.server.serve_forever,
                                       daemon=True)
        self.thread.start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.url = f"http://127.0.0.1:{self.server.server_port}/csw"

    class _SlowHandler(http.server.BaseHTTPRequestHandler):
        """A catalogue which takes a second to answer its document."""

        def do_GET(self):  # noqa: N802 - named by http.server
            time.sleep(1)
            self.send_response(200)
            self.send_header("Content-Length", "0")
            self.end_headers()

        def log_message(self, *args):
            """Silent: the suite is not a server log."""

    def _report_of(self, body, wait_seconds=0.0):
        """Run one attempt and report it against its own measured time."""
        started = time.monotonic()
        opened = run_attempt(body=body)
        elapsed = time.monotonic() - started
        return opened.report(active_seconds=elapsed,
                             wait_seconds=wait_seconds)

    @FOUR_SHAPES
    def test_slow_sql_reads_as_sql_bound(self):
        def slow_query():
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_sleep(1)")
                cursor.fetchall()

        report = self._report_of(slow_query)
        self.assertEqual(report["shape"], "sql_bound")
        self.assertGreaterEqual(report["sql_seconds"], 0.9)
        self.assertEqual(report["http_calls"], 0)

    @FOUR_SHAPES
    def test_slow_external_http_reads_as_http_bound(self):
        report = self._report_of(
            lambda: Session().get(self.url, timeout=5))
        self.assertEqual(report["shape"], "http_bound")
        self.assertGreaterEqual(report["http_seconds"], 0.9)
        self.assertEqual(report["sql_queries"], 0)

    @FOUR_SHAPES
    def test_artificial_cpu_delay_reads_as_cpu_or_unaccounted(self):
        def burns_cpu():
            started = time.monotonic()
            while time.monotonic() - started < 1:
                sum(range(500))

        report = self._report_of(burns_cpu)
        self.assertEqual(report["shape"], "cpu_or_unaccounted")
        # the time is not smeared over a fake CPU total: it stays the named
        # remainder, and the categories stay what was actually measured
        self.assertGreater(report["unaccounted_seconds"], 0.9)
        self.assertEqual(report["sql_seconds"], 0)
        self.assertEqual(report["http_seconds"], 0)

    @FOUR_SHAPES
    def test_a_queue_only_delay_reads_as_queue_wait(self):
        """A message which waited was never a slow task (#1330's clock)."""
        report = self._report_of(lambda: None, wait_seconds=5.0)
        self.assertEqual(report["shape"], "queue_wait")
        self.assertLess(report["active_seconds"], SLOW)

    @FOUR_SHAPES
    def test_the_four_shapes_are_four_different_answers(self):
        def slow_query():
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_sleep(1)")
                cursor.fetchall()

        shapes = [
            self._report_of(slow_query)["shape"],
            self._report_of(
                lambda: Session().get(self.url, timeout=5))["shape"],
            self._report_of(lambda: sum(range(2000)))["shape"],
            self._report_of(lambda: None, wait_seconds=5.0)["shape"],
        ]
        self.assertEqual(len(set(shapes)), 4, shapes)

    @FOUR_SHAPES
    def test_an_unmeasured_attempt_has_no_shape_and_none_is_not_guessed(self):
        run_attempt()
        report = profiling.drain_reports()[0]
        self.assertNotIn("shape", report)
        self.assertNotIn("unaccounted_seconds", report)


class PartialTest(TestCase):
    """Retry, crash, duplicate delivery and what a partial report may say."""

    def setUp(self):
        profiling.reset_profiling_state()

    @ENABLED
    def test_a_retried_attempt_is_marked_partial(self):
        run_attempt(attempt=1, body=lambda: list(CeleryTaskAttempt.objects.all()),
                    outcome="retry")
        report = profiling.drain_reports()[0]
        self.assertIn("retry", report["partial"])
        self.assertEqual(report["outcome"], "retry")
        self.assertEqual(profiling.profiling_stats()["partial"], 1)

    @ENABLED
    def test_a_crashed_attempt_keeps_what_it_measured(self):
        """The split up to the raise is the answer a crash still gives."""
        run_attempt(body=lambda: list(CeleryTaskAttempt.objects.all()),
                    outcome="failure")
        report = profiling.drain_reports()[0]
        self.assertIn("failure", report["partial"])
        self.assertEqual(report["outcome"], "failure")
        self.assertGreater(report["sql_queries"], 0)

    @ENABLED
    def test_a_duplicate_delivery_is_marked_partial(self):
        task_id = str(uuid.uuid4())
        run_attempt(task_id=task_id)
        run_attempt(task_id=task_id)
        reports = profiling.drain_reports()
        self.assertIn("duplicate_delivery", reports[-1]["partial"])
        self.assertEqual(profiling.profiling_stats()["duplicate_delivery"], 1)

    @ENABLED
    def test_one_reason_is_recorded_once(self):
        task_id = str(uuid.uuid4())
        run_attempt(task_id=task_id)
        run_attempt(task_id=task_id, outcome="failure")
        report = profiling.drain_reports()[-1]
        run_attempt(task_id=task_id, outcome="failure")
        self.assertEqual(report["partial"], ["duplicate_delivery", "failure"])

    @ENABLED
    def test_a_partial_report_invents_no_duration(self):
        """Partial names a reason; it never fabricates a category to fill."""
        run_attempt(outcome="retry")
        report = profiling.drain_reports()[0]
        self.assertEqual(report["accounted_seconds"], 0)
        self.assertNotIn("unaccounted_seconds", report)
        self.assertNotIn("shape", report)
        self.assertEqual(report["slow_statements"], [])


class CorrelationTest(TestCase):
    """Chain, chord and retry identity, read off the existing telemetry."""

    def setUp(self):
        profiling.reset_profiling_state()

    @ENABLED
    def test_the_report_carries_the_ids_1330_already_carries(self):
        root = str(uuid.uuid4())
        parent = str(uuid.uuid4())
        task_id = str(uuid.uuid4())
        run_attempt(task_id=task_id, attempt=2, root_id=root,
                    parent_id=parent, queue="harvest")
        report = profiling.drain_reports()[0]
        self.assertEqual(report["task_id"], task_id)
        self.assertEqual(report["attempt_no"], 2)
        self.assertEqual(report["root_id"], root)
        self.assertEqual(report["parent_id"], parent)
        self.assertEqual(report["queue"], "harvest")

    @ENABLED
    def test_a_whole_chord_groups_by_root_id(self):
        """All children of one chord share their root, so they group."""
        root = str(uuid.uuid4())
        for _ in range(2):
            run_attempt(root_id=root)
        reports = profiling.drain_reports()
        self.assertEqual(len(reports), 2)
        self.assertEqual({report["root_id"] for report in reports}, {root})


class LifecycleJoinTest(TestCase):
    """The split read against #1330's attempt row - the reuse the issue asks.

    No second clock: the profiler has no active time and no queue wait of
    its own, and the join with the lifecycle row is what supplies both.
    """

    def setUp(self):
        profiling.reset_profiling_state()

    def _attempt_row(self, task_id, attempt_no=0, active=12.0, wait=0.4):
        return CeleryTaskAttempt.objects.create(
            task_id=task_id, attempt_no=attempt_no, task_name=TASK_NAME,
            started_at=timezone.now(), active_seconds=active,
            wait_seconds=wait, outcome="success")

    @ENABLED
    def test_lifecycle_map_keys_by_the_shared_attempt_identity(self):
        row = self._attempt_row("abc123", 1)
        mapped = profiling.lifecycle_map(CeleryTaskAttempt.objects.all())
        self.assertEqual(mapped, {("abc123", 1): (12.0, 0.4)})
        self.assertEqual(profiling.lifecycle_map([]), {})
        self.assertEqual(row.active_seconds, 12.0)

    @ENABLED
    def test_drain_joins_the_row_and_names_the_remainder(self):
        task_id = "join-me"
        self._attempt_row(task_id)
        run_attempt(task_id=task_id,
                    body=lambda: list(CeleryTaskAttempt.objects.all()))
        reports = profiling.drain_reports(profiling.lifecycle_map(
            CeleryTaskAttempt.objects.all()))
        self.assertEqual(len(reports), 1)
        report = reports[0]
        self.assertEqual(report["active_seconds"], 12.0)
        self.assertEqual(report["wait_seconds"], 0.4)
        self.assertAlmostEqual(
            report["accounted_seconds"] + report["unaccounted_seconds"],
            12.0, places=5)

    @ENABLED
    def test_drain_without_a_row_reports_categories_only(self):
        """Honesty about what is unknown: no row, no shape, no wait."""
        run_attempt()
        report = profiling.drain_reports()[0]
        self.assertNotIn("shape", report)
        self.assertNotIn("wait_seconds", report)
        self.assertNotIn("active_seconds", report)

    @ENABLED
    def test_a_row_for_a_different_attempt_does_not_leak(self):
        self._attempt_row("someone-else", 0)
        run_attempt(task_id="join-me")
        report = profiling.drain_reports(profiling.lifecycle_map(
            CeleryTaskAttempt.objects.all()))[0]
        self.assertNotIn("active_seconds", report)


@ENABLED
class MemoryProfilingTest(TestCase):
    """The memory half of #1620: what an attempt did to its worker.

    The absolute figures belong to the reused prefork worker, not to the
    attempt, so the assertions are about the *movement* between the two reads
    of the attempt's span - and about what the report must say when procfs
    cannot answer at all.
    """

    def setUp(self):
        profiling.reset_profiling_state()
        #: holds what a body allocated, so it is still resident when the
        #: end of the span is sampled in postrun
        self.held = []
        self.addCleanup(self.held.clear)

    MIB = 1024 * 1024

    def _report_of(self, body=None):
        run_attempt(body=body)
        return profiling.drain_reports()[0]

    def _allocate(self, mib):
        """Real, *touched* bytes: untouched zero pages are not resident."""
        self.held.append(bytearray(b"\x01" * (mib * self.MIB)))

    def test_an_attempt_reports_the_memory_it_held(self):
        """Real procfs, real allocation: the retained delta is the claim."""
        report = self._report_of(lambda: self._allocate(150))
        self.assertIn("memory_retained_mib", report)
        self.assertIn("memory_peak_rise_mib", report)
        self.assertGreaterEqual(report["memory_retained_mib"], 100)
        self.assertGreaterEqual(report["memory_peak_rise_mib"], 100)
        self.assertGreater(report["memory_peak_mib"], 0)

    def test_without_procfs_the_report_makes_no_memory_claim(self):
        """No procfs is silence about memory, never a zero."""
        with patch("system.task_profiling._read_first_value",
                   return_value=None):
            report = self._report_of(lambda: None)
        self.assertNotIn("memory_retained_mib", report)
        self.assertNotIn("memory_peak_mib", report)
        self.assertNotIn("memory_limit_mib", report)

    def test_a_broken_memory_read_costs_the_profile_not_the_attempt(self):
        """The fail-open rule of #1330 applies to the new seam as well."""
        with patch("system.task_profiling.memory_snapshot",
                   side_effect=RuntimeError("no procfs here")):
            opened = run_attempt(body=lambda: None)
        self.assertTrue(opened.closed)
        # the attempt was not harmed by the broken seam: no failure noted
        self.assertEqual(profiling.drain_reports()[0].get("outcome"), None)

    def _shaped(self, start, end, **settings):
        """One attempt whose two span reads are the given snapshots.

        Reported the way ``ShapeFixtureTest._report_of`` does: the profile of
        the attempt just run, against its own measured wall clock. The shape
        of a report only exists once an active time is supplied, and the
        memory claim is read off the two span samples taken inside the run.
        """
        snapshots = [start, end] + [end] * 4
        options = dict(TASK_PROFILING_SLOW_SECONDS=SLOW,
                       TASK_PROFILING_SHAPE_THRESHOLD=0.5,
                       TASK_PROFILING_MEMORY_MIB=128)
        options.update(settings)
        with override_settings(TASK_PROFILING_ENABLED=True,
                               TASK_PROFILING_TASKS=[TASK_NAME],
                               TASK_PROFILING_SAMPLE_RATE=1.0, **options), \
                patch("system.task_profiling.memory_snapshot",
                      side_effect=snapshots):
            started = time.monotonic()
            opened = run_attempt(body=lambda: time.sleep(SLOW + 0.05))
            elapsed = time.monotonic() - started
            return opened.report(active_seconds=elapsed), elapsed

    def test_a_big_peak_with_nothing_accounted_reads_as_memory_bound(self):
        """The reading #1620 exists for: not CPU, the objects it held."""
        report, elapsed = self._shaped(
            {"high_water": 300 * self.MIB, "resident": 300 * self.MIB,
             "private_dirty": 200 * self.MIB},
            {"high_water": 520 * self.MIB, "resident": 480 * self.MIB,
             "private_dirty": 400 * self.MIB})
        self.assertEqual(report["shape"], "memory_bound")
        self.assertAlmostEqual(report["memory_peak_rise_mib"], 220.0,
                               delta=1.0)
        self.assertAlmostEqual(report["memory_retained_mib"], 180.0,
                               delta=1.0)
        self.assertGreater(report["unaccounted_seconds"], 0.0)

    def test_a_small_peak_leaves_the_shapes_of_1389_alone(self):
        """Threshold discipline: a modest rise must not read as memory."""
        report, _ = self._shaped(
            {"high_water": 300 * self.MIB, "resident": 300 * self.MIB,
             "private_dirty": 200 * self.MIB},
            {"high_water": 320 * self.MIB, "resident": 305 * self.MIB,
             "private_dirty": 205 * self.MIB},
            TASK_PROFILING_MEMORY_MIB=128)
        self.assertEqual(report["shape"], "cpu_or_unaccounted")

    def test_the_threshold_switches_the_reading_off_entirely(self):
        """Zero disables it, so a deployment can drop the claim, not the run."""
        report, _ = self._shaped(
            {"high_water": 300 * self.MIB, "resident": 300 * self.MIB,
             "private_dirty": 200 * self.MIB},
            {"high_water": 520 * self.MIB, "resident": 480 * self.MIB,
             "private_dirty": 400 * self.MIB},
            TASK_PROFILING_MEMORY_MIB=0)
        self.assertEqual(report["shape"], "cpu_or_unaccounted")

    def test_a_peak_is_read_against_the_ceiling_that_makes_it_a_risk(self):
        """Without the limit a peak is a number nobody can act on."""
        with patch("system.task_profiling.cgroup_limit_bytes",
                   return_value=1024 * self.MIB):
            report, _ = self._shaped(
                {"high_water": 300 * self.MIB, "resident": 300 * self.MIB,
                 "private_dirty": 200 * self.MIB},
                {"high_water": 900 * self.MIB, "resident": 800 * self.MIB,
                 "private_dirty": 700 * self.MIB})
        self.assertEqual(report["memory_limit_mib"], 1024.0)
        self.assertAlmostEqual(report["memory_of_limit"], 0.8789, delta=0.01)

    def test_a_fast_statement_does_not_pay_for_the_rollup(self):
        """Only a seam over the budget reads memory: cost discipline."""
        opened = None
        with patch("system.task_profiling.memory_snapshot",
                   return_value={"high_water": 1, "resident": 1,
                                 "private_dirty": 1}) as read:
            with override_settings(TASK_PROFILING_ENABLED=True,
                                   TASK_PROFILING_TASKS=[TASK_NAME],
                                   TASK_PROFILING_SAMPLE_RATE=1.0,
                                   TASK_PROFILING_MEMORY_SAMPLE_SECONDS=0.5):
                def many_fast_queries():
                    for _ in range(200):
                        profiling._record_sql(0.001, sql="SELECT 1")
                    profiling._record_http(0.4)

                opened = run_attempt(body=many_fast_queries)
        # the two reads of the span itself, and nothing from 201 fast seams
        self.assertEqual(read.call_count, 2,
                         [c.args for c in read.call_args_list])
        self.assertEqual(opened.sql_queries, 200)

    def test_a_slow_statement_is_where_the_peak_is_sampled(self):
        def slow_seams():
            profiling._record_sql(2.0)
            profiling._record_http(1.0)

        with patch("system.task_profiling.memory_snapshot",
                   return_value={"high_water": 1, "resident": 1,
                                 "private_dirty": 1}) as read:
            with override_settings(TASK_PROFILING_ENABLED=True,
                                   TASK_PROFILING_TASKS=[TASK_NAME],
                                   TASK_PROFILING_SAMPLE_RATE=1.0,
                                   TASK_PROFILING_MEMORY_SAMPLE_SECONDS=0.5):
                run_attempt(body=slow_seams)
        # span start, span end, plus one read per slow seam
        self.assertEqual(read.call_count, 4,
                         [c.args for c in read.call_args_list])

    def test_an_unlimited_cgroup_is_not_reported_as_a_ceiling(self):
        """v2's ``max`` and v1's page-aligned giant are both "no ceiling"."""
        for payload in (b"max\n", str(2 ** 63).encode(), b"\n"):
            with patch("builtins.open",
                       side_effect=lambda *a, **k: io.BytesIO(payload)):
                profiling._cgroup_limit_bytes = None
                self.assertIsNone(profiling.cgroup_limit_bytes(), payload)
        profiling._cgroup_limit_bytes = None
