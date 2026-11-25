"""Periodic housekeeping of what a running MrMap accumulates on its own.

The per request json dumps which the rfc5424 formatter leaves below the media root
are the only artifact of a deployment that nothing ever took back: every record the
syslog handler formatted added one, so a demo which ran for a few weeks at the
default threshold held 333,193 files and 1.3 GB under ``<MEDIA_ROOT>/logs`` (#888).
Beat sweeps them with the task below; the schedule is created on migrate, see
``system/apps.py``.
"""

from datetime import datetime, timedelta, timezone
from logging import Logger
from pathlib import Path

from celery import shared_task
from django.conf import settings

from extras.tasks import SingletonTask
from MrMap import celery_queues
from system.logging.formatter import SLOW_REQUEST_DUMP_SUBDIR

logger: Logger = settings.ROOT_LOGGER


def slow_request_dumps_dir():
    """The directory the dumps of the rfc5424 formatter are written to.

    Read from ``MEDIA_ROOT`` on every call, like the formatter which writes them,
    so a deployment which moves its media root moves the sweep with it.
    """
    return Path(settings.MEDIA_ROOT) / SLOW_REQUEST_DUMP_SUBDIR


def _dumps_by_age(directory):
    """The dumps of ``directory`` with their modification time, oldest first.

    Only the ``.json`` files of that very directory and nothing below it: the media
    root keeps the request and response bodies of the security proxy in a subtree of
    its own and those belong to the rows of ``HttpRequestLog``, which are deleted
    with their records and not by age.
    """
    dumps = []
    for entry in directory.glob("*.json"):
        if not entry.is_file():
            continue
        try:
            modified = datetime.fromtimestamp(
                entry.stat().st_mtime, tz=timezone.utc)
        except OSError:
            continue  # taken away between the listing and the stat
        dumps.append((modified, entry))
    dumps.sort(key=lambda dump: dump[0])
    return dumps


def delete_dumps(directory, retention_days, max_files):
    """Takes back the dumps of ``directory`` which are of no use anymore.

    A dump goes when it was written before ``retention_days`` days, or when more
    than ``max_files`` of them are left and it is one of the oldest; a bound of 0
    answers that bound disabled. The count bounds the directory itself, which a
    chatty deployment pays for on every listing, while the age bound is the one
    which aligns with the retention of the log store.

    Returns what was done, which is what the log line and the beat result say.
    """
    dumps = _dumps_by_age(directory)

    expired = []
    if retention_days > 0:
        allowed_since = datetime.now(timezone.utc) - timedelta(
            days=retention_days)
        expired = [entry for modified,
                   entry in dumps if modified < allowed_since]
        # what the age bound took away is gone, so it is not left to the cap
        dumps = [(modified, entry) for modified,
                 entry in dumps if modified >= allowed_since]

    excess = []
    if max_files > 0 and len(dumps) > max_files:
        excess = [entry for _, entry in dumps[:len(dumps) - max_files]]

    for entry in expired + excess:
        entry.unlink(missing_ok=True)

    return {
        "directory": str(directory),
        "retention_days": retention_days,
        "max_files": max_files,
        "expired": len(expired),
        "excess": len(excess),
        "remaining": len(dumps) - len(excess),
    }


@shared_task(queue=celery_queues.DB_ROUTINES, bind=True, base=SingletonTask)
def delete_old_slow_request_dumps(self, *args, **kwargs):
    """Sweeps the slow request dumps out of the media root (#888).

    Runs as a singleton on the ``db-routines`` queue, because two sweeps over the
    same directory have nothing to add to each other, and beat hands it over
    hourly. A dump which is gone only costs the per request sql detail: the syslog
    line which pointed at it stays in the log store for its own retention. Since
    #970 ``db-routines`` carries no floodable backlog anymore - a harvest's import
    backlog fills ``harvest-import`` instead - so this sweep is also reached
    while a catalogue imports.
    """
    summary = delete_dumps(
        slow_request_dumps_dir(),
        retention_days=settings.SLOW_REQUEST_DUMP_RETENTION_DAYS,
        max_files=settings.SLOW_REQUEST_DUMP_MAX_FILES)
    logger.info(
        "Slow request dumps of %s: %s expired and %s exceeding the cap deleted, "
        "%s left (retention %s days, cap %s).",
        summary["directory"], summary["expired"], summary["excess"],
        summary["remaining"], summary["retention_days"], summary["max_files"])
    return summary


@shared_task(queue=celery_queues.DB_ROUTINES, bind=True, base=SingletonTask)
def bound_task_attempt_samples(self, *args, **kwargs):
    """Keeps the attempt samples of #1330 honest and bounded.

    Three sweeps over the ``CeleryTaskAttempt`` rows, in the order they must
    happen:

    *   attempts which never reported an end within
        ``CAPACITY_TELEMETRY_ABANDON_GRACE_HOURS`` get the ``abandoned``
        quality flag - the lost worker or hard-killed process becomes an
        explicitly uncertain observation instead of an open row nobody talks
        about. The flag never fabricates a duration; the aggregation already
        ignores open rows for the occupied seconds. A task which runs past
        the grace but does finish writes its terminal row beside it, and a
        finished attempt with a flagged open twin is no longer counted as
        uncertain - the flag only marks what stayed without an end.
    *   rows recorded before ``CAPACITY_TELEMETRY_RETENTION_DAYS`` go; they
        have told what they had to tell to the snapshot window of #1326.
    *   ``CAPACITY_TELEMETRY_MAX_ATTEMPTS`` bounds the table for a deployment
        whose retention choice outran its disk: the oldest rows go first.

    Runs on ``db-routines`` as a singleton, hourly on a beat row created at
    migrate (``system/apps.py``).
    """
    from django.utils import timezone

    from system.models import AttemptQuality, CeleryTaskAttempt

    summary = {"flagged": 0, "expired": 0, "over_cap": 0, "remaining": 0}
    now = timezone.now()

    # 1. declare the crash residue uncertain, in bounded pages: the page
    #    bound is also the statement bound of a single sweep
    page_size = 500
    grace_hours = max(1, int(getattr(
        settings, "CAPACITY_TELEMETRY_ABANDON_GRACE_HOURS", 48)))
    grace_since = now - timedelta(hours=grace_hours)
    flag = AttemptQuality.ABANDONED.value
    while True:
        stale = list(
            CeleryTaskAttempt.objects
            .filter(outcome="", started_at__lt=grace_since)
            .exclude(quality__contains=[flag])
            .order_by("started_at")[:page_size])
        if not stale:
            break
        for row in stale:
            row.quality = sorted(set(row.quality or []) | {flag})
        CeleryTaskAttempt.objects.bulk_update(stale, ["quality"])
        summary["flagged"] += len(stale)
        if len(stale) < page_size:
            break

    # 2. retention
    retention_days = max(0, int(getattr(
        settings, "CAPACITY_TELEMETRY_RETENTION_DAYS", 14)))
    if retention_days:
        expired, _per_model = CeleryTaskAttempt.objects.filter(
            recorded_at__lt=now - timedelta(days=retention_days)).delete()
        summary["expired"] = expired

    # 3. hard cap: the oldest survivors when the count exceeded the bound
    max_rows = max(0, int(getattr(
        settings, "CAPACITY_TELEMETRY_MAX_ATTEMPTS", 200_000)))
    if max_rows:
        total = CeleryTaskAttempt.objects.count()
        if total > max_rows:
            excess_ids = CeleryTaskAttempt.objects.order_by(
                "recorded_at").values_list("id", flat=True)[:total - max_rows]
            over_cap, _per_model = CeleryTaskAttempt.objects.filter(
                id__in=list(excess_ids)).delete()
            summary["over_cap"] = over_cap
            total -= over_cap
        summary["remaining"] = total

    logger.info(
        "Task attempt samples (#1330): %s open attempts past the grace flagged "
        "abandoned, %s past retention and %s over cap deleted, %s left.",
        summary["flagged"], summary["expired"], summary["over_cap"],
        summary["remaining"])
    return summary


@shared_task(queue=celery_queues.DB_ROUTINES, bind=True, base=SingletonTask)
def refresh_capacity_snapshot(self, *args, **kwargs):
    """Keeps the #1326 capacity snapshot materialized.

    The endpoint is a cache read by design - the walk of every enabled
    schedule belongs here, on beat's cadence, not on an administrator's
    request. ``refresh`` rebuilds only when the cached snapshot went stale
    (its TTL expired or the schedule fingerprint moved) and only while no
    other build holds the lock, so a beat fire that finds the snapshot
    current costs one fingerprint read and answers "unchanged".

    Runs on ``db-routines`` as a singleton, twice an hour on a beat row
    created at migrate (``system/apps.py``); the TTL in ``settings.py`` and
    this cadence are what bound the age of what the endpoint serves.
    """
    from system.capacity_snapshot import refresh

    summary = refresh()
    if summary.get("refreshed"):
        logger.info(
            "Capacity snapshot (#1326): rebuilt for a %s day horizon over "
            "%s schedules, %s dispatches expected, confidence %s, cost "
            "%.2f s.",
            summary["horizon_days"], summary["schedules_walked"],
            summary["occurrences"], summary["confidence"],
            summary["cost_seconds"])
    return summary


@shared_task(queue=celery_queues.DB_ROUTINES, bind=True, base=SingletonTask)
def publish_task_performance(self, *args, **kwargs):
    """Publishes one window of the Celery task-performance series (#1391).

    The dashboard of #1391 reads a log store, and this is what writes it: one
    bounded read of the attempt table per fire, one structured record per
    (task class, queue) bucket of the window plus one fleet total. The windows
    do not overlap - the exporter continues where its last window ended - so
    the published series adds up to what #1330 measured and a fire which is
    late, doubled, or missing cannot invent or double a number.

    Runs on ``db-routines`` as a singleton on a beat row created at migrate
    while ``TASK_PERFORMANCE_EXPORT_ENABLED`` is on (``system/apps.py``); an
    off deployment has neither the row nor the cost. The cadence and the
    bounds of the export are in ``settings.py``; the record shape, the panels
    it feeds and the operator runbook are in
    docs/source/development/celery-task-performance-export.rst.
    """
    from system.task_performance_export import export_task_performance

    summary = export_task_performance()
    if summary.get("window_published"):
        logger.info(
            "Task performance (#1391): published %s records for the window "
            "%s to %s - %s executions, %s occupied slot-seconds over %s "
            "buckets, %s attempts open and %s of them past the grace "
            "(crash residue), resumed from %s.",
            summary["published"], summary["window_start"],
            summary["window_end"], summary["executions"],
            summary["slot_seconds"], summary["buckets"],
            summary.get("open_running", "n/a"),
            summary.get("open_abandoned", "n/a"),
            summary["resumed_from"])
    elif summary.get("coverage_published"):
        # a fire with no window to cover still published the standing read of
        # the table, which is what the coverage panel of the dashboard shows;
        # saying only "nothing published" here would hide the one number an
        # operator of a dead-worker deployment is reading
        logger.info(
            "Task performance (#1391): no window elapsed - published %s "
            "coverage records, %s attempts open and %s of them past the "
            "grace (crash residue).",
            summary["coverage_published"],
            summary.get("open_running", "n/a"),
            summary.get("open_abandoned", "n/a"))
    elif summary.get("reason"):
        logger.info("Task performance (#1391): nothing published - %s.",
                    summary["reason"])
    return summary


@shared_task(queue=celery_queues.DB_ROUTINES, bind=True, base=SingletonTask)
def detect_task_performance(self, *args, **kwargs):
    """Looks for slow, regressing and long-running tasks (#1390).

    The continuous half of epic #1387's V2: not one query per task and never
    on a request path, but one bounded evaluation per fire over the attempt
    samples #1330 already writes - completed slow outliers, p95/slot-cost
    regressions against each class' own previous window, currently active
    executions past their class' budget (only when an answering worker
    confirms them) and the coverage gaps which would otherwise read as
    healthy. Verdicts become the existing incidents of #1319; queue waiting
    is reported as its own labelled condition and stays #1324's capacity
    question.

    Runs on ``db-routines`` as a singleton on a beat interval row created at
    migrate (``system/apps.py``), so a fire still reading the broker costs
    the next one nothing but a skip. ``TASK_PERFORMANCE_ENABLED`` switches
    the work itself off; the row stays, so turning it back on is an
    environment change only.
    """
    from system.task_performance import evaluate_task_performance

    summary = evaluate_task_performance()
    if summary["status"] == "disabled":
        return summary
    logger.info(
        "Task performance (#1390): %s classes over the window %s..%s, %s "
        "conditions, %s verdicts published, %s incidents resolved, worker "
        "inspection %s.",
        summary["classes"], summary["window"]["since"],
        summary["window"]["until"],
        ", ".join(summary["conditions"]) or "none",
        len(summary["published"]), summary["resolved"],
        summary["worker_inspection"])
    return summary
