"""What the schedules of a deployment promise inside the horizon (#1326).

``capacity_demand`` answers the demand side of the capacity snapshot: which
dispatches the enabled beat rows still fire in a finite horizon, on which
queue they land, and how many worker slot seconds those dispatches are
expected to occupy. The property these tests hold it to is that the answer is
the **same sequence Beat dispatches by** - the module may take a fast path
through a per-wall-clock-day grid, but it may never disagree with Celery's own
crontab arithmetic, on a DST transition day least of all. The second property
is honesty about the unknown: an unmeasured schedule contributes occurrences
without seconds (a labeled lower bound with its coverage), a row this Celery
cannot build is named and left out instead of taking the answer down, and a
deployment that outruns a walk budget says so instead of answering slowly.
"""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from django.core.cache import cache
from django.test import TestCase, override_settings
from django_celery_beat.models import (CrontabSchedule, IntervalSchedule,
                                       PeriodicTask)
from extras.scheduling import next_run_after
from MrMap.celery import app

from system import capacity_demand
from system.capacity_demand import _WalkBudget, _count_crontab_occurrences
from system.models import CeleryTaskAttempt

BERLIN = ZoneInfo("Europe/Berlin")
UTC = ZoneInfo("UTC")

#: a Wednesday in a window no European zone changes its offset within; the
#: walk is driven through this moment instead of the wall clock, so the
#: expectations below are the same whenever the test runs
AT = datetime(2026, 6, 10, 7, 17, 13, tzinfo=UTC)
BEFORE = AT - timedelta(days=2)

#: the queue the seeded rows route to; it is not a queue of the deployment,
#: which keeps every count below about the seeded rows and nothing else
QUEUE = "capacity-demand-test"

LOC_MEM = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "capacity-demand-tests",
    },
}


def crontab(tz=UTC, **fields):
    """A stored crontab row; the fields are named, never positional.

    The order of a cron line (minute hour dom moy dow) is not the order of
    the model's fields, so every case spells its fields out.
    """
    defaults = {"minute": "*", "hour": "*", "day_of_week": "*",
                "day_of_month": "*", "month_of_year": "*"}
    schedule_fields = {**defaults, **fields}
    return CrontabSchedule.objects.create(timezone=tz, **schedule_fields)


def beat(name, task="some.task", queue=QUEUE, crontab_row=None, interval=None,
         last_run_at=BEFORE, **kwargs):
    """One beat row as a deployment would hold it.

    ``last_run_at`` is always set: the baseline of the walk is then about the
    row, never about the moment the test happens to run (``date_changed`` is
    ``auto_now`` and would otherwise decide the start of the window).
    """
    return PeriodicTask.objects.create(
        name=name, task=task, queue=queue, crontab=crontab_row,
        interval=interval, last_run_at=last_run_at, **kwargs)


def lower_for(row, at):
    """The baseline the module starts its walk from for one row."""
    return capacity_demand._baseline_of(row, at)


def instants_of(row, at, upper):
    """The instants the module's own walk produces for one row."""
    budgets = _WalkBudget(total=10_000_000, per_setting=1_000_000)
    moments, _ = _count_crontab_occurrences(
        row, lower_for(row, at), upper, False, budgets, {}, {})
    return moments


def canonical_instants(row, lower, upper):
    """The instants Beat's canonical step produces - the oracle.

    This is ``extras.scheduling.next_run_after`` applied at *every* step,
    with the model's own ``crontab.schedule`` (a fresh Celery crontab per
    access): the definition of when beat dispatches, independent of the grid
    fast path the module under test uses between the steps.
    """
    out, moment = [], next_run_after(row, lower)
    while moment is not None and moment <= upper:
        out.append(moment)
        moment = next_run_after(row, moment)
    return out


def as_utc(moments):
    return [moment.astimezone(UTC) for moment in moments]


@override_settings(CACHES=LOC_MEM)
class CrontabOccurrenceTests(TestCase):
    """The occurrence walk: Beat's sequence, bounded, horizon-scoped."""

    def setUp(self):
        cache.clear()
        # the deployment's own beat rows (migrate creates the housekeeping
        # schedules) would otherwise count into every expectation here
        PeriodicTask.objects.filter(enabled=True).update(enabled=False)

    def demand(self, at=AT, horizon_days=7, **kwargs):
        return capacity_demand.periodic_demand(
            at, horizon_days=horizon_days, **kwargs)

    def test_walk_matches_the_step_beat_takes(self):
        """For every shape: the grid fast path may not disagree with Beat."""
        cases = [
            ("every half hour", {"minute": "*/30"}, UTC),
            ("half past two", {"minute": "30", "hour": "2"}, UTC),
            ("working quarter hours",
             {"minute": "*/15", "hour": "9-17", "day_of_week": "1-5"}, UTC),
            ("weekdays", {"minute": "0", "hour": "8", "day_of_week": "1-5"},
             UTC),
            ("saturday by name", {"minute": "0", "hour": "0",
                                  "day_of_week": "SAT"}, UTC),
            ("the thirteenth", {"minute": "15", "hour": "3",
                                "day_of_month": "13"}, UTC),
            ("nested fields", {"minute": "0", "hour": "0,12",
                               "day_of_week": "1-5,*/2",
                               "month_of_year": "*/2"}, UTC),
            ("berlin half past two", {"minute": "30", "hour": "2"}, BERLIN),
            ("berlin quarter hours", {"minute": "*/15"}, BERLIN),
        ]
        end = AT + timedelta(days=7)
        for label, fields, zone in cases:
            with self.subTest(shape=label):
                row = beat(f"case-{label}",
                           crontab_row=crontab(tz=zone, **fields))
                self.assertEqual(
                    as_utc(instants_of(row, AT, end)),
                    as_utc(canonical_instants(row, lower_for(row, AT), end)))

    def test_counts_are_the_arithmetic_the_schedule_promises(self):
        """The hand-computable cases, so an off-by-one at the edges shows up."""
        half_hours = beat("half-hours", crontab_row=crontab(minute="*/30"))
        end = AT + timedelta(days=7)
        self.assertEqual(self.demand()["queues"][QUEUE]["occurrences"], 336)
        self.assertEqual(
            as_utc(instants_of(half_hours, AT, end))[0],
            datetime(2026, 6, 10, 7, 30, tzinfo=UTC))

        PeriodicTask.objects.all().update(enabled=False)
        daily = beat("daily", crontab_row=crontab(minute="30", hour="2"))
        demand = self.demand()
        self.assertEqual(demand["queues"][QUEUE]["occurrences"], 7)
        self.assertEqual(
            as_utc(instants_of(daily, AT, end))[0],
            datetime(2026, 6, 11, 2, 30, tzinfo=UTC))

        PeriodicTask.objects.all().update(enabled=False)
        beat("weekly-saturday",
             crontab_row=crontab(minute="0", hour="0", day_of_week="SAT"))
        demand = self.demand()
        self.assertEqual(demand["totals"]["occurrences"], 1)

    def test_a_schedule_firing_outside_the_horizon_contributes_nothing(self):
        """The horizon is stated, never extrapolated to a permanent rate."""
        row = beat("once-a-year-in-july",
                   crontab_row=crontab(minute="0", hour="0", month_of_year="7"))
        demand = self.demand()
        self.assertEqual(demand["queues"][QUEUE]["occurrences"], 0)
        self.assertEqual(demand["totals"]["occurrences"], 0)
        # it was still walked: the answer is "nothing inside the horizon",
        # not "nothing known about this schedule"
        self.assertEqual(demand["schedules"]["walked"], 1)
        self.assertEqual(
            as_utc(instants_of(row, AT, AT + timedelta(days=15))), [])

    def test_day_of_week_and_day_of_month_are_combined_as_an_and(self):
        """Celery 5.7's day match is the AND of the fields, not vixie's OR."""
        start = datetime(2026, 5, 1, tzinfo=UTC)
        row = beat("monday-the-25th",
                   crontab_row=crontab(minute="0", hour="0", day_of_month="25",
                                       day_of_week="MON"),
                   last_run_at=start - timedelta(days=5))
        # 2026-05-25 is a Monday, so it matches both fields. The Mondays on
        # the 4th, 11th and 18th and the 25th of a non-Monday month would all
        # fire under an OR - they must not
        self.assertEqual(
            as_utc(instants_of(row, start, start + timedelta(days=40))),
            [datetime(2026, 5, 25, 0, 0, tzinfo=UTC)])

    def test_spring_forward_fires_once_at_the_instant_beat_dispatches(self):
        """02:30 Berlin does not exist on 2026-03-29; Beat still fires once."""
        start = datetime(2026, 3, 27, 12, tzinfo=UTC)
        row = beat("daily", crontab_row=crontab(minute="30", hour="2", tz=BERLIN),
                   last_run_at=start - timedelta(days=2))
        demand = self.demand(at=start, horizon_days=5)
        self.assertEqual(demand["totals"]["occurrences"], 5)
        self.assertEqual(
            as_utc(instants_of(row, start, start + timedelta(days=5))), [
                datetime(2026, 3, 28, 1, 30, tzinfo=UTC),
                # the missed wall minute: one fire, at the instant Beat's own
                # step lands on - not a skipped day, not a doubled one
                datetime(2026, 3, 29, 1, 30, tzinfo=UTC),
                datetime(2026, 3, 30, 0, 30, tzinfo=UTC),
                datetime(2026, 3, 31, 0, 30, tzinfo=UTC),
                datetime(2026, 4, 1, 0, 30, tzinfo=UTC),
            ])

    def test_fall_back_fires_once_and_not_twice(self):
        """02:30 Berlin happens twice on 2026-10-25; Beat fires on the first."""
        start = datetime(2026, 10, 23, 12, tzinfo=UTC)
        row = beat("daily", crontab_row=crontab(minute="30", hour="2", tz=BERLIN),
                   last_run_at=start - timedelta(days=2))
        demand = self.demand(at=start, horizon_days=5)
        self.assertEqual(demand["totals"]["occurrences"], 5)
        self.assertEqual(
            as_utc(instants_of(row, start, start + timedelta(days=5))), [
                datetime(2026, 10, 24, 0, 30, tzinfo=UTC),
                datetime(2026, 10, 25, 0, 30, tzinfo=UTC),
                datetime(2026, 10, 26, 1, 30, tzinfo=UTC),
                datetime(2026, 10, 27, 1, 30, tzinfo=UTC),
                datetime(2026, 10, 28, 1, 30, tzinfo=UTC),
            ])

    def test_transition_days_walk_the_canonical_step(self):
        """The dense case: every quarter hour across both transitions."""
        for label, start in (("spring", datetime(2026, 3, 27, 12, tzinfo=UTC)),
                             ("autumn", datetime(2026, 10, 23, 12, tzinfo=UTC))):
            with self.subTest(transition=label):
                PeriodicTask.objects.all().update(enabled=False)
                row = beat(
                    f"quarter-hours-{label}",
                    crontab_row=crontab(minute="*/15", tz=BERLIN),
                    last_run_at=start - timedelta(days=2))
                end = start + timedelta(days=6)
                self.assertEqual(
                    as_utc(instants_of(row, start, end)),
                    as_utc(canonical_instants(row, lower_for(row, start), end)))

    def test_start_time_floors_the_baseline_of_the_walk(self):
        row = beat("late-start", crontab_row=crontab(minute="0"),
                   start_time=AT + timedelta(hours=3))
        moments = as_utc(instants_of(row, AT, AT + timedelta(days=1)))
        self.assertEqual(moments[0], datetime(2026, 6, 10, 11, 0, tzinfo=UTC))
        self.assertEqual(moments, as_utc(canonical_instants(
            row, lower_for(row, AT), AT + timedelta(days=1))))

    def test_expiry_ends_the_horizon_early(self):
        """Beat disables a row once ``now`` reaches ``expires``."""
        expires = AT + timedelta(hours=2)
        row = beat("expiring", crontab_row=crontab(minute="*/30"),
                   expires=expires)
        self.assertEqual(
            [moment.isoformat() for moment in
             as_utc(instants_of(row, AT, expires - timedelta(microseconds=1)))],
            ["2026-06-10T07:30:00+00:00", "2026-06-10T08:00:00+00:00",
             "2026-06-10T08:30:00+00:00", "2026-06-10T09:00:00+00:00"])

    def test_an_already_expired_row_is_excluded_with_its_reason(self):
        beat("expired", crontab_row=crontab(minute="*/30"),
             expires=AT - timedelta(minutes=1))
        demand = self.demand()
        self.assertEqual(demand["schedules"]["excluded"]["expired"], 1)
        self.assertEqual(demand["schedules"]["walked"], 0)
        self.assertEqual(demand["totals"]["occurrences"], 0)

    def test_one_off_counts_once_and_a_ran_one_off_not_at_all(self):
        interval = IntervalSchedule.objects.create(
            every=15, period=IntervalSchedule.MINUTES)
        beat("pending", interval=interval, one_off=True)
        self.assertEqual(self.demand()["totals"]["occurrences"], 1)

        PeriodicTask.objects.all().update(enabled=False)
        beat("already-ran", interval=interval, one_off=True, total_run_count=1)
        demand = self.demand()
        self.assertEqual(demand["schedules"]["excluded"]["one_off_ran"], 1)
        self.assertEqual(demand["totals"]["occurrences"], 0)

    def test_a_disabled_row_is_not_walked(self):
        beat("off", crontab_row=crontab(minute="*/30"), enabled=False)
        demand = self.demand()
        self.assertEqual(demand["schedules"]["walked"], 0)
        self.assertEqual(demand["totals"]["occurrences"], 0)

    def test_a_row_without_a_schedule_is_excluded(self):
        # dcb's own ``save()`` refuses a row without a schedule, so a broken
        # row like this can only have arrived through a direct database
        # write - the walk must still count it as excluded, not crash
        PeriodicTask.objects.bulk_create([PeriodicTask(
            name="no-schedule", task="some.task", queue=QUEUE,
            enabled=True, last_run_at=BEFORE)])
        demand = self.demand()
        self.assertEqual(demand["schedules"]["excluded"]["no_schedule"], 1)
        self.assertEqual(demand["schedules"]["walked"], 0)

    def test_intervals_are_counted_without_a_walk(self):
        quarter = IntervalSchedule.objects.create(
            every=15, period=IntervalSchedule.MINUTES)
        beat("quarter", interval=quarter)
        self.assertEqual(self.demand()["totals"]["occurrences"], 672)

        PeriodicTask.objects.all().update(enabled=False)
        two_hours = IntervalSchedule.objects.create(
            every=2, period=IntervalSchedule.HOURS)
        beat("two-hours", interval=two_hours)
        self.assertEqual(self.demand()["totals"]["occurrences"], 84)

        PeriodicTask.objects.all().update(enabled=False)
        three_days = IntervalSchedule.objects.create(
            every=3, period=IntervalSchedule.DAYS)
        beat("three-days", interval=three_days,
             last_run_at=AT - timedelta(days=1))
        self.assertEqual(self.demand()["totals"]["occurrences"], 2)


@override_settings(CACHES=LOC_MEM)
class CostedDemandTests(TestCase):
    """Per-occurrence costs: measured seconds, or the honest absence of them."""

    def setUp(self):
        cache.clear()
        PeriodicTask.objects.filter(enabled=True).update(enabled=False)

    def sample(self, name, task, active=10.0, count=3, queue=QUEUE):
        """``count`` terminal attempts of one beat row, ``active`` s each."""
        for index in range(count):
            started = AT - timedelta(hours=1, minutes=index)
            CeleryTaskAttempt.objects.create(
                task_id=f"{name}-{index}", attempt_no=0, task_name=task,
                queue=queue, worker="celery@a", periodic_name=name,
                started_at=started,
                finished_at=started + timedelta(seconds=active),
                active_seconds=active, outcome="success", quality=[])

    def costs(self):
        return capacity_demand.measured_costs(since=AT - timedelta(days=7),
                                              until=AT)

    def hourly(self, name, task="some.task", **kwargs):
        return beat(name, task=task, crontab_row=crontab(minute="0"),
                    **kwargs)

    def test_a_measured_setting_costs_its_own_mean(self):
        self.sample("nightly-harvest", "registry.tasks.harvest", active=120.0)
        costs = self.costs()
        self.assertEqual(costs["source"], "measured_worker")
        entry = costs["by_periodic_name"]["nightly-harvest"]
        self.assertAlmostEqual(entry["mean_seconds"], 120.0)
        self.assertEqual(entry["samples"], 3)

    def test_an_unmeasured_setting_falls_back_to_the_task_mean_labeled(self):
        self.sample("measured-row", "shared.task", active=10.0)
        self.hourly("measured-row", task="shared.task")
        self.hourly("unmeasured-row", task="shared.task")
        demand = capacity_demand.periodic_demand(
            AT, horizon_days=1, costs=self.costs())
        entry = demand["queues"][QUEUE]
        # both rows fire hourly; the second costs what the task class was
        # measured to cost, and the answer says which of the two it is
        self.assertEqual(entry["cost_sources"],
                         {"periodic_name": 1, "task_average": 1, "unknown": 0})
        self.assertEqual(entry["cost_coverage"], 1.0)

    def test_fewer_samples_than_the_minimum_answer_no_cost(self):
        self.sample("thin-samples", "thin.task", active=10.0, count=2)
        costs = self.costs()
        self.assertNotIn("thin-samples", costs["by_periodic_name"])
        self.assertNotIn("thin.task", costs["by_task_name"])

    def test_an_uncosted_schedule_keeps_the_demand_a_labeled_lower_bound(self):
        self.sample("costed", "costed.task", active=60.0)
        self.hourly("costed", task="costed.task")
        self.hourly("nobody-measured-this", task="unmeasured.task")
        demand = capacity_demand.periodic_demand(
            AT, horizon_days=1, costs=self.costs())
        totals = demand["totals"]
        self.assertEqual(totals["occurrences"], 48)  # two hourly rows, 24 h
        self.assertAlmostEqual(totals["periodic_demand_worker_seconds"],
                               24 * 60.0)
        self.assertEqual(totals["cost_coverage"], 0.5)
        # without any cost at all the seconds stay null rather than becoming 0
        bare = capacity_demand.periodic_demand(AT, horizon_days=1)
        self.assertIsNone(bare["totals"]["periodic_demand_worker_seconds"])
        self.assertEqual(bare["totals"]["occurrences"], 48)

    def test_histogram_answers_slot_seconds_per_window(self):
        self.sample("hourly", "hourly.task", active=60.0)
        self.hourly("hourly", task="hourly.task")
        demand = capacity_demand.periodic_demand(
            AT, horizon_days=7, costs=self.costs())
        entry = demand["queues"][QUEUE]
        buckets = demand["horizon"]["buckets"]
        self.assertEqual(len(entry["histogram_seconds"]), buckets)
        self.assertEqual(len(entry["histogram_occurrences"]), buckets)
        # the two histograms sum to the totals they belong to - and the
        # seconds histogram answers *seconds*, not a count of settings
        self.assertAlmostEqual(sum(entry["histogram_seconds"]),
                               entry["demand_worker_seconds"])
        self.assertEqual(sum(entry["histogram_occurrences"]),
                         entry["occurrences"])
        self.assertAlmostEqual(entry["histogram_seconds"][0], 60.0)


@override_settings(CACHES=LOC_MEM)
class QueueRoutingTests(TestCase):
    """Which queue a dispatch lands on - the producer's precedence."""

    def setUp(self):
        cache.clear()
        PeriodicTask.objects.filter(enabled=True).update(enabled=False)

    def test_the_row_queue_wins_then_the_declaration_then_the_default(self):
        hourly = crontab(minute="0")
        beat("explicit", queue="explicit-queue", crontab_row=hourly)
        beat("declared", task="registry.tasks.monitoring.run_probe_check",
             queue="", crontab_row=hourly)
        beat("undirected", task="nobody.routes.this.task", queue="",
             crontab_row=hourly)
        demand = capacity_demand.periodic_demand(
            AT, horizon_days=1,
            task_routes={"registry.tasks.monitoring.run_probe_check":
                         "monitoring"})
        queues = demand["queues"]
        self.assertIn("explicit-queue", queues)
        self.assertIn("monitoring", queues)
        self.assertIn(app.conf.task_default_queue, queues)


@override_settings(CACHES=LOC_MEM)
class WalkBudgetTests(TestCase):
    """A deployment that outruns a budget stops counting and says so."""

    def setUp(self):
        cache.clear()
        PeriodicTask.objects.filter(enabled=True).update(enabled=False)

    def test_per_setting_budget_truncates_and_is_reported(self):
        beat("dense", crontab_row=crontab(minute="*/5"))
        with override_settings(
                CAPACITY_SNAPSHOT_MAX_OCCURRENCES_PER_SETTING=10):
            demand = capacity_demand.periodic_demand(AT, horizon_days=7)
        self.assertEqual(demand["totals"]["occurrences"], 10)
        self.assertEqual(demand["schedules"]["truncated_settings"], 1)
        self.assertTrue(demand["walk"]["truncated_settings"])
        # the total budget is nowhere near exhausted: only this row stopped
        self.assertFalse(demand["walk"]["budget_exhausted"])

    def test_total_budget_exhaustion_is_reported(self):
        dense = crontab(minute="*/5")
        for index in range(5):
            beat(f"dense-{index}", crontab_row=dense)
        with override_settings(CAPACITY_SNAPSHOT_MAX_OCCURRENCES=20):
            demand = capacity_demand.periodic_demand(AT, horizon_days=7)
        self.assertEqual(demand["walk"]["occurrences_used"], 20)
        self.assertTrue(demand["walk"]["budget_exhausted"])
        self.assertGreaterEqual(demand["schedules"]["truncated_settings"], 1)


@override_settings(CACHES=LOC_MEM)
class UnreadableScheduleTests(TestCase):
    """A definition this Celery cannot build neither fakes nor breaks."""

    def setUp(self):
        cache.clear()
        PeriodicTask.objects.filter(enabled=True).update(enabled=False)

    def test_one_broken_definition_is_named_and_the_walk_continues(self):
        """django-celery-beat's validator accepts ``day_of_week="7"`` (its own
        help text advertises "Sunday is 0 or 7") while Celery 5.7 refuses to
        build it - so beat can never dispatch the row either. The answer names
        the row and keeps answering about the rest of the deployment."""
        beat("sunday-as-seven",
             crontab_row=crontab(minute="0", hour="0", day_of_week="7"))
        beat("sane", crontab_row=crontab(minute="0"))
        demand = capacity_demand.periodic_demand(AT, horizon_days=1)
        self.assertEqual(demand["schedules"]["excluded"]["unreadable"], 1)
        self.assertEqual(list(demand["schedules"]["unreadable_examples"]),
                         ["sunday-as-seven"])
        self.assertEqual(demand["schedules"]["walked"], 1)
        self.assertEqual(demand["queues"][QUEUE]["occurrences"], 24)


@override_settings(CACHES=LOC_MEM)
class ScheduleFingerprintTests(TestCase):
    """The fingerprint moves with definitions, not with beat's bookkeeping."""

    def setUp(self):
        cache.clear()
        PeriodicTask.objects.filter(enabled=True).update(enabled=False)

    def fingerprint(self):
        return capacity_demand.schedule_fingerprint(force=True)

    def test_bookkeeping_saves_do_not_move_the_fingerprint(self):
        """Beat saves ``last_run_at`` on every dispatch; a fingerprint that
        moved with it would rebuild the snapshot once per fire of the fleet."""
        row = beat("hourly", crontab_row=crontab(minute="0"))
        before = self.fingerprint()
        row.last_run_at = AT
        row.total_run_count = 41
        row.save()
        self.assertEqual(self.fingerprint(), before)

    def test_editing_a_shared_crontab_row_in_place_moves_it(self):
        """Hundreds of services share one crontab row; retiming that row is
        the biggest demand change a deployment can make in one save, and no
        task row changes by a byte when it happens."""
        row = beat("hourly", crontab_row=crontab(minute="0"))
        before = self.fingerprint()
        shared = row.crontab
        shared.minute = "*/15"
        shared.save()
        self.assertNotEqual(self.fingerprint(), before)

    def test_adding_and_removing_a_row_moves_it(self):
        before = self.fingerprint()
        beat("hourly", crontab_row=crontab(minute="0"))
        after = self.fingerprint()
        self.assertNotEqual(before, after)
        PeriodicTask.objects.all().delete()
        self.assertNotEqual(self.fingerprint(), after)

    def test_the_cached_answer_is_used_within_its_own_interval(self):
        beat("hourly", crontab_row=crontab(minute="0"))
        first = capacity_demand.schedule_fingerprint()
        row = PeriodicTask.objects.get(name="hourly")
        row.crontab.minute = "*/15"
        row.crontab.save()
        # not forced: the reader of a snapshot pays at most one fold per
        # CAPACITY_FINGERPRINT_CACHE_SECONDS, not one per request
        self.assertEqual(capacity_demand.schedule_fingerprint(), first)
        self.assertNotEqual(capacity_demand.schedule_fingerprint(force=True),
                            first)


@override_settings(CACHES=LOC_MEM)
class DeploymentScaleTests(TestCase):
    """The acceptance bound of #1326: 43k schedules cost one bounded build."""

    def setUp(self):
        cache.clear()
        PeriodicTask.objects.filter(enabled=True).update(enabled=False)

    def test_43k_schedules_stay_inside_the_budget_and_a_bounded_time(self):
        schedules = [
            crontab(minute="*/30"),
            crontab(minute="0", hour="2"),
            crontab(minute="15"),
        ]
        PeriodicTask.objects.bulk_create([
            PeriodicTask(
                name=f"service-{index}-probe",
                task="registry.tasks.monitoring.run_probe_check",
                queue="monitoring", crontab=schedules[index % 3],
                last_run_at=BEFORE, enabled=True)
            for index in range(43_000)])

        demand = capacity_demand.periodic_demand(AT, horizon_days=7)
        walk = demand["walk"]

        # every row was looked at
        self.assertEqual(demand["schedules"]["walked"], 43_000)
        # rows of this shape promise ~7M dispatches over a week; the budget is
        # what bounds one build, and spending it is reported, not hidden
        self.assertTrue(walk["budget_exhausted"])
        self.assertEqual(walk["occurrences_used"], walk["occurrences_budget"])
        self.assertGreaterEqual(demand["schedules"]["truncated_settings"], 1)
        # and the walk stayed fast enough that beat can run it on a cadence
        self.assertLess(walk["seconds"], 60.0)
