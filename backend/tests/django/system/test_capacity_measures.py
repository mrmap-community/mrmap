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

from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from system.capacity_measures import (
    WINDOW_WRITTEN, attempt_measures, drilldown_samples, grouped_measures,
    recent_samples, task_class_of, uncertain_coverage, window_buckets)
from system.models import (AttemptOutcome, AttemptQuality, CeleryTaskAttempt)


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


class TaskClassTests(SimpleTestCase):
    """The class rule of #1391: a task's module is its dashboard grouping."""

    def test_class_is_the_first_parts_of_the_name(self):
        self.assertEqual(
            task_class_of("registry.tasks.harvest.harvest_metadata"),
            "registry.tasks.harvest")
        self.assertEqual(task_class_of("registry.tasks.harvest"),
                         "registry.tasks.harvest")

    def test_shorter_names_answer_themselves(self):
        # a task with no module to belong to has no class to be folded into
        self.assertEqual(task_class_of("add"), "add")
        self.assertEqual(task_class_of("extras.tasks.add"),
                         "extras.tasks.add")
        self.assertEqual(task_class_of(""), "")


class TaskClassSqlTests(TestCase):
    """The SQL mirror of :func:`task_class_of` agrees with the Python rule."""

    def test_grouped_answer_matches_the_python_rule(self):
        # the exporter groups in SQL and the policy classifies in Python; the
        # two must not be allowed to drift quietly (#1391)
        names = ["registry.tasks.harvest.harvest_metadata",
                 "registry.tasks.harvest", "add", "extras.tasks.add",
                 "a.b.c.d.e", "notify.tasks.send_mail"]
        for name in names:
            seed(task_name=name)
        answer = window_buckets(since=since(), until=timezone.now())
        self.assertEqual(
            {bucket["task_class"] for bucket in answer["buckets"]},
            {task_class_of(name) for name in names})


class WindowBucketsTests(TestCase):
    """The bucket answer the exporter of #1391 publishes."""

    def test_empty_window_answers_unknown_not_zero(self):
        answer = window_buckets(since=since())
        self.assertEqual(answer["buckets"], [])
        self.assertIsNone(answer["fleet"]["slot_seconds"])
        self.assertIsNone(answer["fleet"]["active_p95"])
        self.assertIsNone(answer["fleet"]["wait_p95"])
        self.assertEqual(answer["fleet"]["executions"], 0)
        self.assertIsNone(answer["coverage"]["wait_coverage"])

    def test_buckets_group_by_class_and_queue_heaviest_first(self):
        seed(task_name="registry.tasks.harvest.harvest_metadata",
             queue="harvest-import", active=10.0)
        seed(task_name="registry.tasks.harvest.harvest_result",
             queue="harvest-import", active=4.0)
        seed(task_name="notify.tasks.send_mail", queue="notify", active=1.0)
        answer = window_buckets(since=since())
        self.assertEqual(
            [(bucket["task_class"], bucket["queue"], bucket["executions"])
             for bucket in answer["buckets"]],
            [("registry.tasks.harvest", "harvest-import", 2),
             ("notify.tasks.send_mail", "notify", 1)])
        self.assertAlmostEqual(
            answer["buckets"][0]["slot_seconds"], 14.0)

    def test_queue_waiting_stays_out_of_the_occupancy(self):
        seed(wait=4 * 3600, active=2.0,
             task_name="registry.tasks.harvest.harvest_metadata")
        bucket = window_buckets(since=since())["buckets"][0]
        self.assertAlmostEqual(bucket["slot_seconds"], 2.0)
        self.assertAlmostEqual(bucket["wait_p95"], 4 * 3600)
        self.assertEqual(bucket["wait_samples"], 1)

    def test_unmeasured_wait_stays_unknown_in_its_bucket(self):
        seed(task_name="registry.tasks.harvest.harvest_metadata")
        seed(task_name="registry.tasks.harvest.harvest_metadata", wait=5.0)
        bucket = window_buckets(since=since())["buckets"][0]
        self.assertEqual(bucket["executions"], 2)
        self.assertEqual(bucket["wait_samples"], 1)
        self.assertIsNotNone(bucket["wait_p50"])

    def test_percentiles_of_active_time_are_the_fleet_percentiles(self):
        for seconds in (1.0, 2.0, 3.0, 4.0):
            seed(active=seconds,
                 task_name="registry.tasks.harvest.harvest_metadata")
        fleet = window_buckets(since=since())["fleet"]
        self.assertAlmostEqual(fleet["active_p50"], 2.5)
        self.assertAlmostEqual(fleet["active_p95"], 3.85, places=6)
        self.assertAlmostEqual(fleet["active_p99"], 3.97, places=6)
        self.assertAlmostEqual(fleet["active_max"], 4.0)

    def test_outcomes_count_per_attempt(self):
        task_id = str(uuid.uuid4())
        seed(task_id=task_id, attempt_no=0, outcome="retry", active=1.0,
             task_name="registry.tasks.harvest.harvest_metadata")
        seed(task_id=task_id, attempt_no=1, outcome="failure", active=1.0,
             task_name="registry.tasks.harvest.harvest_metadata")
        bucket = window_buckets(since=since())["buckets"][0]
        self.assertEqual(bucket["executions"], 2)
        self.assertEqual(bucket["retried"], 1)
        self.assertEqual(bucket["failed"], 1)
        self.assertEqual(bucket["succeeded"], 0)

    def test_uncertain_observations_are_bucketed_as_counts(self):
        seed(task_name="registry.tasks.harvest.harvest_metadata",
             outcome="", active=None, started_ago_seconds=30)
        seed(task_name="notify.tasks.send_mail", queue="notify",
             outcome="", active=None, started_ago_seconds=30,
             quality=[AttemptQuality.ABANDONED.value])
        answer = window_buckets(since=since())
        buckets = {bucket["task_class"]: bucket
                   for bucket in answer["buckets"]}
        self.assertEqual(
            buckets["registry.tasks.harvest"]["uncertain_open"], 1)
        self.assertEqual(
            buckets["notify.tasks.send_mail"]["uncertain_abandoned"], 1)
        self.assertEqual(answer["uncertain"]["open_without_end"], 2)
        self.assertEqual(answer["uncertain"]["abandoned"], 1)

    def test_window_excludes_attempts_outside_it(self):
        # one attempt newer than the window's end, one older than its start
        seed(task_name="registry.tasks.harvest.harvest_metadata",
             started_ago_seconds=10)
        seed(task_name="registry.tasks.harvest.harvest_metadata",
             started_ago_seconds=7200)
        until = timezone.now() - timedelta(minutes=30)
        answer = window_buckets(
            since=until - timedelta(minutes=5), until=until)
        self.assertEqual(answer["fleet"]["executions"], 0)
        self.assertEqual(answer["buckets"], [])
        # the attempt inside the window is the one which answers
        seed(task_name="registry.tasks.harvest.harvest_metadata",
             started_ago_seconds=1900)
        answer = window_buckets(
            since=until - timedelta(minutes=5), until=until)
        self.assertEqual(answer["fleet"]["executions"], 1)

    def test_limit_bounds_the_buckets_and_says_so(self):
        for index in range(4):
            seed(task_name="registry.tasks.harvest%d.task" % index,
                 queue="q%d" % index, active=float(4 - index))
        answer = window_buckets(since=since(), limit=2)
        self.assertEqual(len(answer["buckets"]), 2)
        self.assertTrue(answer["truncated"])
        # the fleet row keeps its exact totals over the whole window even
        # when the bucket list had to be cut
        self.assertEqual(answer["fleet"]["executions"], 4)

    def test_coverage_says_how_much_was_measurable(self):
        seed(task_name="registry.tasks.harvest.harvest_metadata", wait=1.0)
        seed(task_name="registry.tasks.harvest.harvest_metadata")
        answer = window_buckets(since=since())
        self.assertEqual(answer["coverage"]["terminal_samples"], 2)
        self.assertEqual(answer["coverage"]["stamped_samples"], 1)
        self.assertAlmostEqual(answer["coverage"]["wait_coverage"], 0.5)

    def test_query_budget(self):
        seed(task_name="registry.tasks.harvest.harvest_metadata")
        with self.assertNumQueries(4):
            # grouped buckets, per-bucket uncertain, fleet uncertain, fleet
            window_buckets(since=since())
        with self.assertNumQueries(2):
            window_buckets(since=since(), include_uncertain=False)


class DrilldownSamplesTests(TestCase):

    def test_answers_the_newest_rows_of_the_classes_asked_for(self):
        seed(task_name="registry.tasks.harvest.harvest_metadata",
             started_ago_seconds=60)
        seed(task_name="registry.tasks.harvest.harvest_metadata",
             started_ago_seconds=10)
        seed(task_name="notify.tasks.send_mail", queue="notify",
             started_ago_seconds=5)
        rows = drilldown_samples(
            since(), task_classes=["registry.tasks.harvest"])
        self.assertEqual([row["task_name"] for row in rows],
                         ["registry.tasks.harvest.harvest_metadata",
                          "registry.tasks.harvest.harvest_metadata"])

    def test_no_classes_answers_nothing(self):
        seed()
        self.assertEqual(drilldown_samples(since(), task_classes=[]), [])
        self.assertEqual(drilldown_samples(since()), [])

    def test_open_attempts_are_not_samples(self):
        seed(task_name="registry.tasks.harvest.harvest_metadata",
             outcome="", active=None)
        self.assertEqual(
            drilldown_samples(since(),
                              task_classes=["registry.tasks.harvest"]), [])

    def test_rows_carry_measurement_and_correlation_columns_only(self):
        # the drill-down is bounded by the same privacy rule as the rest of
        # the module: no argument, no url, no payload column exists
        seed(task_name="registry.tasks.harvest.harvest_metadata")
        row = drilldown_samples(
            since(), task_classes=["registry.tasks.harvest"])[0]
        self.assertEqual(set(row), {
            "task_id", "attempt_no", "task_name", "task_class", "queue",
            "worker", "root_id", "parent_id", "periodic_name",
            "published_at", "started_at", "finished_at", "active_seconds",
            "wait_seconds", "outcome", "quality"})

    def test_query_budget(self):
        seed(task_name="registry.tasks.harvest.harvest_metadata")
        with self.assertNumQueries(1):
            drilldown_samples(since(),
                              task_classes=["registry.tasks.harvest"])


class UncertainCoverageTests(TestCase):
    """The standing crash residue the coverage panel of #1391 reads.

    These rows are seeded the way the collector and the sweep of
    ``system.tasks`` actually leave a crashed worker behind - an open row
    whose ``started_at`` AND whose ``recorded_at`` are both hours old - rather
    than with the flag pre-set on a fresh row, which is a state no sweep
    produces inside a window and the reason the gap these tests close stayed
    invisible.
    """

    def crashed_row(self, task_name="registry.tasks.harvest.work",
                    hours_ago=49, quality=None):
        """An open row as the crash leaves it: written when it started.

        ``recorded_at`` is moved back with an ``update`` because it is an
        ``auto_now_add`` column - which is exactly what makes this row
        unreachable for a window measured by when a row was written.
        """
        row = CeleryTaskAttempt.objects.create(
            task_id=str(uuid.uuid4()), attempt_no=0, task_name=task_name,
            queue="default", worker="celery@worker-1",
            started_at=timezone.now() - timedelta(hours=hours_ago),
            outcome="", quality=quality or [])
        CeleryTaskAttempt.objects.filter(pk=row.pk).update(
            recorded_at=row.started_at)
        return row

    def test_the_residue_is_answered_for_a_row_no_window_can_reach(self):
        # the row is open, hours old, and not yet flagged: a window of minutes
        # measured by the row write sees neither the row nor its flag, this
        # read sees the row
        self.crashed_row()
        coverage = uncertain_coverage()
        self.assertEqual(coverage["open_abandoned"], 1)
        self.assertEqual(coverage["open_running"], 0)
        self.assertEqual(coverage["open_total"], 1)

    def test_a_task_still_running_is_residue_in_name_only(self):
        # an attempt which started inside the grace may well still run: it
        # must not move the crash-residue number, or a long task reads as
        # crashed workers
        self.crashed_row(hours_ago=1)
        coverage = uncertain_coverage()
        self.assertEqual(coverage["open_abandoned"], 0)
        self.assertEqual(coverage["open_running"], 1)
        self.assertEqual(coverage["open_total"], 1)

    def test_the_read_does_not_wait_for_the_sweep_to_notice(self):
        # the sweep is the deployment's own declaration of the residue, so
        # what it flags must be in the answer - and what it has not reached
        # yet must be there too, because the age says what the flag will say
        from system.tasks import bound_task_attempt_samples

        flagged = self.crashed_row(hours_ago=60)
        unflagged = self.crashed_row(hours_ago=49)
        self.assertNotIn(AttemptQuality.ABANDONED.value, unflagged.quality)
        bound_task_attempt_samples.run()
        flagged.refresh_from_db()
        self.assertIn(AttemptQuality.ABANDONED.value, flagged.quality)

        coverage = uncertain_coverage()
        self.assertEqual(coverage["open_abandoned"], 2)
        self.assertEqual(coverage["open_running"], 0)

    def test_a_late_terminal_row_ends_the_residue(self):
        crashed = self.crashed_row()
        CeleryTaskAttempt.objects.create(
            task_id=crashed.task_id, attempt_no=crashed.attempt_no,
            task_name=crashed.task_name, queue=crashed.queue,
            started_at=crashed.started_at, finished_at=timezone.now(),
            active_seconds=3.0, outcome=AttemptOutcome.SUCCESS.value)
        self.assertEqual(uncertain_coverage()["open_total"], 0)

    def test_the_window_of_its_row_write_cannot_reach_it_at_all(self):
        # the defect the standing read replaces: the row was written when the
        # task started, so it sits outside every window the exporter ever
        # publishes, whether or not the sweep has flagged it
        self.crashed_row()
        self.assertEqual(uncertain_coverage()["open_abandoned"], 1)
        window_end = timezone.now() - timedelta(minutes=1)
        answer = window_buckets(
            since=window_end - timedelta(minutes=5), until=window_end,
            attribution=WINDOW_WRITTEN)
        self.assertEqual(answer["uncertain"]["open_without_end"], 0)
        self.assertEqual(answer["uncertain"]["abandoned"], 0)
        # ... and the standing read still reports it, which is the point
        self.assertEqual(uncertain_coverage()["open_abandoned"], 1)

    def test_the_classes_holding_the_residue_are_named(self):
        self.crashed_row(task_name="registry.tasks.harvest.work")
        self.crashed_row(task_name="registry.tasks.harvest.other")
        self.crashed_row(task_name="notify.tasks.send_mail", hours_ago=1)
        coverage = uncertain_coverage(group_by_class=True)
        self.assertEqual(
            [(row["task_class"], row["open_abandoned"], row["open_running"])
             for row in coverage["by_class"]],
            [("registry.tasks.harvest", 2, 0),
             ("notify.tasks.send_mail", 0, 1)])

    def test_the_read_is_bounded_and_small(self):
        for index in range(3):
            seed(active=1.0, task_name="registry.tasks.harvest.task%d" % index)
        self.crashed_row()
        with self.assertNumQueries(1):
            # one bounded aggregate answers the whole fleet's standing state
            uncertain_coverage()
        with self.assertNumQueries(2):
            # plus one grouped read, for who is holding the residue
            uncertain_coverage(group_by_class=True)

    def test_an_empty_table_answers_zeroes(self):
        coverage = uncertain_coverage(group_by_class=True)
        self.assertEqual(coverage["open_running"], 0)
        self.assertEqual(coverage["open_abandoned"], 0)
        self.assertEqual(coverage["open_total"], 0)
        self.assertEqual(coverage["by_class"], [])
        self.assertEqual(coverage["grace_seconds"], 48 * 3600)
        self.assertEqual(coverage["source"], "measured_worker")
