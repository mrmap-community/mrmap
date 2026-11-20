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
*   a broken seam costs the profile, never the task; a full buffer costs a
    counter, never the task.
"""

import uuid
from unittest.mock import MagicMock, patch

from celery.app.task import Context
from celery.signals import task_postrun, task_prerun
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from requests import Session

from system import task_profiling as profiling
from system.models import CeleryTaskAttempt

TASK_NAME = "registry.tasks.test.slow"

ENABLED = override_settings(
    TASK_PROFILING_ENABLED=True,
    TASK_PROFILING_TASKS=[TASK_NAME],
    TASK_PROFILING_SAMPLE_RATE=1.0)


def make_task(task_id=None, attempt=0, task=TASK_NAME):
    """A task and request exactly as a worker hands them to the signals."""
    task_obj = MagicMock()
    task_obj.name = task
    task_obj.request = Context(
        task_id=task_id or str(uuid.uuid4()), retries=attempt, task=task)
    return task_obj


def run_attempt(task_id=None, attempt=0, task=TASK_NAME, body=None):
    """Drive prerun/postrun around a body; return the profile it opened."""
    task_obj = make_task(task_id=task_id, attempt=attempt, task=task)
    task_prerun.send(sender=task_obj, task_id=task_obj.request["task_id"],
                     task=task_obj, args=(), kwargs={},
                     parent_id=None, elapsed=None, retries=attempt)
    opened = profiling.active_profile()
    try:
        if body is not None:
            body()
    finally:
        task_postrun.send(sender=task_obj, task_id=task_obj.request["task_id"],
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
