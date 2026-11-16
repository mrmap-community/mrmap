"""The read API #1326 builds its capacity snapshot on (#1330).

``capacity_measures`` answers occupancy, attempts and queue waiting for a
bounded window. What these tests pin down is the labelling the epic #1324
demands: sums come from measured terminals only, missing evidence stays
``None`` instead of becoming a zero, open attempts are counted as uncertain
rather than summed, and every answer arrives in a fixed, small number of
queries.
"""

import uuid
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from system.capacity_measures import (attempt_measures, grouped_measures,
                                      recent_samples)
from system.models import (AttemptQuality, CeleryTaskAttempt)


def seed(task_id=None, attempt_no=0, queue="default", task_name="some.task",
         outcome="success", active=2.0, wait=None, started_ago_seconds=0,
         quality=None, periodic_name="", worker="celery@a"):
    """One attempt row as the collector would have written it."""
    started = timezone.now() - timedelta(seconds=started_ago_seconds)
    published = (started - timedelta(seconds=wait)
                 if wait is not None else None)
    terminal = outcome != ""
    return CeleryTaskAttempt.objects.create(
        task_id=task_id or str(uuid.uuid4()),
        attempt_no=attempt_no,
        task_name=task_name,
        queue=queue,
        worker=worker,
        periodic_name=periodic_name,
        published_at=published,
        started_at=started,
        finished_at=started + timedelta(seconds=active or 0)
        if terminal else None,
        active_seconds=active if terminal else None,
        wait_seconds=float(wait) if wait is not None else None,
        outcome=outcome,
        quality=quality or [],
    )


def since():
    return timezone.now() - timedelta(hours=1)


class AttemptMeasuresTests(TestCase):

    def test_empty_window_answers_unknown_not_zero(self):
        measures = attempt_measures(since=since())
        self.assertIsNone(measures["occupied_slot_seconds"])
        self.assertIsNone(measures["queue_wait"])
        self.assertEqual(measures["attempts"]["total"], 0)
        self.assertEqual(measures["source"], "measured_worker")

    def test_slot_seconds_sum_terminals_only(self):
        seed(active=3.0)
        seed(active=4.5)
        seed(outcome="", active=None)  # an open attempt: never summed
        measures = attempt_measures(since=since())
        self.assertAlmostEqual(measures["occupied_slot_seconds"], 7.5)
        self.assertEqual(measures["attempts"]["total"], 2)

    def test_backlog_never_becomes_occupancy(self):
        # the acceptance example: 4 h of broker waiting, 2 s of execution
        seed(wait=4 * 3600, active=2.0)
        measures = attempt_measures(since=since())
        self.assertAlmostEqual(measures["occupied_slot_seconds"], 2.0)
        self.assertAlmostEqual(measures["queue_wait"]["p50"], 4 * 3600)
        self.assertEqual(measures["queue_wait"]["samples"], 1)

    def test_retries_and_outcomes_count_per_attempt(self):
        task_id = str(uuid.uuid4())
        seed(task_id=task_id, attempt_no=0, outcome="retry", active=1.0)
        seed(task_id=task_id, attempt_no=1, outcome="failure", active=1.0)
        seed(task_id=task_id, attempt_no=2, outcome="success", active=1.0)
        measures = attempt_measures(since=since())
        self.assertEqual(measures["attempts"]["total"], 3)
        self.assertEqual(measures["attempts"]["by_outcome"]["retry"], 1)
        self.assertEqual(measures["attempts"]["by_outcome"]["failure"], 1)
        self.assertEqual(measures["attempts"]["by_outcome"]["success"], 1)
        self.assertAlmostEqual(measures["occupied_slot_seconds"], 3.0)

    def test_open_rows_count_as_uncertain_once(self):
        finished = seed()
        seed(task_id=finished.task_id, outcome="", active=None)  # flushed twin
        seed(outcome="", active=None)                            # crash residue
        seed(outcome="", active=None, quality=[AttemptQuality.ABANDONED.value])
        measures = attempt_measures(since=since())
        # the open twin of the finished attempt is NOT uncertain; the two
        # open rows without an end ARE, one of them flagged abandoned
        self.assertEqual(measures["attempts"]["total"], 1)
        self.assertEqual(measures["uncertain"]["open_without_end"], 2)
        self.assertEqual(measures["uncertain"]["abandoned"], 1)

    def test_queue_wait_reports_percentiles_and_coverage(self):
        for index in range(1, 21):
            seed(wait=float(index))
        seed()  # terminal without any stamp -> wait unknown
        measures = attempt_measures(since=since())
        wait = measures["queue_wait"]
        self.assertEqual(wait["samples"], 20)
        self.assertAlmostEqual(wait["p50"], 10.5)
        self.assertAlmostEqual(wait["p95"], 19.05)
        self.assertAlmostEqual(wait["max"], 20.0)
        self.assertEqual(measures["coverage"]["terminal_samples"], 21)
        self.assertAlmostEqual(
            measures["coverage"]["wait_coverage"], 20 / 21)

    def test_filters_narrow_by_queue_task_and_periodic_setting(self):
        seed(queue="monitoring", task_name="run_probe_check", active=5.0,
             periodic_name="hourly wms check")
        seed(queue="update", task_name="update_service", active=9.0)
        for filters in (
                {"queue": "monitoring"},
                {"task_name": "run_probe_check"},
                {"periodic_name": "hourly wms check"}):
            measures = attempt_measures(since=since(), **filters)
            self.assertAlmostEqual(
                measures["occupied_slot_seconds"], 5.0, msg=filters)
        measures = attempt_measures(since=since(), queue="update")
        self.assertAlmostEqual(measures["occupied_slot_seconds"], 9.0)

    def test_window_bounds_the_rows_read(self):
        old = timezone.now() - timedelta(days=10)
        seed(active=100.0, started_ago_seconds=10 * 24 * 3600)
        seed(active=1.0)
        measures = attempt_measures(since=since())
        self.assertAlmostEqual(measures["occupied_slot_seconds"], 1.0)
        measures = attempt_measures(since=old - timedelta(hours=1))
        self.assertAlmostEqual(measures["occupied_slot_seconds"], 101.0)

    def test_query_budget(self):
        seed(active=2.0)
        with self.assertNumQueries(3):
            attempt_measures(since=since())


class GroupedMeasuresTests(TestCase):

    def test_grouped_by_queue_with_heaviest_first(self):
        seed(queue="monitoring", active=5.0)
        seed(queue="monitoring", active=5.0)
        seed(queue="harvest-import", active=7.0)
        seed(outcome="", active=None)  # open: never in any group
        answer = grouped_measures(since=since(), by=("queue",))
        # heaviest group first: monitoring with 10 before harvest-import 7
        self.assertEqual(
            [(g["queue"], g["slot_seconds"]) for g in answer["groups"]],
            [("monitoring", 10.0), ("harvest-import", 7.0)])
        self.assertFalse(answer["truncated"])

    def test_grouping_cuts_off_and_says_so(self):
        for name in ("a", "b", "c", "d"):
            seed(task_name=name, queue=name, active=1.0)
        answer = grouped_measures(since=since(), by=("queue",), limit=2)
        self.assertEqual(len(answer["groups"]), 2)
        self.assertTrue(answer["truncated"])

    def test_grouping_by_task_name_and_periodic_setting(self):
        seed(task_name="run_probe_check", periodic_name="hourly", active=2.0)
        seed(task_name="run_probe_check", periodic_name="hourly", active=3.0)
        answer = grouped_measures(
            since=since(), by=("periodic_name", "task_name"))
        self.assertEqual(answer["groups"], [{
            "periodic_name": "hourly", "task_name": "run_probe_check",
            "slot_seconds": 5.0, "samples": 2}])

    def test_unknown_dimension_refuses_instead_of_inventing(self):
        with self.assertRaises(ValueError):
            grouped_measures(since=since(), by=("service_url",))

    def test_query_budget(self):
        seed(queue="x")
        with self.assertNumQueries(1):
            grouped_measures(since=since())


class RecentSamplesTests(TestCase):

    def test_samples_are_bounded_newest_first_value_dicts(self):
        for index in range(5):
            seed(active=float(index), started_ago_seconds=10 - index)
        rows = recent_samples(since(), limit=3)
        self.assertEqual(len(rows), 3)
        self.assertEqual(
            [row["active_seconds"] for row in rows], [4.0, 3.0, 2.0])

    def test_samples_answer_measurement_columns_only(self):
        # the shape #1326 may render: the value set IS the privacy promise
        seed()
        row = recent_samples(since())[0]
        self.assertEqual(set(row), {
            "task_id", "attempt_no", "task_name", "queue", "worker",
            "root_id", "parent_id", "periodic_name", "published_at",
            "started_at", "finished_at", "active_seconds", "wait_seconds",
            "outcome", "quality", "recorded_at"})

    def test_query_budget(self):
        seed()
        with self.assertNumQueries(1):
            recent_samples(since())
