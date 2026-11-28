"""Reading what #1330 measured, in bounded queries (#1326's data layer).

These functions are the *sample API* the capacity snapshot endpoint of #1326
builds on. They keep the semantics the collector writes (see
``system.capacity_telemetry``) and add only honest labelling:

*   occupied worker seconds are summed **from terminal attempts only** - a
    4 h backlog in front of a 2 s task contributes 2 occupied slot-seconds
    and a 4 h *queue wait sample*, two separate answers (the acceptance
    example of #1330);
*   an empty window answers ``None`` for the durations, not ``0`` - "nothing
    measured" and "measured zero" are different statements;
*   open and abandoned attempts are reported as counts of *uncertain*
    observations, never converted into durations;
*   every answer carries ``source="measured_worker"`` and its sample count,
    the evidence class of epic #1324, so a reader can never present a global
    prior as this deployment's measurement.

Every function is one bounded query on the (queue, started_at) index with the
window required; none of them enumerates settings, services or schedules -
demand side (43k schedules) belongs to #1326, supply-and-consumption side
here.

:func:`window_buckets` is the one addition of epic #1387's V2 (#1391): the
same semantics of the same table, grouped per task class and queue for one
non-overlapping window, so a scheduled exporter - never a browser - can
publish what the task dashboard of the deployment shows.
"""

from datetime import timedelta

from django.conf import settings
from django.db import models
from django.db.models import (Avg, CharField, Count, Exists, F, FloatField,
                              Max, OuterRef, Q, Sum, Value)
from django.db.models.expressions import Func
from django.utils import timezone

from system.models import (AttemptOutcome, AttemptQuality,
                           CeleryTaskAttempt)


#: the duration columns a percentile may be asked of; the vocabulary is the
#: model's own, so no caller can steer the aggregate at another column
PERCENTILE_FIELDS = ("active_seconds", "wait_seconds")


class PercentileWithinGroup(models.Aggregate):
    """One percentile of a duration column of the attempt table, as one clause.

    Django dropped postgres' order-set aggregates with 5.0, and re-building
    the whole ``WITHIN GROUP`` machinery for this one number is not worth it:
    the SQL here is the documented form of the question, bound to a column
    the collector itself writes. The FILTER keeps the semantics of the read
    modules: a duration is read from attempts which *finished* and whose
    duration was actually measured - an unknown duration never joins the
    distribution as a zero.

    The column is named by the caller, so the same expression answers the
    queue wait of #1326 and the active seconds of #1390; only the attempt
    table's own duration columns are readable this way - the vocabulary is
    :data:`PERCENTILE_FIELDS`, the model's own, and the column is quoted
    through the connection rather than interpolated from caller text.
    """

    def __init__(self, column, quantile, **extra):
        self.column = str(column)
        self.quantile = float(quantile)
        super().__init__(output_field=FloatField(), **extra)

    def as_sql(self, compiler, connection, **extra_context):
        if self.column not in PERCENTILE_FIELDS:
            raise ValueError(
                "cannot take a percentile of %s, the measured duration "
                "columns are %s"
                % (self.column, ", ".join(PERCENTILE_FIELDS)))
        opts = CeleryTaskAttempt._meta
        try:
            column = opts.get_field(self.column).column
        except Exception:
            raise ValueError(
                f"'{self.column}' is no column of the attempt samples.")
        table = connection.ops.quote_name(opts.db_table)
        column = connection.ops.quote_name(column)
        outcome = connection.ops.quote_name(
            opts.get_field("outcome").column)
        sql = (
            "percentile_cont(%s) WITHIN GROUP (ORDER BY {table}.{column}) "
            "FILTER (WHERE {table}.{outcome} <> '' "
            "AND {table}.{column} IS NOT NULL)"
        ).format(table=table, column=column, outcome=outcome)
        return sql, [self.quantile]


class _WaitPercentile(PercentileWithinGroup):
    """The percentile of the measured queue waits (#1326's read)."""

    def __init__(self, quantile, **extra):
        super().__init__("wait_seconds", quantile, **extra)


#: the evidence class of epic #1324 this module answers with; a duration
#: carrying it was measured from worker signals of an actual execution
SOURCE_MEASURED_WORKER = "measured_worker"

#: the grouping dimensions #1326 may ask costs grouped by (issue text:
#: logical periodic setting type, queue, actual task class)
GROUP_DIMENSIONS = ("queue", "task_name", "periodic_name", "outcome")

#: how many dot separated parts of a task name name its class; the task
#: families of epic #1387's baseline are the modules below ``tasks`` -
#: ``registry.tasks.harvest`` is one class, ``registry`` alone would be a
#: whole app, and a deeper cut would split one function from itself
TASK_CLASS_PARTS = 3


def task_class_of(task_name):
    """The class a task name belongs to, off the name itself.

    The celery name of a first-party task is its dotted import path, so the
    module which declares it is its class: every task of
    ``registry/tasks/harvest.py`` shares one class, one cost profile and one
    threshold policy (#1390), and a periodic dispatch's ``periodic_name``
    stays the finer grouping inside it (#1326). A name shorter than the
    class depth - a bare ``add`` - answers itself, which is the honest
    answer for a task with no module to belong to.

    This is the only place the rule lives: the exporter of #1391 groups its
    rows with it, the dashboard aggregates by the value it produces, and
    :func:`window_buckets` reads it off the same code, so the dashboard's
    "task class" and the detector's "task class" cannot drift apart.
    """
    parts = (task_name or "").split(".")
    return ".".join(parts[:TASK_CLASS_PARTS]) or task_name


#: the capacity questions of #1326/#1330 ask what RAN in a period: a row
#: belongs to the window its attempt started in
WINDOW_RUN = "started_at"
#: the publication windows of #1391 partition the ledger by ARRIVAL: a row
#: belongs to the window the collector wrote it in, which is the only
#: attribution under which a series of non-overlapping windows can neither
#: lose the late flush of a worker nor count one row in two windows
WINDOW_WRITTEN = "recorded_at"


def _windowed(since, until=None, queue=None, task_name=None,
              periodic_name=None, attribution=WINDOW_RUN):
    """The base queryset of one bounded window, filters applied.

    ``since`` is mandatory on purpose: a scan over the unbounded table is
    exactly what the snapshot of #1326 may not do on a request path.

    ``attribution`` names the time column the window is measured against:
    :data:`WINDOW_RUN` (the default) selects ``[since, until]`` of
    ``started_at``, the closed window of a capacity question;
    :data:`WINDOW_WRITTEN` selects ``(since, until]`` of ``recorded_at``,
    the half-open window of the exporter of #1391, whose cursor IS the
    previous window's end: with a closed window a row written in exactly the
    cursor's moment would ride two windows, and with ``started_at`` a late
    flush of a finished attempt would ride none.
    """
    if attribution == WINDOW_WRITTEN:
        qs = CeleryTaskAttempt.objects.filter(recorded_at__gt=since)
        if until is not None:
            qs = qs.filter(recorded_at__lte=until)
    else:
        qs = CeleryTaskAttempt.objects.filter(started_at__gte=since)
        if until is not None:
            qs = qs.filter(started_at__lte=until)
    if queue is not None:
        qs = qs.filter(queue=queue)
    if task_name is not None:
        qs = qs.filter(task_name=task_name)
    if periodic_name is not None:
        qs = qs.filter(periodic_name=periodic_name)
    return qs


def _terminal_q():
    return ~Q(outcome="") & Q(active_seconds__isnull=False)


def _open_q():
    return Q(outcome="")


def _abandoned_q():
    """An open attempt the sweep of #1330 has declared without an end."""
    return Q(quality__contains=[AttemptQuality.ABANDONED.value])


def _uncertain_open_qs(since, until=None, queue=None, task_name=None,
                       periodic_name=None, attribution=WINDOW_RUN):
    """Open attempts for which NO terminal row of the same identity exists.

    An attempt that finished normally has its open row from an earlier flush
    sitting beside its terminal row; that pair is a completed execution, not
    an uncertain observation. Only open rows without a terminal counterpart
    are the crash residue #1330 promises to report as partial evidence.
    """
    terminal_twin = CeleryTaskAttempt.objects.filter(
        task_id=OuterRef("task_id"),
        attempt_no=OuterRef("attempt_no")).exclude(outcome="")
    return (_windowed(since, until, queue, task_name, periodic_name,
                      attribution=attribution)
            .annotate(has_terminal=Exists(terminal_twin))
            .filter(_open_q() & ~Q(has_terminal=True)))


def attempt_measures(since, until=None, queue=None, task_name=None,
                     periodic_name=None):
    """The measured occupancy and waiting of one window, as one dict.

    Keys (all durations ``None`` when nothing was measured in the window):

    ``occupied_slot_seconds``
        Sum of the active seconds of the terminal attempts - worker slot
        occupancy including remote waiting *inside* the task, never the
        broker time.
    ``attempts``
        ``{"total", "by_outcome", "retried"}`` of the terminal rows; one row
        per actual attempt, retries counted as their own attempts.
    ``uncertain``
        ``{"open_without_end", "abandoned"}`` - the partial/unknown class:
        executions nobody measured an end for. Never summed into the
        occupancy above.
    ``queue_wait``
        ``{"samples", "p50", "p95", "max", "mean"}`` seconds of enqueue→
        start; ``samples`` counts the attempts whose message carried the
        publish stamp - with no stamp the wait stays unknown and this stays
        None, which is the difference between the backlog of #1324's live
        rig and an actually observed one.
    ``coverage``
        How much of the window could be seen at all: terminal sample count,
        stamped share, and the ``source``/``window`` bookkeeping #1326 must
        carry into its snapshot (sample size, window, timestamp).
    """
    window = {
        "since": since, "until": until or timezone.now(),
    }
    terminal = _windowed(since, until, queue, task_name, periodic_name)
    stats = terminal.aggregate(
        samples=Count("pk", filter=_terminal_q()),
        slot_seconds=Sum("active_seconds", filter=_terminal_q()),
        succeeded=Count("pk", filter=(
            _terminal_q() & Q(outcome=AttemptOutcome.SUCCESS.value))),
        failed=Count("pk", filter=(
            _terminal_q() & Q(outcome=AttemptOutcome.FAILURE.value))),
        retried=Count("pk", filter=(
            _terminal_q() & Q(outcome=AttemptOutcome.RETRY.value))),
        revoked=Count("pk", filter=(
            _terminal_q() & Q(outcome=AttemptOutcome.REVOKED.value))),
        # a dropped fire never executed, so it is not a terminal sample and
        # not in ``samples`` either: its own count is the answer (#1827)
        skipped=Count("pk", filter=Q(
            outcome=AttemptOutcome.SKIPPED.value)),
        wait_samples=Count("pk", filter=(
            _terminal_q() & Q(wait_seconds__isnull=False))),
        wait_p50=_WaitPercentile(0.5),
        wait_p95=_WaitPercentile(0.95),
        wait_max=Max("wait_seconds", filter=(
            _terminal_q() & Q(wait_seconds__isnull=False))),
        wait_mean=Avg("wait_seconds", filter=(
            _terminal_q() & Q(wait_seconds__isnull=False))),
        active_mean=Avg("active_seconds", filter=_terminal_q()),
    )

    uncertain_qs = _uncertain_open_qs(since, until, queue, task_name,
                                      periodic_name)
    uncertain_total = uncertain_qs.count()
    abandoned = uncertain_qs.filter(
        quality__contains=[AttemptQuality.ABANDONED.value]).count()

    samples = stats["samples"] or 0
    wait_samples = stats["wait_samples"] or 0
    return {
        "source": SOURCE_MEASURED_WORKER,
        "window": window,
        "occupied_slot_seconds": (stats["slot_seconds"]
                                  if samples else None),
        "mean_active_seconds": stats["active_mean"] if samples else None,
        "attempts": {
            "total": samples,
            "by_outcome": {
                AttemptOutcome.SUCCESS.value: stats["succeeded"],
                AttemptOutcome.FAILURE.value: stats["failed"],
                AttemptOutcome.RETRY.value: stats["retried"],
                AttemptOutcome.REVOKED.value: stats["revoked"],
            },
            # the fires a singleton lock dropped in this window: never in
            # ``total`` (nothing executed), reported here so the share of
            # dropped fires of a schedule is a number and not a grep (#1827)
            "dropped_fires": stats["skipped"],
        },
        "uncertain": {
            "open_without_end": uncertain_total,
            "abandoned": abandoned,
        },
        "queue_wait": None if not wait_samples else {
            "samples": wait_samples,
            "p50": stats["wait_p50"],
            "p95": stats["wait_p95"],
            "max": stats["wait_max"],
            "mean": stats["wait_mean"],
        },
        "coverage": {
            "terminal_samples": samples,
            "stamped_samples": wait_samples,
            # share of terminal attempts whose queue wait was measurable
            "wait_coverage": (wait_samples / samples) if samples else None,
        },
    }


def grouped_measures(since, until=None, by=("queue", "task_name"),
                     limit=200):
    """Occupancy grouped by the dimensions #1326 costs its pools with.

    One grouped, bounded query over the terminal rows of the window; the
    answer is ordered by the heaviest group first and cut off at ``limit``,
    with ``truncated`` saying so - the cost table of 43k settings must not
    come back unbounded on a request path either.
    """
    by = tuple(dict.fromkeys(by))
    unknown = [name for name in by if name not in GROUP_DIMENSIONS]
    if unknown:
        raise ValueError(
            "cannot group attempts by %s, the measured dimensions are %s"
            % (", ".join(sorted(unknown)), ", ".join(GROUP_DIMENSIONS)))
    qs = (_windowed(since, until)
          .filter(_terminal_q())
          .values(*by)
          .annotate(slot_seconds=Sum("active_seconds"),
                    samples=Count("pk"))
          .order_by("-slot_seconds"))
    rows = list(qs[:limit + 1])
    truncated = len(rows) > limit
    return {
        "source": SOURCE_MEASURED_WORKER,
        "grouped_by": list(by),
        "groups": rows[:limit],
        "truncated": truncated,
    }


def grouped_reachability(since, until=None, limit=200):
    """The measured duration AND the dropped fires of every beat name.

    One grouped, bounded read over the windowed attempt index, keyed by the
    beat setting name - the identity a schedule dispatches under - and the
    task class and queue it really ran on. Answers per group:

    ``samples``
        terminal attempts of the window, the ones which ran and measured a
        duration; the p95 belongs to exactly these rows.
    ``active_p95``
        the 95th percentile of those occupied slot seconds, or None when
        nothing was measured - which is unknown, not fast.
    ``dropped``
        the fires the singleton lock refused in the same window (#1827).
        Those rows never executed and carry no duration, so they are in
        neither ``samples`` nor the p95: their count beside them is what
        makes "half the fires were dropped" a number instead of a grep of
        INFO lines.

    The p95 is what a cadence is judged with: a schedule is only reachable
    when its unlucky run still fits inside the interval it fires on.
    """
    rows = (_windowed(since, until)
            .values("periodic_name", "task_name", "queue")
            .annotate(
                samples=Count("pk", filter=_terminal_q()),
                active_p95=PercentileWithinGroup("active_seconds", 0.95),
                active_max=Max("active_seconds", filter=_terminal_q()),
                dropped=Count("pk", filter=Q(
                    outcome=AttemptOutcome.SKIPPED.value)))
            .order_by("-samples"))
    rows = list(rows[:limit + 1])
    truncated = len(rows) > limit
    return {
        "source": SOURCE_MEASURED_WORKER,
        "window": {"since": since, "until": until or timezone.now()},
        "grouped_by": ["periodic_name", "task_name", "queue"],
        "groups": rows[:limit],
        "truncated": truncated,
    }


def measured_p95_of_periodic_task(periodic_name, task_name=None,
                                  since=None, minutes=6 * 60,
                                  min_samples=None):
    """The p95 completed duration of ONE beat schedule, or None.

    The one-schedule form of :func:`grouped_reachability`, for the caller
    which asks about a single cadence instead of building a panel: the refresh
    of the alert rows reads its own measurement at migrate time, so the
    interval a fresh row gets IS the number this read answers (#1827).

    ``None`` means "nothing measured", which is never an answer of "fast
    enough": a caller must not conclude reachability from the absence of a
    number. The window keeps the read on the recent behaviour of the
    deployment - the size-dependent duration this is about moves with the
    catalogue, and a p95 over the whole retention would be a p95 of history.
    """
    since = (timezone.now() - timedelta(minutes=max(1, int(minutes)))
             if since is None else since)
    minimum = (int(getattr(settings, "CAPACITY_REACHABILITY_MIN_SAMPLES", 5))
               if min_samples is None else int(min_samples))
    rows = (_windowed(since, None, task_name=task_name,
                      periodic_name=periodic_name)
            .aggregate(
                samples=Count("pk", filter=_terminal_q()),
                active_p95=PercentileWithinGroup("active_seconds", 0.95)))
    if not rows["samples"] or rows["samples"] < minimum:
        return None
    return rows["active_p95"]


def recent_samples(since, queue=None, task_name=None, limit=100):
    """The newest measured attempts of a window, schema-shaped (#1326's drill-down).

    Values only, bounded by ``limit``, and the value list is the module's
    own: it repeats the columns of the model and nothing else - the rows
    carry no argument, url or payload to leak, by construction.
    """
    qs = (_windowed(since, queue=queue, task_name=task_name)
          .order_by("-started_at")
          .values("task_id", "attempt_no", "task_name", "queue", "worker",
                  "root_id", "parent_id", "periodic_name", "published_at",
                  "started_at", "finished_at", "active_seconds",
                  "wait_seconds", "outcome", "quality", "recorded_at")
          [:limit])
    return list(qs)


#: the grouping dimension #1391's series is keyed by; the value of one task
#: name comes from :func:`task_class_of`, which the SQL expression of
#: :func:`_task_class_expression` mirrors (and whose test says it does)
TASK_CLASS_FIELD = "task_class"

#: the percentiles #1391's dashboard shows; stated once so the exporter, the
#: dashboard's legend and the answer of this module name the same three
#: numbers, and nobody has to guess which one a column is
ACTIVE_QUANTILES = (0.5, 0.95, 0.99)
WAIT_QUANTILES = (0.5, 0.95)

#: the ceiling of the per-class task-name read; a class is a module, so this
#: is a short list by construction and the bound only says what a pathological
#: set of names may not turn into
DISTINCT_TASK_NAME_BOUND = 500


class TaskClass(Func):
    """:func:`task_class_of` as one SQL expression, for one grouped query.

    The pattern anchors the first :data:`TASK_CLASS_PARTS` dot separated parts
    *plus whatever follows them* and the replacement answers only the anchor,
    so a longer name is shortened to its class while a name with fewer or
    exactly that many parts cannot match and comes back unchanged - which is
    what the Python rule does with a task simply named ``add``. Anchoring the
    parts alone would be a replacement of a match with itself, and a
    ``concat`` of three ``split_part`` calls cannot say it either: that
    function answers ``''`` past the end of the name, so it would answer
    ``add.``.

    One expression mirrors one function, which is a drift risk the test of
    ``tests.django.system.test_capacity_measures`` closes: it seeds names of
    every shape and asserts the grouped answer matches ``task_class_of`` for
    each of them, so the class the dashboard groups by and the class the
    policy of #1390 names cannot disagree quietly.
    """

    function = "REGEXP_REPLACE"
    output_field = CharField()

    def __init__(self, **extra):
        parts = TASK_CLASS_PARTS - 1
        super().__init__(
            F("task_name"),
            Value("^((?:[^.]+[.]){%d}[^.]+).*$" % parts),
            Value("\\1"),
            **extra)


def _aggregate_fields():
    """The aggregate clause of one bucket, for a grouped and a whole answer.

    Every duration aggregate rides :class:`PercentileWithinGroup`, so a
    duration which was never measured stays out of the distribution instead
    of joining it as a zero; the counts are the terminal rows of the window,
    outcome by outcome - a retry is its own attempt (#1330), which is what
    makes the retry panel of #1391 a count of attempts and not a count of
    tasks.
    """
    terminal = _terminal_q()
    stamped = terminal & Q(wait_seconds__isnull=False)
    fields = {
        "executions": Count("pk", filter=terminal),
        "slot_seconds": Sum("active_seconds", filter=terminal),
        "succeeded": Count("pk", filter=(
            terminal & Q(outcome=AttemptOutcome.SUCCESS.value))),
        "failed": Count("pk", filter=(
            terminal & Q(outcome=AttemptOutcome.FAILURE.value))),
        "retried": Count("pk", filter=(
            terminal & Q(outcome=AttemptOutcome.RETRY.value))),
        "revoked": Count("pk", filter=(
            terminal & Q(outcome=AttemptOutcome.REVOKED.value))),
        # the fires a singleton lock dropped (#1827): a fire which never ran
        # its body has no measured duration, so it is NOT a terminal sample of
        # ``_terminal_q()`` and joins none of the numbers above - this count
        # over its own outcome is the only place their share is visible
        "skipped": Count("pk", filter=Q(
            outcome=AttemptOutcome.SKIPPED.value)),
        "wait_samples": Count("pk", filter=stamped),
        "wait_max": Max("wait_seconds", filter=stamped),
        "active_max": Max("active_seconds", filter=terminal),
    }
    for quantile in ACTIVE_QUANTILES:
        fields[f"active_p{int(quantile * 100)}"] = PercentileWithinGroup(
            "active_seconds", quantile)
    for quantile in WAIT_QUANTILES:
        fields[f"wait_p{int(quantile * 100)}"] = PercentileWithinGroup(
            "wait_seconds", quantile)
    return fields


#: the duration columns of a bucket: a percentile or a maximum of an empty
#: distribution is unknown, never zero
_DURATION_FIELDS = (
    "slot_seconds", "active_max", "wait_max",
    "active_p50", "active_p95", "active_p99", "wait_p50", "wait_p95")

#: the count columns of a bucket: additive, and 0 is their honest answer for
#: a window in which nothing of that kind happened
_COUNT_FIELDS = ("executions", "succeeded", "failed", "retried", "revoked",
                 "skipped", "wait_samples")


def _bucket_row(stats):
    """One aggregate answer with its unmeasured durations turned into None.

    A group without terminal attempts has no distribution and answers
    ``None``, not ``0`` - the rule of this module applied per bucket, so the
    dashboard of #1391 shows a gap where nothing was measured instead of a
    floor at zero. The counts stay numbers: "no failure in this window" is a
    measured statement, "no measured duration" is not.
    """
    executions = stats["executions"] or 0
    wait_samples = stats["wait_samples"] or 0
    row = {key: stats[key] for key in _COUNT_FIELDS}
    row["executions"] = executions
    row["wait_samples"] = wait_samples
    for key in _DURATION_FIELDS:
        if key.startswith("wait_"):
            row[key] = stats[key] if wait_samples else None
        else:
            row[key] = stats[key] if executions else None
    return row


def window_buckets(since, until=None, limit=200, include_uncertain=True,
                   attribution=WINDOW_RUN):
    """Terminal attempts of one window, bucketed per task class and queue.

    The answer #1391 publishes and plots. One grouped, bounded query over the
    windowed attempt index carries every number of a bucket - the occupied
    slot-seconds, the attempts outcome by outcome, and the percentiles of the
    active and waiting durations - plus one whole-window aggregate for the
    fleet row and one grouped read for the uncertain observations. Never a
    query per attempt, never anything on a browser's path: whoever calls this
    on a schedule publishes what it answers, and the dashboard reads what was
    published.

    The semantics are the ones this module always had and the issue insists on
    keeping apart:

    *   occupied seconds come from terminal attempts only, so an attempt which
        waited 4 h in front of a 2 s execution contributes 2 slot-seconds and
        a 4 h *wait* sample - the queue is congested, the task is not slow;
    *   queue waiting is its own columns and never part of the occupancy;
    *   a bucket without terminal attempts answers ``None`` for every duration
        and keeps its counts as the numbers they are;
    *   ``wait_samples`` says how much of a bucket could be seen at all - a
        bucket whose messages carried no publish stamp has an *unknown* wait,
        not a fast one;
    *   ``uncertain_open``/``uncertain_abandoned`` are counts of observations
        nobody measured an end for, never converted into durations.

    ``limit`` bounds how many buckets the answer carries, heaviest first, with
    ``truncated`` naming the cut. The cardinality of the answer is the number
    of (class, queue) pairs of the deployment - which is what keeps a
    high-volume scenario from producing log lines or queries proportional to
    its attempts.

    Args:
        since (datetime): the window's start, mandatory as everywhere here
        until (datetime): the window's end, ``now`` by default
        limit (int): maximum number of buckets in the answer
        include_uncertain (bool): count the uncertain observations per bucket
        attribution (str): which time column owns a row's window, see
            :data:`WINDOW_RUN` and :data:`WINDOW_WRITTEN`
    """
    grouped = (_windowed(since, until, attribution=attribution)
               .annotate(**{TASK_CLASS_FIELD: TaskClass()})
               .values(TASK_CLASS_FIELD, "queue")
               .annotate(**_aggregate_fields())
               .order_by("-slot_seconds"))
    rows = list(grouped[:limit + 1])
    truncated = len(rows) > limit
    buckets = []
    for row in rows[:limit]:
        buckets.append(dict(
            {TASK_CLASS_FIELD: row[TASK_CLASS_FIELD], "queue": row["queue"]},
            **_bucket_row(row)))

    if include_uncertain:
        # per bucket, from the same uncertain question attempt_measures asks;
        # the fleet's own total is the second read below, so a deployment with
        # more (class, queue) pairs than the bound of this grouped read still
        # answers its fleet totals exactly
        uncertain = (_uncertain_open_qs(
            since, until, attribution=attribution)
            .annotate(**{TASK_CLASS_FIELD: TaskClass()})
            .values(TASK_CLASS_FIELD, "queue")
            .annotate(
                open_without_end=Count("pk"),
                abandoned=Count("pk", filter=Q(
                    quality__contains=[AttemptQuality.ABANDONED.value])))
            [:DISTINCT_TASK_NAME_BOUND])
        counts = {(row[TASK_CLASS_FIELD], row["queue"]): row
                  for row in uncertain}
        for bucket in buckets:
            row = counts.get((bucket[TASK_CLASS_FIELD], bucket["queue"]), {})
            bucket["uncertain_open"] = row.get("open_without_end", 0)
            bucket["uncertain_abandoned"] = row.get("abandoned", 0)
        # the fleet's own total is its own read: a deployment with more
        # (class, queue) pairs than the bound above would otherwise understate
        # its own uncertain count, which is a coverage statement
        fleet_counts = _uncertain_open_qs(
            since, until, attribution=attribution).aggregate(
            open_without_end=Count("pk"),
            abandoned=Count("pk", filter=Q(
                quality__contains=[AttemptQuality.ABANDONED.value])))
        fleet_open = fleet_counts["open_without_end"]
        fleet_abandoned = fleet_counts["abandoned"]
    else:
        fleet_open = fleet_abandoned = None

    whole = _windowed(since, until,
                      attribution=attribution).aggregate(
        **_aggregate_fields())
    fleet = _bucket_row(whole)
    executions = fleet["executions"]
    return {
        "source": SOURCE_MEASURED_WORKER,
        "window": {"since": since, "until": until or timezone.now()},
        "grouped_by": [TASK_CLASS_FIELD, "queue"],
        "quantiles": {
            "active_seconds": list(ACTIVE_QUANTILES),
            "wait_seconds": list(WAIT_QUANTILES),
        },
        "buckets": buckets,
        "truncated": truncated,
        "fleet": fleet,
        "uncertain": {"open_without_end": fleet_open,
                      "abandoned": fleet_abandoned},
        "coverage": {
            "terminal_samples": executions,
            "stamped_samples": fleet["wait_samples"],
            # share of terminal attempts whose queue wait was measurable;
            # None says "nothing to compare", which is not the same as 0
            "wait_coverage": ((fleet["wait_samples"] / executions)
                              if executions else None),
        },
    }


def drilldown_samples(since, until=None, task_classes=None, limit=50,
                      attribution=WINDOW_RUN):
    """The newest measured attempts of some classes, for the operator's click.

    The drill-down of #1391: the row of one attempt as #1330 measured it, with
    the correlation keys a reader needs to reach the job or incident behind it
    (``root_id``, ``periodic_name``) - and nothing else, because the value
    list is the module's own and the table has no column for an argument, a
    URL or a payload.

    One bounded query over the window, newest first, filtered to the classes
    asked for; the answer is what a scheduled exporter may publish as a
    *sample* of a class. These rows are never a series: a dashboard must not
    group them over time, which is how the task uuid of #1391's warning stays
    out of every label.

    Args:
        since (datetime): the window's start
        until (datetime): the window's end, ``now`` by default
        task_classes (iterable): the classes to answer for; empty answers empty
        limit (int): maximum number of rows
    """
    classes = list(task_classes or [])
    if not classes:
        return []
    return list(
        _windowed(since, until, attribution=attribution)
        .filter(_terminal_q())
        .annotate(**{TASK_CLASS_FIELD: TaskClass()})
        .filter(**{f"{TASK_CLASS_FIELD}__in": classes})
        .order_by("-started_at")
        .values("task_id", "attempt_no", "task_name", TASK_CLASS_FIELD,
                "queue", "worker", "root_id", "parent_id", "periodic_name",
                "published_at", "started_at", "finished_at", "active_seconds",
                "wait_seconds", "outcome", "quality")
        [:limit])


#: the sweep of system.tasks declares an open attempt abandoned only once it
#: is older than this grace; the standing coverage read uses the same bound to
#: tell "still running" from "the worker is gone"
ABANDON_GRACE_SETTING = "CAPACITY_TELEMETRY_ABANDON_GRACE_HOURS"

#: how far the standing coverage read of :func:`uncertain_coverage` looks
#: back over ``started_at``. A multiple of the grace comfortably outlives both
#: bounds the sweep enforces (retention and the hard row cap), so no residue
#: which is still in the table can hide behind the bound, while the read stays
#: a range scan on the indexed column rather than a scan of the whole table.
UNCERTAIN_COVERAGE_LOOKBACK_GRACES = 8


def _abandon_grace():
    return timedelta(hours=max(1, int(getattr(
        settings, ABANDON_GRACE_SETTING, 48))))


def uncertain_coverage(group_by_class=False, limit=DISTINCT_TASK_NAME_BOUND):
    """The crash residue the attempt table is holding RIGHT NOW.

    The coverage question of #1391 - "can this dashboard see what ran?" - is a
    question about the *state of the table*, not about a window. The windowed
    counters of :func:`window_buckets` cannot answer it: the sweep of
    ``system.tasks`` flags an open attempt abandoned only
    ``CAPACITY_TELEMETRY_ABANDON_GRACE_HOURS`` (~48 h) after it started, while
    an exporter's window is minutes wide and measures by when a row was
    written - by the time the flag exists, the row has long left every window
    it could be counted in. A deployment whose workers died mid-task would
    publish ``0 / 0`` beside a panel presenting itself as exactly that read.

    So this read is not windowed. It asks the standing question and answers
    three numbers which a window query cannot tell apart:

    ``open_running``
        open attempts without a terminal twin which started *within* the grace
        - attempts the fleet may still be running, an expected state;
    ``open_abandoned``
        open attempts without a terminal twin which started *before* the grace
        - the crash residue the sweep has declared (or is about to declare)
        without an end; this is the number a coverage panel must move;
    ``open_total``
        both together, for a reader who wants "everything still open".

    Partitioning at the grace is what makes the two states distinguishable at
    all: a flagged attempt and a merely long-running one have the same row
    shape, and collapsing them would let a healthy long task read as crashed
    workers, or the reverse. The read is bounded on ``started_at`` by a
    multiple of the grace which outlives retention, so it stays an indexed
    range scan on a table whose only growing edge is the recent one.

    Args:
        group_by_class (bool): also answer the residue per task class, so an
            operator can see which class is holding it
        limit (int): bound of that grouped read
    """
    now = timezone.now()
    grace = _abandon_grace()
    grace_moment = now - grace
    lookback = now - grace * UNCERTAIN_COVERAGE_LOOKBACK_GRACES
    # what the sweep of system.tasks declares - and, one sweep later, always
    # will: an open row of the grace's age. Reading the age as well as the
    # flag is what makes this answer independent of when the sweep last ran;
    # a row whose worker is gone is residue from the moment it stops being
    # plausible that it is still running, not from the hour the sweep noticed.
    residue_q = _abandoned_q() | Q(started_at__lt=grace_moment)
    # the same uncertain question as _uncertain_open_qs, over the standing
    # span instead of a window: open rows of the lookback whose identity has
    # no terminal row anywhere (a terminal row is always as old as its open
    # twin, so bounding the search by the open row's own age misses nothing)
    terminal_twin = CeleryTaskAttempt.objects.filter(
        task_id=OuterRef("task_id"),
        attempt_no=OuterRef("attempt_no")).exclude(outcome="")
    standing = (CeleryTaskAttempt.objects
                .filter(started_at__gte=lookback)
                .annotate(has_terminal=Exists(terminal_twin))
                .filter(_open_q() & ~Q(has_terminal=True)))

    def _counts(qs):
        return qs.aggregate(
            open_running=Count("pk", filter=~residue_q),
            open_abandoned=Count("pk", filter=residue_q),
            open_total=Count("pk"))

    fleet = _counts(standing)
    answer = {
        # the fleet's own read, never a sum over the bounded grouped read
        "open_running": fleet["open_running"],
        "open_abandoned": fleet["open_abandoned"],
        "open_total": fleet["open_total"],
        "grace_seconds": int(grace.total_seconds()),
        "source": SOURCE_MEASURED_WORKER,
    }
    if group_by_class:
        grouped = (standing
                   .annotate(**{TASK_CLASS_FIELD: TaskClass()})
                   .values(TASK_CLASS_FIELD)
                   .annotate(
                       open_running=Count("pk", filter=~residue_q),
                       open_abandoned=Count("pk", filter=residue_q),
                       open_total=Count("pk"))
                   .order_by("-open_abandoned", "-open_running")[:limit])
        answer["by_class"] = [
            {TASK_CLASS_FIELD: row[TASK_CLASS_FIELD],
             "open_running": row["open_running"],
             "open_abandoned": row["open_abandoned"],
             "open_total": row["open_total"]} for row in grouped]
    else:
        answer["by_class"] = []
    return answer
