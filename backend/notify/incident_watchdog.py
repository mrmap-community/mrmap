"""The independent, bounded watchdog for stalled operational work (#1320).

A task which stands cannot be trusted to report about standing: the failure
class of #1038 is exactly a chord whose retry budget died inside celery's
own unlock, leaving the ``BackgroundProcess`` reporting progress forever
while nothing worked anymore. This module asks, on its own beat schedule
and out of the durable state which exists anyway, which open operations are
waiting for work which demonstrably nobody is doing - and publishes a
watchdog verdict (#1320) through the one reporting seam of
``notify.incident_reporting``.

What it checks, and what it never does:

*   It reports incidents. It never touches a ``BackgroundProcess``, a
    harvesting job or any other source state - the authoritative recovery
    of a stranded harvest stays where #1038/#891 put it, and "stalled
    suspected" is a diagnosis, not a status.
*   Every verdict names its evidence: a retry window which expired beyond
    the grace and for which the broker answers no trace of the operation's
    work (the same ``active/reserved/scheduled`` inspection the abort of
    #1179 and the import watchdog of #1038 use), or a declared queue which
    no answering worker consumes while processes are open. Elapsed runtime
    alone is never evidence - slow work which moves, and work whose retry
    attempt did appear, answer nothing.
*   A broker which answers nothing answers "unknown" for the whole fire:
    the watchdog goes quiet instead of guessing, and its next fire is the
    retry of the question.
*   Its verdicts resolve themselves: the sweep at the start of every fire
    closes the standing verdicts whose evidence has moved on - the process
    was reported with, rescheduled or decided - and the queue incidents
    whose queue is consumed again. The completion of a process resolves
    the verdicts of its resource through the terminal resolver of
    #1320's reporting module.

The scan is bounded in every dimension: one windowed query per check,
sliced by a maximum, one broker inspection for the whole fire, and the
standing-verdict sweep iterates over the small set of the watchdog's own
active incidents - no unbounded polling of the broker or the database.
"""
from datetime import timedelta
from logging import Logger

from django.conf import settings
from django.utils.timezone import now

from MrMap import celery_queues
from MrMap.celery import app
from notify.enums import IncidentSeverityEnum, ProcessStatusEnum
from notify.incident_reporting import (WATCHDOG_CODE_PREFIX,
                                       publish_watchdog_verdict,
                                       source_and_resource, system_verdict)
from notify.models import BackgroundProcess

logger: Logger = settings.ROOT_LOGGER

#: the code of the verdict "this operation waits for a retry attempt which
#: never appeared"; shared verbatim with the recovery sweep below and
#: prefixed by the watchdog family of #1320's reporting module
RETRY_WINDOW_CODE = f"{WATCHDOG_CODE_PREFIX}retry_window_expired"
#: the prefix of the verdict "no worker consumes this declared queue"; the
#: queue name closes the code, so one code names one queue and the dedup
#: key of #1319 keeps one standing incident per queue
CONSUMER_CODE_PREFIX = f"{WATCHDOG_CODE_PREFIX}consumer_missing_"


def _minutes(name, default):
    return timedelta(
        minutes=max(1, int(getattr(settings, name, default))))


def _hours(name, default):
    return timedelta(
        hours=max(1, int(getattr(settings, name, default))))


def retry_grace():
    """How long past its deadline a retry window may stand unexplained.

    The grace must outlast the watchdog's own fire interval by a margin,
    or a fire could judge a window which the next fire has not even seen
    scheduled yet; the settings keep both open for a deployment which
    re-schedules either side.
    """
    return _minutes("OPERATIONAL_WATCH_RETRY_GRACE_MINUTES", 15)


def retry_lookback():
    """How far back the scan looks for expired retry windows.

    A window older than this is a process the watchdog has reported about
    already (its verdict stands and the sweep of every fire re-checks it)
    or one decided through its own paths; re-reporting the ancient past
    every five minutes is the unbounded polling this watchdog must not
    become (#1320).
    """
    return _hours("OPERATIONAL_WATCH_RETRY_LOOKBACK_HOURS", 24)


def max_verdicts_per_fire():
    """The ceiling of verdicts one fire may publish (#1320's limit).

    A whole deployment which loses its workers is a bounded number of
    incidents, not one per process: the dedup key of #1319 already keeps
    the standing ones from multiplying, and the ceiling keeps one fire of
    a mass event from writing thousands of distinct resource incidents.
    """
    return max(1, int(getattr(settings, "OPERATIONAL_WATCH_MAX_VERDICTS", 25)))


def declared_queues():
    """The queue names mrmap declares, from the single module of #1040."""
    return {
        value for name, value in vars(celery_queues).items()
        if name.isupper() and isinstance(value, str)}


def _inspection(at):
    """One broker inspection for the whole fire, or None.

    None answers "the broker is dark": no inspected call reached a worker
    at all, which is the case of a network problem, not of stalled work -
    the watchdog must not turn its own outage into everybody else's
    incident. A partial answer is kept per key; only the keys which
    answered are used below.
    """
    control = app.control.inspect()
    answers = {}
    for name in ("active", "reserved", "scheduled", "active_queues"):
        answers[name] = getattr(control, name)()
    if all(answer is None for answer in answers.values()):
        return None
    return answers


def _pks_with_visible_work(answers):
    """The process ids whose work an inspected worker is doing.

    The same matching the abort of #1179 performs: a worker reports the
    kwargs it received from the broker, which carry the process as a
    string. A process in this set has live work - or its retry attempt
    just appeared - and no verdict of this fire may name it.
    """
    pks = set()
    for key in ("active", "reserved", "scheduled"):
        for workers in (answers.get(key) or {}).values():
            for task in workers or []:
                pk = (task.get("kwargs") or {}).get(
                    "background_process_pk")
                if pk is not None:
                    pks.add(str(pk))
    return pks


def consumed_queues(answers):
    """The queue names the answering workers declare to consume.

    None answers "no worker declared anything", which is unknown, not
    empty: the difference between a broker which answered "no workers"
    and one which did not answer is the difference between evidence and
    guessing.
    """
    views = answers.get("active_queues")
    if views is None:
        return None
    consumed = set()
    for queues in views.values():
        for queue in queues or []:
            name = queue.get("name") if isinstance(queue, dict) else \
                getattr(queue, "name", None)
            if name:
                consumed.add(name)
    return consumed


def _retry_window_iso(process):
    return process.retry_scheduled_until.isoformat() \
        if process.retry_scheduled_until is not None else None


def resolve_stale_verdicts(answers, at=None):
    """Close the standing watchdog verdicts whose evidence has moved on.

    A retry-window verdict stands as long as its exact evidence stands:
    the same expired window on the same open process. The moment the
    process reports again (which closes the window - #1207), schedules a
    new attempt (which moved the window), or decides about itself, the
    suspicion was answered and the incident resolves. A verdict whose
    process row cannot be read anymore resolves too - the cascade of
    #1319 would have taken the incident anyway when the resource went.

    Consumer verdicts resolve when the queue is consumed again, which
    only an answering ``active_queues`` can prove.

    Returns:
        int: how many incidents this sweep resolved
    """
    from notify.enums import IncidentStatusEnum
    from notify.models import OperationalIncident

    at = at or now()
    resolved = 0

    for incident in OperationalIncident.objects.filter(
            code=RETRY_WINDOW_CODE,
            status=IncidentStatusEnum.ACTIVE.value).iterator():
        process_pk = (incident.details or {}).get("background_process")
        process = BackgroundProcess.objects.filter(
            pk=process_pk).first() if process_pk else None
        stale_window = (incident.details or {}).get(
            "retry_window_expires_at")
        if process is None \
                or process.done_at is not None \
                or process.retry_scheduled_until is None \
                or _retry_window_iso(process) != stale_window:
            resolved += OperationalIncident.objects.resolve(
                incident.dedup_key, at=at)

    consumed = consumed_queues(answers)
    if consumed is not None:
        for incident in OperationalIncident.objects.filter(
                code__startswith=CONSUMER_CODE_PREFIX,
                status=IncidentStatusEnum.ACTIVE.value).iterator():
            queue = incident.code[len(CONSUMER_CODE_PREFIX):]
            if queue in consumed:
                resolved += OperationalIncident.objects.resolve(
                    incident.dedup_key, at=at)
    return resolved


def watch_retry_windows(answers, visible, at, verdicts):
    """Verdicts for operations waiting for a retry which never comes.

    The evidence, all of it broker- and row-side: the process reports a
    retry window which expired beyond the grace, nothing of the process
    is visible in any inspected worker's active, reserved or scheduled
    work, and the process itself still stands open. That is the #1038
    shape - the retry scheduled inside the chord unlock, and the unlock
    which gave up without a trace mrmap could read. A worker which is
    merely slow keeps its tasks visible; a process whose work legitimately
    runs without a retry window is never scanned at all.
    """
    if any(answers.get(key) is None
           for key in ("active", "reserved", "scheduled")):
        # without all three views the "no trace" answer would be a guess
        return
    grace = retry_grace()
    window_start = at - retry_lookback()
    stale = BackgroundProcess.objects.select_related(
        "related_resource_type"
    ).filter(
        done_at__isnull=True,
        status__in=[ProcessStatusEnum.PENDING.value,
                    ProcessStatusEnum.RUNNING.value],
        retry_scheduled_until__isnull=False,
        retry_scheduled_until__lt=at - grace,
        retry_scheduled_until__gt=window_start,
    ).order_by("retry_scheduled_until")[:max_verdicts_per_fire()]

    for process in stale:
        if str(process.pk) in visible:
            continue
        # a verdict without a typed resource would share one system key
        # with every other resource-less process and merge their stories;
        # the consumer verdict is the one verdict meant to be about the
        # deployment itself
        source, resource = source_and_resource(process)
        if source is None or not resource:
            continue
        window_iso = _retry_window_iso(process)
        summary = (
            f"The {process.process_type} operation waits for a retry "
            f"attempt which did not appear on the broker; its retry "
            f"window closed at {window_iso} and no inspected worker "
            f"reports work of it.")
        incident, created = publish_watchdog_verdict(
            RETRY_WINDOW_CODE,
            process,
            IncidentSeverityEnum.WARNING.value,
            summary,
            {
                "background_process": str(process.pk),
                "retry_window_expires_at": window_iso,
                "revision": process.revision,
                "grace_minutes": int(grace.total_seconds() // 60),
            })
        if incident is not None:
            verdicts.append(f"{incident.dedup_key} ({'new' if created else 'standing'})")


def watch_missing_consumers(answers, verdicts):
    """Verdicts for declared queues which no worker consumes.

    A queue of #1040's declarations which no answering worker declares,
    while operations stand open, is the starvation of #970 before it
    turns into a stuck deployment. The verdict names no resource - a
    missing consumer is the deployment's own problem - and by the one
    rule of #1319 only administrators will ever read it, which is where
    the epic wants the queue-without-consumer evidence.
    """
    consumed = consumed_queues(answers)
    if consumed is None:
        return
    unwatched = declared_queues() - consumed
    if not unwatched:
        return
    if not BackgroundProcess.objects.filter(
            done_at__isnull=True).exists():
        # without any open operation the absence is not observable as
        # starvation from here - the startup check of MrMap.celery names
        # it in the logs already (#970)
        return
    for queue in sorted(unwatched):
        summary = (
            f"No worker consumes the celery queue '{queue}'; work "
            f"published to it waits without a consumer.")
        incident, created = system_verdict(
            f"{CONSUMER_CODE_PREFIX}{queue}",
            IncidentSeverityEnum.ERROR.value,
            summary,
            {"queue": queue,
             "consumed_queues": sorted(consumed)})
        if incident is not None:
            verdicts.append(
                f"{incident.dedup_key} ({'new' if created else 'standing'})")


def watch_operational_work(at=None):
    """One bounded fire of the watchdog; the entry of the beat task.

    Returns:
        list: a readable line per published verdict, for the log and the
            tests; an empty list when the broker is dark or everything is
            in order.
    """
    at = at or now()
    answers = _inspection(at)
    if answers is None:
        logger.warning(
            "the operational watchdog reached no worker; this fire "
            "publishes nothing (#1320)")
        return []

    resolved = resolve_stale_verdicts(answers, at=at)
    verdicts = []
    visible = _pks_with_visible_work(answers)
    watch_retry_windows(answers, visible, at, verdicts)
    watch_missing_consumers(answers, verdicts)
    if resolved or verdicts:
        logger.info(
            "the operational watchdog resolved %s verdicts and published "
            "%s (#1320)", resolved, len(verdicts))
    return verdicts
