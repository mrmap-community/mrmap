"""What the schedules of the deployment expect inside a horizon (#1326).

This is the demand side of the capacity snapshot. It answers, per queue and
per time window, how many dispatches the enabled schedules still promise and
how many **worker slot seconds** those dispatches are expected to occupy -
and it answers from the same Beat semantics the scheduler dispatches by
(``extras.scheduling.next_run_after`` is the one occurrence step, Celery's
own crontab arithmetic is the one rule), never from a re-derived cron.

The honesty rules are the module:

*   the walk covers ``(at, at + horizon]`` only - a finite horizon is stated,
    not a permanent rate; a monthly schedule that fires outside the horizon
    contributes nothing and the limitation is named, not extrapolated;
*   an occurrence costs what it was *measured* to cost: the mean occupied
    slot seconds of its terminal attempt samples (#1330), per beat setting
    name first and per task class second. A schedule nobody measured
    contributes **occurrences without seconds**, which keeps the total
    demand a labeled lower bound with its coverage, never a guessed number;
*   a disabled, expired, already-ran one-off or unscheduled setting fires
    nothing and is counted as excluded with its reason;
*   a definition this Celery cannot build at all (the day-of-week ``"7"``
    which django-celery-beat's validator accepts and Celery 5.7 rejects is
    the known one) is counted as unreadable and left out by its own row -
    one broken definition neither fakes demand nor takes the answer down;
*   the walk itself is budgeted (settings, occurrences per setting, occur-
    rences in total). A deployment that outruns a budget stops counting and
    says so - the cost of one build stays bounded by construction, which is
    what lets the snapshot be rebuilt without paging through 43k settings on
    a request path.

Occurrence counting uses a per-wall-clock-day grid whenever the day does not
change its UTC offset: within such a day the crontab's occurrences are the
product of its hour and minute sets, which is the same sequence Celery's
``crontab`` steps through (its day match is the AND of day-of-week,
day-of-month and month-of-year, and its ``ffwd`` arithmetic is a wall-clock
``replace`` in the schedule's zone - for a ``zoneinfo`` zone the grid's
construction of the same wall time is the same instant). Days that change
the offset walk the canonical step instead; what a snapshot then reports for
those two days a year per zone is the stepped answer, and the difference a
*late* dispatch makes to the rest of such a day is the walk's one named
limitation.
"""

import hashlib
import importlib
from bisect import bisect_right
from datetime import datetime, timedelta, timezone
from logging import Logger
from time import monotonic

from django.apps import apps
from django.conf import settings
from django.core.cache import cache
# ``timezone`` is taken by ``datetime`` in this module (the walk needs
# ``timezone.utc``), so the django clock arrives under its own name
from django.utils import timezone as util_timezone
from django_celery_beat.models import (CrontabSchedule, IntervalSchedule,
                                       PeriodicTask)
from extras.scheduling import next_run_after
from MrMap.celery import app

from system import capacity_measures

logger: Logger = settings.ROOT_LOGGER

#: the cache key of the schedule fingerprint; a changed value is the one
#: machine-readable fact that says the counted demand is out of date
FINGERPRINT_CACHE_KEY = "mrmap-capacity-schedule-fingerprint"

#: the fields that decide what a schedule will dispatch within a horizon.
#: ``last_run_at``/``total_run_count``/``date_changed`` are deliberately
#: *not* in the fold: beat's bookkeeping saves touch exactly those (plus the
#: auto ``date_changed``) on every dispatch, and a fingerprint that moved
#: with them would rebuild the snapshot on every fire of the fleet. Their
#: effect on the window is bounded: the walk starts from ``max(baseline, at)``
#: and a snapshot is never older than its TTL, so a dispatch that happened
#: after the build only ever *removes* an occurrence the horizon has already
#: passed - which keeps the demand a labeled lower bound, never an invented
#: one. ``enabled`` and ``expires`` ARE in the fold: beat disables rows on
#: expiry, which is exactly a schedule-set change.
FINGERPRINT_FIELDS = (
    "id", "name", "task", "queue", "enabled", "one_off",
    "start_time", "expires", "crontab_id", "interval_id")

#: the content of the shared schedule rows, folded alongside the task rows:
#: a task points at a crontab row by id, so editing that row in place - the
#: way a deployment retimes hundreds of services with one save - has to move
#: the fingerprint too. Every field which decides a firing moment is in it;
#: ``description`` and ``comment`` are not, they decide nothing.
CRONTAB_FOLD_FIELDS = ("id", "minute", "hour", "day_of_week", "day_of_month",
                       "month_of_year", "timezone")
INTERVAL_FOLD_FIELDS = ("id", "every", "period")

#: a deployment with 43k settings holds a handful of distinct crontab rows;
#: the Celery field-set expansion is paid once per row, never per setting
_SCHEDULE_CACHE_LIMIT = 2_000

#: the cached "no occurrences for this wall-clock day" answer - an empty
#: list would be ambiguous against the day the grid refuses to answer
_NO_DAY = ()


class _WalkBudget:
    """The occurrence budgets of one walk, shared across its settings."""

    def __init__(self, total, per_setting):
        self.total = total
        self.per_setting = per_setting
        self.used = 0
        self.exhausted = False
        self.truncated_settings = 0

    def take(self):
        """Whether one more occurrence still fits; consumes it."""
        if self.used + 1 > self.total:
            self.exhausted = True
            return False
        self.used += 1
        return True


class _CrontabView:
    """The ``extras.scheduling`` view of one stored crontab row.

    ``next_run_after`` reads ``crontab.timezone`` and ``crontab.schedule``;
    the model's ``schedule`` property builds a fresh Celery crontab per
    access (its field-set expansion is the expensive part), so this hands
    out the row's timezone directly and the build's cached Celery schedule -
    the same object Beat evaluates.
    """

    def __init__(self, crontab, schedules):
        self._crontab = crontab
        self._schedules = schedules

    @property
    def timezone(self):
        return self._crontab.timezone

    @property
    def schedule(self):
        return _celery_schedule(self._crontab, self._schedules)


class _Effective:
    """The ``extras.scheduling`` view of one beat row."""

    def __init__(self, task_row, schedules):
        self.crontab = _CrontabView(task_row.crontab, schedules)


def _celery_schedule(crontab, cache_by_pk):
    """The Celery crontab of a stored CrontabSchedule, once per row."""
    schedule = cache_by_pk.get(crontab.pk)
    if schedule is None:
        schedule = crontab.schedule
        if len(cache_by_pk) < _SCHEDULE_CACHE_LIMIT:
            cache_by_pk[crontab.pk] = schedule
    return schedule


class _DayGrids:
    """The per-wall-clock-day occurrence grids of one crontab row.

    :data:`_NO_DAY` answers a day the crontab matches no occurrence on and a
    day that changes its UTC offset - both walk the canonical step; a list
    answers the sorted aware instants of the day otherwise. Built lazily,
    shared by every setting with the same crontab row, dropped with the
    build.
    """

    def __init__(self, crontab, tz):
        self.crontab = crontab
        self.tz = tz
        self._days = {}

    def day(self, day):
        cached = self._days.get(day)
        if cached is not None:
            return cached
        grid = self._build(day)
        grid = _NO_DAY if grid is None else grid
        self._days[day] = grid
        return grid

    def _build(self, day):
        # the day match is Celery's: the AND of the three expanded sets,
        # with the Sunday-is-0 weekday numbering Celery normalizes to
        if not (day.month in self.crontab.month_of_year
                and day.day in self.crontab.day_of_month
                and (day.isoweekday() % 7) in self.crontab.day_of_week):
            return None
        if self._changes_offset(day):
            return None
        instants = []
        for hour in sorted(self.crontab.hour):
            for minute in sorted(self.crontab.minute):
                instants.append(
                    datetime(day.year, day.month, day.day, hour, minute,
                             tzinfo=self.tz))
        return instants

    def _changes_offset(self, day):
        """Whether the UTC offset of the day differs 24 h further.

        Compares start-of-day to the same instant plus a day: every zone of
        the IANA database which transitions inside a snapshot horizon
        changes its offset overnight that way. A zone that changed and
        changed back within the same 24 h would go undetected - the named
        limitation of the grid, which no future transition of a deployment's
        zones does.
        """
        start = datetime(day.year, day.month, day.day, tzinfo=self.tz)
        return start.utcoffset() != (
            start + timedelta(days=1)).utcoffset()


def _baseline_of(row, at):
    """The Beat baseline the walk starts from, floored at the snapshot moment.

    ``next_run_expected_at`` documents the baseline beat itself uses:
    ``last_run_at`` of a dispatched row, its ``date_changed`` while it never
    dispatched, floored by ``start_time``. Strictly *after* that baseline is
    what still fires; floored at ``at`` because a snapshot counts future
    dispatches only.
    """
    baseline = row.last_run_at or row.date_changed
    if baseline is None:
        baseline = at
    if row.start_time is not None:
        baseline = max(baseline, row.start_time)
    return max(baseline, at)


def _grid_next(grids, t):
    """The next wall-clock-grid instant of t's day, None on offset days.

    ``None`` means "no fast path here": the caller steps with Beat's
    canonical ``next_run_after`` instead. Days whose UTC offset changes
    carry no grid for exactly that reason.
    """
    day_instants = grids.day(t.date())
    if day_instants is _NO_DAY:
        return None
    index = bisect_right(day_instants, t)
    if index < len(day_instants):
        return day_instants[index]
    return None


def _count_crontab_occurrences(row, lower, upper, one_off, budgets,
                               schedules, grids_by_pk):
    """The instants the crontab of a row still fires within (lower, upper].

    Returns:
        tuple: ``(instants, truncated)`` - ``truncated`` says a walk budget
            ended the count, which the caller reports as a partial answer
            instead of a whole one.
    """
    crontab = row.crontab
    if crontab.pk not in grids_by_pk:
        grids_by_pk[crontab.pk] = _DayGrids(
            _celery_schedule(crontab, schedules), crontab.timezone)
    grids = grids_by_pk[crontab.pk]

    effective = _Effective(row, schedules)
    instants = []
    truncated = False
    t = next_run_after(effective, lower)
    while t is not None and t <= upper:
        if one_off:
            instants.append(t)
            break  # beat disables the row after its first dispatch
        if len(instants) + 1 > budgets.per_setting or not budgets.take():
            truncated = True
            break
        instants.append(t)
        # the fast path: the next grid instant of the same wall-clock day
        nxt = _grid_next(grids, t)
        t = nxt if nxt is not None else next_run_after(effective, t)
    if truncated:
        budgets.truncated_settings += 1
    return instants, truncated


class _CrontabHolder:
    """The ``extras.scheduling`` view of a bare crontab row (no task row)."""

    def __init__(self, view):
        self.crontab = view


def walk_crontab(crontab, lower, upper, max_occurrences):
    """The instants a crontab fires within (lower, upper], bounded walk.

    Public so the cadence check of #1328 can count the occurrences of an
    **unsaved** `CrontabSchedule` through the very same stepping the
    snapshot walks saved rows with: the wall-clock grid on steady days, the
    canonical Beat step (`next_run_after`) where the grid refuses - the
    offset-changing day included. A proposal is therefore counted by the
    same Celery arithmetic the dispatch will later obey, and original and
    alternative are compared over an identical window.

    Args:
        crontab (CrontabSchedule): the saved or unsaved row to step
        lower (datetime): the exclusive lower bound the walk starts from
        upper (datetime): the inclusive upper bound of the window
        max_occurrences (int): the budget; more ends the walk as truncated

    Returns:
        tuple: ``(instants, truncated)`` - a truncated count is a partial
            answer, so a caller verifying counts must treat it as no answer.
    """
    schedules = {}
    schedule = _celery_schedule(crontab, schedules)
    grids = _DayGrids(schedule, crontab.timezone)
    effective = _CrontabHolder(_CrontabView(crontab, schedules))
    instants = []
    truncated = False
    t = next_run_after(effective, lower)
    while t is not None and t <= upper:
        if len(instants) + 1 > max_occurrences:
            truncated = True
            break
        instants.append(t)
        nxt = _grid_next(grids, t)
        t = nxt if nxt is not None else next_run_after(effective, t)
    return instants, truncated


def _count_interval_occurrences(row, lower, upper, one_off, budgets):
    """The dispatches an interval schedule still fires within (lower, upper].

    Celery's interval schedule answers ``last_run_at + run_every`` and beat
    re-baselines on every dispatch - the same instants as the arithmetic
    grid ``baseline + k * every`` starting strictly after ``lower``. No
    walk is needed: the count falls out of the division.
    """
    every = row.interval.schedule.run_every
    baseline = row.last_run_at or row.date_changed
    if baseline is None:
        baseline = lower
    if row.start_time is not None:
        baseline = max(baseline, row.start_time)
    start = max(baseline, lower)
    every_seconds = every.total_seconds()
    if start >= upper or every_seconds <= 0:
        return [], False
    k = int((start - baseline).total_seconds() // every_seconds) + 1
    instants = []
    truncated = False
    while True:
        t = baseline + every * k
        if t > upper:
            break
        if one_off:
            instants.append(t)
            break
        if len(instants) + 1 > budgets.per_setting or not budgets.take():
            truncated = True
            break
        instants.append(t)
        k += 1
    if truncated:
        budgets.truncated_settings += 1
    return instants, truncated


def queue_of(row, task_routes, default_queue):
    """The queue a dispatch of this row lands on.

    ``PeriodicTask.queue`` is what beat hands the producer (it overrides the
    task declaration); without it the task's ``queue=`` declaration decides,
    and the broker default answers the rest (``MrMap/celery_queues.py``).
    """
    if row.queue:
        return row.queue
    return task_routes.get(row.task) or default_queue


def schedule_fingerprint(force=False):
    """A digest of what the schedules will dispatch, cheap and bounded.

    The fingerprint folds :data:`FINGERPRINT_FIELDS` over every beat row and
    the content of the distinct crontab and interval rows those tasks point
    at, and is cached for ``CAPACITY_FINGERPRINT_CACHE_SECONDS``, so the
    reader of a snapshot pays a few bounded reads of the schedule tables per
    that interval - and never per request. It moves exactly when the
    *definition* of the schedule set moves; beat's per-dispatch bookkeeping
    saves do not move it, which is what keeps a busy fleet from turning the
    snapshot into a rebuild-per-dispatch.
    """
    ttl = max(1, int(getattr(
        settings, "CAPACITY_FINGERPRINT_CACHE_SECONDS", 30)))
    if not force:
        cached = cache.get(FINGERPRINT_CACHE_KEY)
        if cached is not None:
            return cached
    digest = hashlib.sha256()
    count = 0
    for row in (PeriodicTask.objects
                .order_by("pk")
                .values_list(*FINGERPRINT_FIELDS)
                .iterator()):
        digest.update(repr(row).encode())
        count += 1
    # the fold above names the schedule rows a task points at, not their
    # content. Editing a shared crontab row in place - retiming "every hour"
    # to "every 15 minutes" is how a deployment moves hundreds of services at
    # once, and the task rows of those services do not change by a byte -
    # moves the whole demand. django-celery-beat reads exactly that as a
    # schedule change (its ``PeriodicTasks.changed`` fires for the schedule
    # tables too), so the definitions themselves are folded here. The tables
    # hold one row per *distinct* schedule, not one per task, and the fold is
    # one values_list read per table behind the same cache.
    for model, fields in ((CrontabSchedule, CRONTAB_FOLD_FIELDS),
                          (IntervalSchedule, INTERVAL_FOLD_FIELDS)):
        for row in (model.objects
                    .order_by("pk")
                    .values_list(*fields)
                    .iterator()):
            digest.update(repr(row).encode())
    value = f"{digest.hexdigest()}:{count}"
    cache.set(FINGERPRINT_CACHE_KEY, value, ttl)
    return value


#: the unit of every ``period`` an ``IntervalSchedule`` row may carry
_INTERVAL_UNITS = None


def _interval_units():
    global _INTERVAL_UNITS
    if _INTERVAL_UNITS is None:
        _INTERVAL_UNITS = {
            IntervalSchedule.SECONDS: 1,
            IntervalSchedule.MINUTES: 60,
            IntervalSchedule.HOURS: 3600,
            IntervalSchedule.DAYS: 86400,
        }
    return _INTERVAL_UNITS


def interval_seconds(every, period):
    """The seconds of one interval schedule, or None when unreadable."""
    try:
        unit = _interval_units().get(period)
        return None if unit is None else float(every) * unit
    except (TypeError, ValueError):  # dcb's validators rule these out
        return None


def schedule_intervals(max_interval_seconds, limit=None):
    """The live interval of every short-interval beat row, per setting name.

    Answers ``{setting_name: {"seconds", "task"}}`` for the enabled rows which
    fire on an **interval** schedule at least as often as
    ``max_interval_seconds``. Three bounds, because this is read on a beat
    cadence beside the walk of the demand side: interval schedules only (a
    crontab has no single interval to compare a duration against - and the
    per-service schedules of a big deployment are all crontabs), enabled
    non-one-off rows only, and a row count bound. A deployment whose beat rows
    are all crontabs therefore answers ``{}``, which is the honest "nothing to
    judge" and not an error.

    The queue is deliberately not answered here: a reader which wants it reads
    the queue the attempt actually ran on, which is the observed answer.
    """
    bound = float(max_interval_seconds)
    rows = (PeriodicTask.objects
            .filter(enabled=True, one_off=False)
            .exclude(interval_id=None)
            .select_related("interval")
            .order_by("pk")
            .values_list("name", "task", "interval__every",
                         "interval__period")
            [:int(limit if limit is not None
                  else getattr(settings, "CAPACITY_COST_GROUP_LIMIT", 5_000))])
    intervals = {}
    for name, task, every, period in rows:
        seconds = interval_seconds(every, period)
        if seconds is None or seconds <= 0 or seconds > bound:
            continue
        intervals[name] = {"seconds": seconds, "task": task}
    return intervals


def schedule_reachability(since, until=None, max_interval_seconds=None,
                          limit=200):
    """Every short-interval beat schedule beside its own measured duration.

    The join the deployment needs to answer "is this cadence reachable at all"
    (#1827): the interval a row fires on, against the p95 of the attempts THAT
    row dispatched, plus the fires of the same window the singleton lock
    dropped. A run which costs more than the interval it is scheduled with
    never fits, and every second fire is then refused by the lock - which no
    duration read of this module can see on its own, because a dropped fire
    measured nothing.

    Answers one entry per live interval beat row which has samples, keyed by
    the beat setting name, each with the measured duration, the interval, the
    drop share and the verdict of ``capacity_measures``:

    *   ``"unreachable"`` - the p95 exceeds the interval (``overrun_ratio``
        above 1.0): the schedule cannot be met at this size.
    *   ``"tight"`` - the p95 fits but with less headroom than asked for.
    *   ``"reachable"`` - the p95 fits with headroom.
    *   ``"unknown"`` - nothing measured for the row: it never fired, or its
        attempts carry no duration. Never answered as reachable.

    One grouped read for the samples side, one bounded read for the schedule
    side, and the join in Python over the two - never one query per schedule.
    """
    if max_interval_seconds is None:
        max_interval_seconds = getattr(
            settings, "TASK_PERFORMANCE_REACHABILITY_MAX_INTERVAL_SECONDS", 300)
    bound = float(max_interval_seconds)
    headroom = float(getattr(settings, "CAPACITY_REACHABILITY_HEADROOM", 1.1))
    minimum = int(getattr(settings, "CAPACITY_REACHABILITY_MIN_SAMPLES", 5))
    intervals = schedule_intervals(bound)
    if not intervals:
        return {
            "source": capacity_measures.SOURCE_MEASURED_WORKER,
            "window": {"since": since, "until": until or util_timezone.now()},
            "schedules": {},
            "truncated": False,
        }
    answer = capacity_measures.grouped_reachability(since, until, limit=limit)
    schedules = {}
    for group in answer["groups"]:
        entry = intervals.get(group["periodic_name"])
        if entry is None or group["task_name"] != entry["task"]:
            # an attempt of a task whose beat row this read does not cover
            # (the row was edited or removed, or the task fired by hand):
            # without a live interval there is no cadence to judge
            continue
        samples = group["samples"] or 0
        dropped = group["dropped"] or 0
        fires = samples + dropped
        p95 = group["active_p95"]
        if p95 is None or samples < minimum:
            verdict = "unknown"
        elif p95 > entry["seconds"]:
            verdict = "unreachable"
        elif p95 > entry["seconds"] / headroom:
            verdict = "tight"
        else:
            verdict = "reachable"
        key = f'{group["periodic_name"]}|{group["task_name"]}|{group["queue"]}'
        schedules[key] = {
            "periodic_name": group["periodic_name"],
            "task_name": group["task_name"],
            "queue": group["queue"],
            "interval_seconds": entry["seconds"],
            "samples": samples,
            "min_samples": minimum,
            "active_p95": p95,
            "active_max": group["active_max"],
            "dropped_fires": dropped,
            "fires": fires,
            "skipped_share": (dropped / fires) if fires else None,
            "overrun_ratio": (p95 / entry["seconds"])
            if p95 is not None else None,
            "verdict": verdict,
        }
    return {
        "source": answer["source"],
        "window": answer["window"],
        "headroom": headroom,
        "schedules": schedules,
        "truncated": answer["truncated"],
    }


def measured_costs(since, until=None):
    """The measured cost of one dispatch, per beat name and per task class.

    Reads the terminal attempt samples of #1330 through the sample API of
    ``system.capacity_measures`` - two bounded grouped queries, one grouped
    by the beat setting name and one by the task class. A name with fewer
    than ``CAPACITY_COST_MIN_SAMPLES`` terminal samples answers no cost; the
    caller then falls back to the task-class mean or reports the occurrences
    as uncosted, which is what keeps the demand honest.
    """
    limit = int(getattr(settings, "CAPACITY_COST_GROUP_LIMIT", 5_000))
    minimum = int(getattr(settings, "CAPACITY_COST_MIN_SAMPLES", 3))
    by_periodic = {}
    by_task = {}
    truncated = False
    for grouped, target, key in (
            (("periodic_name",), by_periodic, "periodic_name"),
            (("task_name",), by_task, "task_name")):
        answer = capacity_measures.grouped_measures(
            since=since, until=until, by=grouped, limit=limit)
        truncated = truncated or answer["truncated"]
        for group in answer["groups"]:
            name = group.get(key)
            samples = group["samples"] or 0
            slot_seconds = group["slot_seconds"]
            if not name or not samples or slot_seconds is None:
                continue
            if samples < minimum:
                continue
            target[name] = {
                "samples": samples,
                "mean_seconds": slot_seconds / samples,
            }
    return {
        "source": capacity_measures.SOURCE_MEASURED_WORKER,
        "window": {"since": since, "until": until},
        "by_periodic_name": by_periodic,
        "by_task_name": by_task,
        "truncated": truncated,
        "min_samples": minimum,
    }


def ensure_task_registry():
    """Import every app's ``tasks`` module, as a worker's finalize does.

    Task routing reads the ``queue=`` of the task declarations, and
    ``autodiscover_tasks`` is lazy: a web process which builds a snapshot on
    demand sees the routing a worker sees only after the modules are
    imported. Importing is idempotent and side-effect free.
    """
    for config in apps.get_app_configs():
        try:
            importlib.import_module(f"{config.name}.tasks")
        except ModuleNotFoundError:
            continue  # an app without tasks declares no routes


def _exclusion_of(row, at):
    """Why this row contributes no future demand, or None if it is walked.

    ``no_schedule`` can only be a row that reached the table without going
    through the model's own validation (dcb's ``save()`` refuses it); it is
    counted and named rather than crashing the walk.
    """
    if row.crontab_id is None and row.interval_id is None:
        return "no_schedule"
    if row.one_off and row.total_run_count > 0:
        return "one_off_ran"
    if row.expires is not None and row.expires <= at:
        return "expired"
    return None


def _walk_row(row, at, end, budgets, schedules, grids_by_pk):
    """The instants a live row still fires within the horizon.

    Beat disables a row once ``now`` reaches ``expires``: the dispatch
    exactly at the expiry moment is already no future demand - hence the
    exclusive upper bound when ``expires`` falls inside the horizon.
    """
    upper = end
    if row.expires is not None and row.expires < upper:
        upper = row.expires - timedelta(microseconds=1)
    lower = _baseline_of(row, at)
    if row.crontab_id is not None:
        instants, _truncated = _count_crontab_occurrences(
            row, lower, upper, row.one_off, budgets, schedules, grids_by_pk)
    else:
        instants, _truncated = _count_interval_occurrences(
            row, lower, upper, row.one_off, budgets)
    return instants


def _new_queue_entry(buckets):
    """A queue's demand accumulator: counts, seconds and both histograms."""
    return {
        "occurrences": 0,
        "costed_occurrences": 0,
        "demand_seconds": 0.0,
        "cost_sources": {"periodic_name": 0, "task_average": 0,
                         "unknown": 0},
        "histogram_seconds": [0.0] * buckets,
        "histogram_occurrences": [0] * buckets,
    }


def _accumulate_occurrences(entry, totals, instants, cost, at,
                            bucket_seconds, buckets):
    """Fold one walked row's instants into its queue and the grand totals."""
    for moment in instants:
        bucket = bucket_of(moment, at, bucket_seconds, buckets)
        entry["occurrences"] += 1
        entry["histogram_occurrences"][bucket] += 1
        totals["occurrences"] += 1
        if cost is not None:
            entry["costed_occurrences"] += 1
            entry["demand_seconds"] += cost
            entry["histogram_seconds"][bucket] += cost
            totals["demand_seconds"] += cost
            totals["costed"] += 1


def periodic_demand(at, horizon_days=None, costs=None, task_routes=None):
    """The periodic demand of the next ``horizon_days`` days, per queue.

    Args:
        at (datetime): the moment the horizon starts from (the snapshot
            moment); only dispatches strictly after it are counted
        horizon_days (int): the length of the horizon, default
            ``CAPACITY_SNAPSHOT_HORIZON_DAYS``
        costs (dict): a :func:`measured_costs` answer; without it every
            occurrence stays uncosted and the seconds stay null
        task_routes (dict): task name to queue map of the deployment
            (``system.capacity_topology.task_routes()``, with
            :func:`ensure_task_registry` run first)

    Returns:
        dict: ``horizon``, ``schedules`` (walked, excluded, truncated),
            ``queues`` (per queue: occurrences, expected worker seconds,
            their coverage and both histograms), ``totals`` and the
            ``walk`` cost bookkeeping. The histograms answer **expected slot
            seconds per time window** and the matching occurrence counts -
            never "settings per minute".
    """
    horizon_days = int(horizon_days or getattr(
        settings, "CAPACITY_SNAPSHOT_HORIZON_DAYS", 7))
    max_days = int(getattr(
        settings, "CAPACITY_SNAPSHOT_MAX_HORIZON_DAYS", 31))
    horizon_days = max(1, min(horizon_days, max_days))
    bucket_seconds = max(1, int(getattr(
        settings, "CAPACITY_SNAPSHOT_BUCKET_SECONDS", 3600)))
    max_buckets = int(getattr(settings, "CAPACITY_SNAPSHOT_MAX_BUCKETS", 744))
    end = at + timedelta(days=horizon_days)
    buckets = min(
        max(1, -(-int((end - at).total_seconds()) // bucket_seconds)),
        max_buckets)

    task_routes = task_routes or {}
    default_queue = app.conf.task_default_queue
    costs = costs or {"by_periodic_name": {}, "by_task_name": {}}
    budgets = _WalkBudget(
        total=int(getattr(
            settings, "CAPACITY_SNAPSHOT_MAX_OCCURRENCES", 2_000_000)),
        per_setting=int(getattr(
            settings, "CAPACITY_SNAPSHOT_MAX_OCCURRENCES_PER_SETTING",
            20_000)))

    started = monotonic()
    queues = {}
    walked = 0
    excluded = {"one_off_ran": 0, "expired": 0, "no_schedule": 0,
                "unreadable": 0}
    unreadable_reasons = {}
    totals = {"occurrences": 0, "demand_seconds": 0.0, "costed": 0}
    schedules = {}
    grids_by_pk = {}

    rows = (PeriodicTask.objects
            .select_related("crontab", "interval")
            .filter(enabled=True)
            .order_by("pk")[:int(getattr(
                settings, "CAPACITY_SNAPSHOT_MAX_SCHEDULES", 100_000))])
    for row in rows.iterator():
        reason = _exclusion_of(row, at)
        if reason is not None:
            excluded[reason] += 1
            continue
        try:
            instants = _walk_row(row, at, end, budgets, schedules,
                                 grids_by_pk)
        except Exception as error:
            # a definition this Celery refuses to build at all: the
            # day-of-week "7", which django-celery-beat's own validator
            # accepts (its help text advertises "Sunday is 0 or 7") while
            # Celery 5.7 rejects it as "Invalid end range: 7 > 6", is the
            # known shape. Beat cannot dispatch such a row either - but one
            # of them must not take the whole snapshot down. The row is
            # named, counted and left out: the demand keeps its meaning as
            # the lower bound it claims to be, and the answer names what
            # is missing instead of answering nothing at all.
            excluded["unreadable"] += 1
            unreadable_reasons[row.name] = (
                f"{type(error).__name__}: {error}"[:200])
            logger.debug("capacity demand: schedule %s cannot be walked: %s",
                         row.name, error)
            continue
        walked += 1

        queue = queue_of(row, task_routes, default_queue)
        entry = queues.setdefault(queue, _new_queue_entry(buckets))
        cost, source = _cost_of(row, costs)
        entry["cost_sources"][source if cost is not None else "unknown"] += 1
        _accumulate_occurrences(entry, totals, instants, cost, at,
                                bucket_seconds, buckets)

    for entry in queues.values():
        entry["demand_worker_seconds"] = _seconds_or_none(
            entry["demand_seconds"], entry["costed_occurrences"])
        entry["cost_coverage"] = _coverage(
            entry["costed_occurrences"], entry["occurrences"])

    return {
        "horizon": {
            "start": at, "end": end, "days": horizon_days,
            "bucket_seconds": bucket_seconds, "buckets": buckets,
        },
        "schedules": {
            "walked": walked,
            "excluded": excluded,
            "unreadable_examples": dict(sorted(
                unreadable_reasons.items())[:20]),
            "truncated_settings": budgets.truncated_settings,
        },
        "queues": queues,
        "totals": {
            "occurrences": totals["occurrences"],
            "periodic_demand_worker_seconds": _seconds_or_none(
                totals["demand_seconds"], totals["costed"]),
            "cost_coverage": _coverage(
                totals["costed"], totals["occurrences"]),
        },
        "walk": {
            "seconds": monotonic() - started,
            "occurrences_budget": budgets.total,
            "occurrences_used": budgets.used,
            "budget_exhausted": budgets.exhausted,
            "truncated_settings": budgets.truncated_settings,
        },
    }


def _cost_of(row, costs):
    """The measured seconds one dispatch of this row occupies a slot.

    The beat setting name first - its samples are exactly this schedule's
    dispatches - then the task class mean, a coarser answer which the caller
    still sees labeled ``task_average``, and nothing for schedules nobody
    measured. ``None`` is an answer; ``0`` would be a different one.
    """
    entry = costs.get("by_periodic_name", {}).get(row.name)
    if entry is not None:
        return entry["mean_seconds"], "periodic_name"
    entry = costs.get("by_task_name", {}).get(row.task)
    if entry is not None:
        return entry["mean_seconds"], "task_average"
    return None, None


def bucket_of(moment, start, bucket_seconds, buckets):
    """The histogram bucket an occurrence belongs to, 0-based.

    Bucket 0 covers the partial window from ``start`` to the first bucket
    boundary; the last bucket keeps every occurrence the horizon still
    counts beyond its window, so the two histograms always sum to the totals.
    """
    offset = (moment.astimezone(timezone.utc)
              - start.astimezone(timezone.utc)).total_seconds()
    index = int(offset // bucket_seconds)
    return max(0, min(index, buckets - 1))


def _seconds_or_none(total, costed):
    """The summed seconds - or nothing, when nothing was costed to sum."""
    return total if costed else None


def _coverage(costed, total):
    return None if not total else costed / total
