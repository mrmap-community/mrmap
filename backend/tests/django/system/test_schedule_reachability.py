"""A beat schedule which cannot meet its own interval is reported (#1827).

The deployment of the issue fires the alert refresh every 20 s while one run
needs 43 s at p95. Beat keeps the cadence, the singleton lock of #837 refuses
every second fire, the rows are current every ~40 s - and nothing reports it:
the dropped fires executed nothing, so no duration read of the deployment can
see them at all. These tests pin the three halves of the answer:

*   a refused fire is an observation of its own - counted, and never mixed
    into a duration distribution;
*   a schedule is judged against the interval its OWN row fires on, which no
    duration read alone can answer, and the reading arrives as an incident of
    #1319 plus a named gap in the capacity snapshot;
*   the interval of the shipped row comes from the measurement instead of a
    guessed constant.

The failure mode of a diagnostic like this is the opposite of a missing one:
a schedule which merely runs long, or one nobody ever measured, must not
become an incident. Half of the cases below are about staying silent.
"""

import uuid
from contextlib import contextmanager
from datetime import timedelta
from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone
from django_celery_beat.models import IntervalSchedule, PeriodicTask

from notify.enums import IncidentStatusEnum
from notify.models import OperationalIncident
from system import capacity_demand, capacity_snapshot
from system.capacity_measures import (attempt_measures,
                                      measured_p95_of_periodic_task)
from system.models import AttemptOutcome, CeleryTaskAttempt
from system.task_performance import (CODE_SCHEDULE_OVERRUN, class_code,
                                     evaluate_reachability,
                                     evaluate_task_performance)

#: a cadence an operator chose in seconds, and the queue the seeded rows use
REFRESH_SECONDS = 20
QUEUE = "reachability-test"
BEAT = "reachability.test.refresh"
TASK = "registry.tasks.alerts.refresh_service_alerts"

#: generous bounds, so only the cases which want one set a bound
UNCAPPED = dict(TASK_PERFORMANCE_MAX_CLASSES=200,
                TASK_PERFORMANCE_REACHABILITY_MAX_INTERVAL_SECONDS=300,
                CAPACITY_REACHABILITY_HEADROOM=1.1,
                CAPACITY_REACHABILITY_MIN_SAMPLES=5,
                CAPACITY_COST_GROUP_LIMIT=5000,
                CAPACITY_SNAPSHOT_MAX_SCHEDULES=2000,
                CAPACITY_SNAPSHOT_MAX_OCCURRENCES=1_000_000,
                CAPACITY_SNAPSHOT_MAX_OCCURRENCES_PER_SETTING=1_000_000)

LOC_MEM = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "reachability-tests",
    },
}

NO_TOPOLOGY = {"available": False, "reason": "no worker answered",
               "observed_at": None, "workers": {}, "consumed_by": {},
               "zero_consumer_queues": [], "unknown_routing_workers": [],
               "declared_queues": [], "task_routes": {}}
NO_DEPTH = {"available": False, "reason": "the broker did not answer",
            "observed_at": None, "queues": {}}
NO_BACKLOG = {"available": True, "observed_at": None,
              "totals": {"active": 0, "reserved": 0}}


def interval(every=REFRESH_SECONDS, period=IntervalSchedule.SECONDS):
    return IntervalSchedule.objects.create(every=every, period=period)


def beat(name=BEAT, task=TASK, queue=QUEUE, rows=None, enabled=True,
         one_off=False, **kwargs):
    """One interval beat row, its ``last_run_at`` in the past.

    The walk of the demand side takes the baseline of a row which never ran
    from ``date_changed`` (``auto_now``); setting the field keeps a horizon
    assertion about the schedule and not about the moment the test runs.
    """
    return PeriodicTask.objects.create(
        name=name, task=task, queue=queue, interval=rows or interval(),
        enabled=enabled, one_off=one_off,
        last_run_at=timezone.now() - timedelta(days=2), **kwargs)


def attempt(*, periodic_name=BEAT, task_name=TASK, queue=QUEUE,
            outcome="success", active=None, wait=0.5, started_ago=0):
    """One attempt row as the collector of #1330 writes it.

    A ``skipped`` fire answers without a duration by construction: nothing
    ran, so there is nothing to measure. ``wait`` defaults to a stamp, so a
    seeded sample is a *stamped* one and never joins the coverage verdicts of
    the #1390 fire while the cadence question is what is under test.
    """
    started = timezone.now() - timedelta(seconds=started_ago)
    terminal = outcome not in ("", AttemptOutcome.SKIPPED.value)
    return CeleryTaskAttempt.objects.create(
        task_id=str(uuid.uuid4()),
        attempt_no=0,
        task_name=task_name,
        queue=queue,
        worker="celery@w1",
        periodic_name=periodic_name,
        published_at=started - timedelta(seconds=wait)
        if (terminal and wait is not None) else None,
        started_at=started,
        finished_at=started + timedelta(seconds=active) if terminal else None,
        active_seconds=active if terminal else None,
        wait_seconds=float(wait) if (terminal and wait is not None) else None,
        outcome=outcome,
    )


def seed_run(count, active, spacing=60, **kwargs):
    """``count`` completed runs of one schedule, spaced inside its window."""
    return [attempt(active=active, started_ago=index * spacing + 5, **kwargs)
            for index in range(count)]


def seed_skipped(count, spacing=60, **kwargs):
    """``count`` fires the singleton lock refused."""
    return [attempt(outcome=AttemptOutcome.SKIPPED.value,
                    started_ago=index * spacing + 5, **kwargs)
            for index in range(count)]


class DroppedFireTests(TestCase):
    """The refused fire is counted, and joins no distribution (#1827)."""

    def setUp(self):
        CeleryTaskAttempt.objects.all().delete()

    def measures(self):
        return attempt_measures(since=timezone.now() - timedelta(hours=1))

    def test_dropped_fire_never_becomes_an_occupied_slot(self):
        # the whole point: 20 refused fires of a 43 s schedule must not read
        # as 860 s of occupancy, and must not dilute the sample either
        seed_run(6, active=43.0)
        seed_skipped(20)
        measures = self.measures()
        self.assertAlmostEqual(measures["occupied_slot_seconds"], 6 * 43.0)
        self.assertEqual(measures["attempts"]["total"], 6)
        self.assertEqual(measures["attempts"]["dropped_fires"], 20)

    def test_dropped_fire_is_not_a_failure_and_has_no_duration(self):
        attempt(outcome=AttemptOutcome.SKIPPED.value)
        row = CeleryTaskAttempt.objects.get(
            outcome=AttemptOutcome.SKIPPED.value)
        self.assertIsNone(row.active_seconds)
        self.assertFalse(row.is_terminal)
        measures = self.measures()
        self.assertIsNone(measures["occupied_slot_seconds"])
        self.assertEqual(measures["attempts"]["by_outcome"]["failure"], 0)
        self.assertEqual(measures["attempts"]["dropped_fires"], 1)

    def test_a_window_of_only_dropped_fires_measures_nothing(self):
        # "the schedule never got to run" is not "the schedule is fast"
        seed_skipped(6)
        self.assertIsNone(self.measures()["occupied_slot_seconds"])


class ReachabilityReadTests(TestCase):
    """The join of a schedule's measured duration with its own interval."""

    def setUp(self):
        CeleryTaskAttempt.objects.all().delete()
        PeriodicTask.objects.all().delete()

    def reachability(self, **kwargs):
        return capacity_demand.schedule_reachability(
            timezone.now() - timedelta(hours=6), **kwargs)

    def sample(self, result):
        self.assertEqual(len(result["schedules"]), 1)
        return next(iter(result["schedules"].values()))

    @override_settings(**UNCAPPED)
    def test_p95_above_the_interval_is_unreachable_with_the_drop_share(self):
        # the issue's own numbers: 43 s of work on a 20 s cadence, and every
        # second fire refused by the lock
        beat()
        seed_run(6, active=43.0)
        seed_skipped(6)
        entry = self.sample(self.reachability())
        self.assertEqual(entry["verdict"], "unreachable")
        self.assertAlmostEqual(entry["interval_seconds"], REFRESH_SECONDS)
        self.assertAlmostEqual(entry["active_p95"], 43.0)
        self.assertAlmostEqual(entry["overrun_ratio"], 43.0 / REFRESH_SECONDS)
        self.assertEqual(entry["dropped_fires"], 6)
        self.assertEqual(entry["fires"], 12)
        self.assertAlmostEqual(entry["skipped_share"], 0.5)

    @override_settings(**UNCAPPED)
    def test_the_panel_and_the_single_schedule_read_agree(self):
        # the shipped interval is chosen from the one-schedule read, so the
        # two answers may never disagree about one schedule
        beat()
        seed_run(6, active=43.0)
        entry = self.sample(self.reachability())
        self.assertAlmostEqual(entry["active_p95"],
                               measured_p95_of_periodic_task(BEAT))

    @override_settings(**UNCAPPED)
    def test_a_run_that_fits_with_room_stays_silent(self):
        beat()
        seed_run(6, active=2.0)
        self.assertEqual(self.sample(self.reachability())["verdict"],
                         "reachable")

    @override_settings(**UNCAPPED)
    def test_a_run_which_fits_tightly_is_tight_not_unreachable(self):
        # 19 s on a 20 s cadence fits, but with less than the headroom factor
        # to spare: a schedule about to drop fires, not one which already does
        beat()
        seed_run(6, active=19.0)
        entry = self.sample(self.reachability())
        self.assertEqual(entry["verdict"], "tight")
        self.assertLess(entry["overrun_ratio"], 1.0)

    @override_settings(**UNCAPPED)
    def test_a_schedule_outside_the_interval_bound_is_not_judged(self):
        # a nightly job is not the shape this reads: judging it would turn
        # every long-running schedule into a finding about its own runtime
        beat(rows=interval(every=1, period=IntervalSchedule.HOURS))
        seed_run(6, active=90.0)
        self.assertEqual(self.reachability()["schedules"], {})

    @override_settings(**UNCAPPED)
    def test_disabled_and_one_off_rows_are_not_judged(self):
        beat(enabled=False)
        beat(name="reachability.test.one-off", one_off=True)
        seed_run(6, active=43.0)
        self.assertEqual(self.reachability()["schedules"], {})

    @override_settings(**UNCAPPED)
    def test_a_row_renamed_since_it_ran_is_not_judged(self):
        # the attempt names the row which dispatched it; without a live row of
        # that name there is no interval, and no interval means no verdict
        beat(name="reachability.test.renamed")
        seed_run(6, active=43.0, periodic_name=BEAT)
        self.assertEqual(self.reachability()["schedules"], {})

    @override_settings(**UNCAPPED)
    def test_too_few_samples_answer_unknown_not_fast(self):
        # a schedule which only just started being measured is not a schedule
        # whose cadence was proven - and definitely not a reachable one
        beat()
        seed_run(4, active=43.0)
        entry = self.sample(self.reachability())
        self.assertEqual(entry["verdict"], "unknown")
        self.assertEqual(entry["samples"], 4)
        self.assertEqual(entry["min_samples"], 5)
        self.assertIsNone(entry["overrun_ratio"])

    @override_settings(**UNCAPPED)
    def test_nothing_measured_answers_unknown_never_reachable(self):
        beat()
        seed_skipped(6)
        entry = self.sample(self.reachability())
        self.assertEqual(entry["verdict"], "unknown")
        self.assertIsNone(entry["active_p95"])
        self.assertEqual(entry["dropped_fires"], 6)

    @override_settings(**UNCAPPED)
    def test_the_window_travels_and_the_bound_is_a_setting(self):
        beat()
        seed_run(6, active=43.0)
        result = self.reachability()
        self.assertAlmostEqual(
            result["window"]["since"].timestamp(),
            (timezone.now() - timedelta(hours=6)).timestamp(), delta=5)
        self.assertEqual(
            self.reachability(max_interval_seconds=10)["schedules"], {})


class ReachabilityDetectorTests(TestCase):
    """The same reading as an incident of #1319, and its resolution."""

    fixtures = ["test_users.json", "test_keywords.json", "test_crs.json",
                "test_wms.json", "test_csw.json"]

    def setUp(self):
        CeleryTaskAttempt.objects.all().delete()
        PeriodicTask.objects.all().delete()
        OperationalIncident.objects.all().delete()
        cache.clear()

    def code(self):
        return class_code(CODE_SCHEDULE_OVERRUN, TASK, QUEUE)

    def fire(self):
        """One detector fire over a fleet which answered nothing (unknown).

        The broker inspection is stubbed exactly as the watchdog tests of
        #1320 stub it - ``Control.inspect`` is a cached_property, so only a
        class patch reaches it - and answers dark, which is the honest shape
        for a fire about a cadence: the reading this is about never asks a
        worker anything.
        """
        from MrMap.celery import app
        app.control.__dict__.pop("inspect", None)
        with patch("celery.app.control.Control.inspect") as inspect:
            control = inspect.return_value
            for name in ("active", "conf"):
                getattr(control, name).return_value = None
            return evaluate_task_performance()

    @override_settings(**UNCAPPED)
    def test_unreachable_schedule_publishes_the_overrun_incident(self):
        beat()
        seed_run(6, active=43.0)
        seed_skipped(6)
        verdicts = evaluate_reachability(
            timezone.now() - timedelta(hours=6), timezone.now(),
            timezone.now())
        self.assertEqual(len(verdicts), 1)
        verdict = verdicts[0]
        self.assertEqual(verdict["condition"], "schedule_overrun")
        self.assertEqual(verdict["periodic_name"], BEAT)
        self.assertEqual(verdict["samples"], 6)
        self.assertEqual(verdict["dropped_fires"], 6)
        self.assertAlmostEqual(verdict["skipped_share"], 0.5)
        # the answer an operator needs is in the summary, not only in details
        self.assertIn("MRMAP_SERVICE_ALERT_REFRESH_SECONDS",
                      verdict["summary"])

    @override_settings(**UNCAPPED)
    def test_the_fire_publishes_it_and_the_next_fire_resolves_it(self):
        beat()
        seed_run(6, active=43.0)
        seed_skipped(6)
        summary = self.fire()
        self.assertIn(self.code(), summary["published"])
        incident = OperationalIncident.objects.get(code=self.code())
        self.assertEqual(incident.status, IncidentStatusEnum.ACTIVE.value)
        self.assertEqual(incident.details["periodic_name"], BEAT)
        self.assertGreater(incident.details["overrun_ratio"], 1.0)

        # recovery: the catalogue shrank and the schedule fits again - the
        # next fire has to take the incident away by itself
        CeleryTaskAttempt.objects.all().delete()
        seed_run(6, active=2.0)
        summary = self.fire()
        self.assertGreaterEqual(summary["resolved"], 1)
        self.assertEqual(OperationalIncident.objects.filter(
            code=self.code(),
            status=IncidentStatusEnum.ACTIVE.value).count(), 0)
        incident.refresh_from_db()
        self.assertEqual(incident.status, IncidentStatusEnum.RESOLVED.value)

    @override_settings(**UNCAPPED, TASK_PERFORMANCE_ENABLED=False)
    def test_the_cadence_is_reported_although_slow_detection_is_off(self):
        # the slow-task budgets are what a deployment switches off when a fire
        # gets too expensive; that must not silence the cadence reading too,
        # which is the one an operator cannot notice in any other way
        beat()
        seed_run(6, active=43.0)
        summary = self.fire()
        self.assertEqual(summary["status"], "disabled")
        self.assertIn(self.code(), summary["published"])
        self.assertEqual(OperationalIncident.objects.filter(
            code=self.code()).count(), 1)

    @override_settings(**UNCAPPED)
    def test_a_reachable_schedule_publishes_nothing(self):
        beat()
        seed_run(6, active=2.0)
        seed_skipped(1)
        self.assertEqual(evaluate_reachability(
            timezone.now() - timedelta(hours=6), timezone.now(),
            timezone.now()), [])


class CapacitySnapshotReachabilityTests(TestCase):
    """The panel an operator can read before any incident exists at all."""

    def setUp(self):
        CeleryTaskAttempt.objects.all().delete()
        PeriodicTask.objects.all().delete()
        cache.clear()

    @contextmanager
    def dark_console(self):
        """The build's console/broker reads, handed "nothing answered"."""
        with patch.object(capacity_snapshot.capacity_topology,
                          "observe_topology", return_value=NO_TOPOLOGY), \
                patch.object(capacity_snapshot, "observe_queue_depths",
                             return_value=NO_DEPTH), \
                patch.object(capacity_snapshot, "observe_message_backlog",
                             return_value=NO_BACKLOG):
            yield

    @override_settings(CACHES=LOC_MEM, **UNCAPPED)
    def test_unreachable_schedule_names_its_gap_and_fills_the_panel(self):
        # 90 s of work on a 60 s cadence - a minute rather than the issue's 20
        # s only to keep the horizon walk of the same build small
        beat(rows=interval(every=60))
        seed_run(6, active=90.0)
        seed_skipped(6)
        with self.dark_console():
            snapshot = capacity_snapshot.build_capacity_snapshot(
                horizon_days=1)
        self.assertTrue(snapshot["available"])
        self.assertIn("schedule_interval_unreachable", snapshot["gaps"])
        entries = [entry
                   for entry in snapshot["reachability"]["schedules"].values()
                   if entry["periodic_name"] == BEAT]
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["verdict"], "unreachable")
        self.assertEqual(entries[0]["dropped_fires"], 6)

    @override_settings(CACHES=LOC_MEM, **UNCAPPED)
    def test_a_fleet_which_never_answered_still_answers_the_schedule_side(self):
        # the acceptance point of the issue: the reading does not depend on a
        # worker answering the inspect broadcast, so a deployment whose fleet
        # is unknown still learns that its cadence is not met
        beat(rows=interval(every=60))
        seed_run(6, active=90.0)
        with self.dark_console():
            snapshot = capacity_snapshot.build_capacity_snapshot(
                horizon_days=1)
        self.assertTrue(snapshot["available"])
        self.assertIsNone(snapshot["fleet"]["unique_worker_slots"])
        self.assertIn("topology_unavailable", snapshot["gaps"])
        self.assertIn("schedule_interval_unreachable", snapshot["gaps"])

    @override_settings(CACHES=LOC_MEM, **UNCAPPED)
    def test_a_schedule_which_keeps_up_names_no_unreachable_gap(self):
        beat(rows=interval(every=60))
        seed_run(6, active=5.0)
        with self.dark_console():
            snapshot = capacity_snapshot.build_capacity_snapshot(
                horizon_days=1)
        self.assertNotIn("schedule_interval_unreachable", snapshot["gaps"])
        entries = [entry
                   for entry in snapshot["reachability"]["schedules"].values()
                   if entry["periodic_name"] == BEAT]
        self.assertEqual(entries[0]["verdict"], "reachable")


class RefreshIntervalChoiceTests(TestCase):
    """The shipped cadence comes from the measurement, never a guess."""

    def setUp(self):
        CeleryTaskAttempt.objects.all().delete()
        PeriodicTask.objects.all().delete()
        cache.clear()

    def create_row(self, **settings_override):
        from registry.apps import (SERVICE_ALERT_REFRESH_TASK_NAME,
                                   create_service_alert_refresh_task)
        with override_settings(**settings_override):
            create_service_alert_refresh_task(sender=None)
        return PeriodicTask.objects.get(name=SERVICE_ALERT_REFRESH_TASK_NAME)

    def seed_refresh(self, active, count=6):
        from registry.apps import SERVICE_ALERT_REFRESH_TASK_NAME
        seed_run(count, active=active,
                 periodic_name=SERVICE_ALERT_REFRESH_TASK_NAME)

    @override_settings(**UNCAPPED)
    def test_a_measured_schedule_gets_an_interval_above_its_p95(self):
        # 43 s at p95 -> at least 43 s times the headroom, and bounded by the
        # ceiling rather than the hardcoded 20 s of the earlier release
        self.seed_refresh(43.0)
        row = self.create_row()
        self.assertGreaterEqual(row.interval.every, 64)
        self.assertLess(row.interval.every, 300)
        self.assertEqual(row.interval.period, IntervalSchedule.SECONDS)
        self.assertEqual(row.task, TASK)

    @override_settings(**UNCAPPED)
    def test_a_row_the_operator_moved_stays_theirs(self):
        # the row is keyed by its name: a deployment which re-scheduled it
        # over the api keeps what it chose, adaptation included
        chosen = interval(every=90)
        row = self.create_row()
        row.interval = chosen
        row.save()
        self.seed_refresh(43.0)
        self.create_row()
        row.refresh_from_db()
        self.assertEqual(row.interval, chosen)

    @override_settings(SERVICE_ALERT_REFRESH_ADAPTIVE=False, **UNCAPPED)
    def test_the_adaptation_has_an_operator_kill_switch(self):
        from registry.apps import SERVICE_ALERT_REFRESH_SECONDS
        self.seed_refresh(43.0)
        row = self.create_row(SERVICE_ALERT_REFRESH_ADAPTIVE=False)
        self.assertEqual(row.interval.every, SERVICE_ALERT_REFRESH_SECONDS)

    @override_settings(**UNCAPPED)
    def test_an_explicit_slower_choice_is_never_shortened(self):
        from registry.apps import SERVICE_ALERT_REFRESH_SECONDS
        # the operator asked for a slower refresh than the measurement wants;
        # the adaptive step is a floor under the cadence, not a scheduler
        self.seed_refresh(5.0)
        wanted = SERVICE_ALERT_REFRESH_SECONDS + 60
        row = self.create_row(SERVICE_ALERT_REFRESH_SECONDS=wanted)
        self.assertEqual(row.interval.every, wanted)

    @override_settings(**UNCAPPED)
    def test_an_unmeasured_deployment_keeps_the_configured_cadence(self):
        from registry.apps import SERVICE_ALERT_REFRESH_SECONDS
        row = self.create_row()
        self.assertEqual(row.interval.every, SERVICE_ALERT_REFRESH_SECONDS)

    @override_settings(**UNCAPPED)
    def test_the_ceiling_bounds_an_expensive_measurement(self):
        self.seed_refresh(400.0)
        row = self.create_row(SERVICE_ALERT_REFRESH_MAX_INTERVAL_SECONDS=120)
        self.assertEqual(row.interval.every, 120)

    @override_settings(**UNCAPPED)
    def test_a_broken_measurement_read_costs_the_migrate_nothing(self):
        # a migrate must never fail because the attempt table did not answer
        from registry.apps import SERVICE_ALERT_REFRESH_SECONDS
        self.seed_refresh(43.0)
        with patch("system.capacity_measures.measured_p95_of_periodic_task",
                   side_effect=RuntimeError("the database did not answer")):
            row = self.create_row()
        self.assertEqual(row.interval.every, SERVICE_ALERT_REFRESH_SECONDS)
