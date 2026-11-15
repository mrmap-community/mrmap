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
"""

from django.db import models
from django.db.models import (Avg, Count, Exists, FloatField, Max, OuterRef,
                              Q, Sum)
from django.utils import timezone

from system.models import (AttemptOutcome, AttemptQuality,
                           CeleryTaskAttempt)


class _WaitPercentile(models.Aggregate):
    """One percentile of the measured queue waits, as one aggregate clause.

    Django dropped postgres' order-set aggregates with 5.0, and re-building
    the whole ``WITHIN GROUP`` machinery for this one number is not worth it:
    the SQL here is the documented form of the question, bound to the two
    columns the collector itself writes. The FILTER keeps the semantics of
    the module: waiting is read from attempts which were *stamped and
    finished* - an unknown wait never joins the distribution as a zero.
    """

    def __init__(self, quantile, **extra):
        self.quantile = float(quantile)
        super().__init__(output_field=FloatField(), **extra)

    def as_sql(self, compiler, connection, **extra_context):
        opts = CeleryTaskAttempt._meta
        table = connection.ops.quote_name(opts.db_table)
        wait = connection.ops.quote_name(
            opts.get_field("wait_seconds").column)
        outcome = connection.ops.quote_name(
            opts.get_field("outcome").column)
        sql = (
            "percentile_cont(%s) WITHIN GROUP (ORDER BY {table}.{wait}) "
            "FILTER (WHERE {table}.{outcome} <> '' "
            "AND {table}.{wait} IS NOT NULL)"
        ).format(table=table, wait=wait, outcome=outcome)
        return sql, [self.quantile]


#: the evidence class of epic #1324 this module answers with; a duration
#: carrying it was measured from worker signals of an actual execution
SOURCE_MEASURED_WORKER = "measured_worker"

#: the grouping dimensions #1326 may ask costs grouped by (issue text:
#: logical periodic setting type, queue, actual task class)
GROUP_DIMENSIONS = ("queue", "task_name", "periodic_name", "outcome")


def _windowed(since, until=None, queue=None, task_name=None,
              periodic_name=None):
    """The base queryset of one bounded window, filters applied.

    ``since`` is mandatory on purpose: a scan over the unbounded table is
    exactly what the snapshot of #1326 may not do on a request path.
    """
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


def _uncertain_open_qs(since, until=None, queue=None, task_name=None,
                       periodic_name=None):
    """Open attempts for which NO terminal row of the same identity exists.

    An attempt that finished normally has its open row from an earlier flush
    sitting beside its terminal row; that pair is a completed execution, not
    an uncertain observation. Only open rows without a terminal counterpart
    are the crash residue #1330 promises to report as partial evidence.
    """
    terminal_twin = CeleryTaskAttempt.objects.filter(
        task_id=OuterRef("task_id"),
        attempt_no=OuterRef("attempt_no")).exclude(outcome="")
    return (_windowed(since, until, queue, task_name, periodic_name)
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
