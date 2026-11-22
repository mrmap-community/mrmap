"""Publishing the series the Celery task dashboard of #1391 reads.

The issue's central constraint is the shape of this module: a browser refresh
must never become a database scan, and a busy deployment must never write one
log line per task attempt. So the numbers of the task dashboard travel the way
the deployment's other observations already travel - over the syslog handler
into the log store the Grafana of the stack already queries - and what travels
is a **bucket per task class and queue per window**, never a task.

One fire of the beat task of ``system.tasks`` reads
:func:`system.capacity_measures.window_buckets` for one window and writes one
structured record per bucket plus one fleet record for the window. The windows
do not overlap: the moment a window ended is cached, and the next fire covers
``(that moment, now]`` - so what a deployment published adds up to what it
measured, and a fire which arrives twice, late, or not at all cannot double
count and cannot leave a hole it does not name. The first fire of a fresh
deployment looks back over ``TASK_PERFORMANCE_EXPORT_FIRST_WINDOW_MINUTES`` and
answers ``resumed_from: first_window``: it counts what the retention still
holds, it does not invent history.

Cardinality is the point of the bucket. A dashboard which grouped raw attempts
by task would make a task uuid a label of a time series - the thing #1391 rules
out - so the series are keyed by task **class** (:func:`task_class_of`), queue
and outcome. The drill-down records carry ``task_id`` and ``root_id`` as *log
content* an operator reads, never as a grouping key, and the safe correlation
into the existing job and incident views is by ``periodic_name`` and
``root_id`` - the keys #1330 already carries. No record carries an argument, a
URL, a header or a payload, because the value list of
:func:`system.capacity_measures.drilldown_samples` does not read any: the
attempt table has no column which could hold one (#1330's privacy boundary,
inherited here for free).

What a record says and what it does not: an unmeasured duration stays absent
from the record rather than becoming a zero, occupied seconds never contain
queue waiting, and the coverage counts say how much of the window could be seen
at all. A panel which plots these records therefore shows a gap where nothing
was published - not a flat line at zero, which would tell the same lie about a
quiet deployment and about a broken exporter.

Failure rule: this is telemetry, of the family of #1330's collector and #1320's
publishers. A window whose read or write fails costs the dashboard that window
and names it in the summary; it never raises into the caller, and the only
state it writes is one cache key.

Dashboard, panels and the operator runbook:
``docs/source/development/celery-task-performance.rst``.
"""

from datetime import timedelta
from logging import Logger

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

from system.capacity_measures import drilldown_samples, window_buckets

logger: Logger = settings.ROOT_LOGGER

#: the structured-data id of every record of this exporter. The dashboard
#: selects on it, so it is the contract between the two and stated exactly
#: once; it is not the request dashboard's id, so the two dashboards cannot
#: read each other's lines
TELEMETRY_SDID = "metaSDID@taskperf"

#: the record types: one fleet total per window, one bucket per (class, queue),
#: and the drill-down samples of the heaviest classes of the window
EVENT_FLEET = "fleet"
EVENT_CLASS_BUCKET = "class_bucket"
EVENT_SAMPLE = "class_sample"

#: the cache key holding the end of the last published window. A cache read on
#: purpose: an exporter that needs a table row to know where it stopped is a
#: second data store, and a lost key costs one short window which the summary
#: names, not a wrong number
WINDOW_CURSOR_KEY = "mrmap-task-performance-window-cursor"

#: how far the very first window of a deployment looks back, when there is no
#: cursor to continue from
FIRST_WINDOW_MINUTES = 60


def _setting(name, default):
    return getattr(settings, name, default)


def export_enabled():
    """Whether the deployment publishes its task-performance series at all.

    Read per fire like every other mode of this epic, so a running worker
    picks a change up without a rebuild. Off by default: the series exists for
    a deployment which runs the Grafana of the stack, and an operator who
    never installed the dashboard should not pay records nobody reads. The
    measurement itself (#1330) is unaffected - this only publishes it.
    """
    return bool(_setting("TASK_PERFORMANCE_EXPORT_ENABLED", False))


def _max_buckets():
    return max(1, int(_setting("TASK_PERFORMANCE_EXPORT_MAX_BUCKETS", 200)))


def _samples_per_class():
    return max(0, int(_setting(
        "TASK_PERFORMANCE_EXPORT_SAMPLES_PER_CLASS", 5)))


def _drilldown_classes():
    return max(0, int(_setting(
        "TASK_PERFORMANCE_EXPORT_DRILLDOWN_CLASSES", 3)))


def _seconds(value):
    """A duration as the number a log store can aggregate, or None.

    ``None`` stays out of the record entirely: "not measured" and "measured
    zero" are different statements and the dashboard has to keep telling them
    apart (#1391: show no data as unavailable, not zero).
    """
    if value is None:
        return None
    return round(float(value), 3)


def _moment(value):
    return value.isoformat() if value is not None else None


def _sd_value(value):
    """One record value as RFC 5424 structured data carries it: a string.

    The formatter quotes whatever it is handed, so a number which was not
    stringified here arrives in the log store as a string anyway - naming the
    boundary once keeps the values of a published record honest about their
    wire type, while the summary the beat task of ``system.tasks`` adds up and
    logs stays numbers.
    """
    return str(value)


def _window_fields(window):
    """The window's own fields, identical on every record of one fire.

    A dashboard plots ``window_end`` as the point of a bucket and
    ``window_seconds`` as its width, so the buckets of one fire are one
    non-overlapping interval and the sum of a series over a range is the sum
    of the attempts of that range - which is what lets an operator check a
    panel's total against a ``capacity_measures`` query of the same window.
    """
    return {
        "window_start": _moment(window["since"]),
        "window_end": _moment(window["until"]),
        "window_seconds": _seconds(
            (window["until"] - window["since"]).total_seconds()),
    }


def _fleet_record(answer):
    """The one record per window that says what the window held in total."""
    fleet = answer["fleet"]
    coverage = answer["coverage"]
    uncertain = answer["uncertain"]
    record = {
        "event": EVENT_FLEET,
        "executions": fleet["executions"],
        "slot_seconds": _seconds(fleet["slot_seconds"]),
        "succeeded": fleet["succeeded"],
        "failed": fleet["failed"],
        "retried": fleet["retried"],
        "revoked": fleet["revoked"],
        "uncertain_open": uncertain["open_without_end"],
        "uncertain_abandoned": uncertain["abandoned"],
        "active_p50": _seconds(fleet["active_p50"]),
        "active_p95": _seconds(fleet["active_p95"]),
        "active_p99": _seconds(fleet["active_p99"]),
        "active_max": _seconds(fleet["active_max"]),
        "wait_p50": _seconds(fleet["wait_p50"]),
        "wait_p95": _seconds(fleet["wait_p95"]),
        "wait_max": _seconds(fleet["wait_max"]),
        "wait_samples": fleet["wait_samples"],
        "wait_coverage": (None if coverage["wait_coverage"] is None
                          else round(coverage["wait_coverage"], 4)),
        "buckets": len(answer["buckets"]),
        "truncated": answer["truncated"],
        "source": answer["source"],
    }
    record.update(_window_fields(answer["window"]))
    return record


def _bucket_records(answer):
    """One record per (class, queue) bucket of the window, heaviest first."""
    window = _window_fields(answer["window"])
    records = []
    for bucket in answer["buckets"]:
        record = {
            "event": EVENT_CLASS_BUCKET,
            "task_class": bucket["task_class"],
            "queue": bucket["queue"],
            "executions": bucket["executions"],
            "slot_seconds": _seconds(bucket["slot_seconds"]),
            "succeeded": bucket["succeeded"],
            "failed": bucket["failed"],
            "retried": bucket["retried"],
            "revoked": bucket["revoked"],
            "uncertain_open": bucket["uncertain_open"],
            "uncertain_abandoned": bucket["uncertain_abandoned"],
            "active_p50": _seconds(bucket["active_p50"]),
            "active_p95": _seconds(bucket["active_p95"]),
            "active_p99": _seconds(bucket["active_p99"]),
            "active_max": _seconds(bucket["active_max"]),
            "wait_p50": _seconds(bucket["wait_p50"]),
            "wait_p95": _seconds(bucket["wait_p95"]),
            "wait_max": _seconds(bucket["wait_max"]),
            "wait_samples": bucket["wait_samples"],
            "source": answer["source"],
        }
        record.update(window)
        records.append(record)
    return records


def _sample_records(answer, classes):
    """The newest measured attempts of the heaviest classes of the window.

    The drill-down #1391 asks for, within the boundaries it asks for: rows an
    operator reads, not a series. The safe correlation keys ride along
    (``periodic_name`` names the periodic setting behind a dispatch,
    ``root_id`` the workflow it belongs to, which is how a background job or
    an incident of #1104 becomes reachable from a slow class); credentials and
    remote URLs are not columns of the attempt table and are not read here.
    """
    samples = drilldown_samples(
        answer["window"]["since"], answer["window"]["until"],
        task_classes=classes,
        limit=_samples_per_class() * max(1, len(classes)))
    window = _window_fields(answer["window"])
    per_class = {}
    records = []
    for row in samples:
        task_class = row["task_class"]
        if per_class.get(task_class, 0) >= _samples_per_class():
            continue
        per_class[task_class] = per_class.get(task_class, 0) + 1
        record = {
            "event": EVENT_SAMPLE,
            "task_class": task_class,
            "task_name": row["task_name"],
            "queue": row["queue"],
            "worker": row["worker"] or None,
            "periodic_name": row["periodic_name"] or None,
            "root_id": row["root_id"] or None,
            "task_id": row["task_id"],
            "attempt_no": row["attempt_no"],
            "outcome": row["outcome"] or None,
            "active_seconds": _seconds(row["active_seconds"]),
            "wait_seconds": _seconds(row["wait_seconds"]),
            "started_at": _moment(row["started_at"]),
            "finished_at": _moment(row["finished_at"]),
            "source": answer["source"],
        }
        record.update(window)
        records.append(record)
    return records


def _log(record):
    """One structured record, written the way this deployment logs everything.

    ``disable_python_meta`` keeps the formatter from adding a code position
    nobody reads and ``suppress_dump`` keeps it from writing the json dump it
    would otherwise leave below the media root for a record with structured
    data: the numbers *are* the record, so the syslog line carries them and
    nothing is duplicated on disk (see system/logging/formatter.py, #1033).
    The values are strings by the time they arrive here, which is what
    RFC 5424 structured data carries.
    """
    logger.info("Celery task performance %s" % record["event"], extra={
        "disable_python_meta": True,
        "suppress_dump": True,
        "structured_data": {
            TELEMETRY_SDID: {
                key: _sd_value(value) for key, value in record.items()
                if value is not None},
        },
    })


def _next_window(now):
    """The window this fire covers: ``(last published end, now]``.

    Answers ``(since, resumed_from)``. Without a cursor the window looks back
    over the configured first-window span, which describes a real window of a
    new deployment instead of whatever the retention happens to still hold.
    """
    cursor = cache.get(WINDOW_CURSOR_KEY)
    if isinstance(cursor, str):
        try:
            return timezone.datetime.fromisoformat(cursor), "cursor"
        except ValueError:
            # a cursor which cannot be read is no cursor; saying so beats
            # guessing where the last window ended
            logger.warning("task performance export (#1391): the window "
                           "cursor %r could not be read; starting a new "
                           "window", cursor)
    return (now - timedelta(minutes=int(_setting(
        "TASK_PERFORMANCE_EXPORT_FIRST_WINDOW_MINUTES",
        FIRST_WINDOW_MINUTES))), "first_window")


def export_task_performance():
    """Publish one window of the task-performance series; report what happened.

    The cost of one fire is fixed and small: two bounded grouped reads and one
    bounded aggregate over the windowed attempt index, one bounded sample read,
    and at most ``1 + buckets + samples`` log records. Never a query per
    attempt, never a record per attempt, and nothing at all on a browser's
    path - the acceptance criterion of #1391 that a high-volume scenario must
    not produce logs or queries proportional to dashboard refreshes times task
    attempts.

    Returns the summary the beat task logs: ``published`` with the record
    count and the window it covers, or a ``reason`` for the window that was not
    published.
    """
    if not export_enabled():
        return {"published": 0, "reason": "task performance export is off"}

    now = timezone.now()
    since, resumed_from = _next_window(now)
    if now <= since:
        # no window elapsed since the last fire; there is nothing to cover
        # and nothing to say about the window it would have had
        return {"published": 0, "reason": "no window elapsed since the last",
                "window_start": _moment(since), "window_end": _moment(now)}

    try:
        answer = window_buckets(since=since, until=now, limit=_max_buckets())
    except Exception as error:  # a broken read costs a window, never a task
        logger.warning("task performance export (#1391): the window of %s "
                       "could not be measured: %s", _moment(since), error)
        cache.set(WINDOW_CURSOR_KEY, now.isoformat())
        return {"published": 0, "reason": str(error),
                "window_start": _moment(since), "window_end": _moment(now)}

    classes = [bucket["task_class"] for bucket
               in answer["buckets"][:_drilldown_classes()]]
    records = [_fleet_record(answer)]
    records += _bucket_records(answer)
    if classes and _samples_per_class():
        try:
            records += _sample_records(answer, classes)
        except Exception as error:
            # the series is the product; the drill-down is a convenience on
            # top of it and never costs a window its buckets
            logger.warning("task performance export (#1391): the drill-down "
                           "of %s could not be read: %s", classes, error)

    published = 0
    for record in records:
        try:
            _log(record)
            published += 1
        except Exception as error:  # a log store which is down costs records
            logger.warning("task performance export (#1391): %s of %s records "
                           "of the window %s could not be written: %s",
                           published, len(records), _moment(now), error)
            break

    cache.set(WINDOW_CURSOR_KEY, now.isoformat())
    summary = {
        "published": published,
        "window_start": _moment(since),
        "window_end": _moment(now),
        "executions": answer["fleet"]["executions"],
        "slot_seconds": _seconds(answer["fleet"]["slot_seconds"]),
        "buckets": len(answer["buckets"]),
        "truncated": answer["truncated"],
        "drilldown_classes": classes,
        "resumed_from": resumed_from,
    }
    if answer["truncated"]:
        summary["note"] = (
            "the window held more than %s (class, queue) buckets; the "
            "heaviest were published, so the series is partial for this "
            "window and says so" % _max_buckets())
    return summary
