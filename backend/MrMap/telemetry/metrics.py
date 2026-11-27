"""The ``mrmap.*`` task metrics of a worker process (#1779, ADR-0003).

The Celery instrumentor of the pinned release records
``flower.task.runtime.seconds`` with a raw task name and a worker name as
dimensions, and it records per *execution* rather than per terminal attempt. That
is neither the contract of ADR-0003 nor privacy-safe, so its stream is dropped by a
view (:data:`MrMap.telemetry.policy.DROP_INSTRUMENTS`) and this module answers the
same question with the reviewed dimensions:

``mrmap.task.attempt.duration``
    one terminal attempt, worker occupancy including blocking HTTP;
``mrmap.task.queue.wait``
    published-to-start, only where a trusted publish stamp exists - the same
    stamp #1330 uses, so the two answers cannot disagree;
``mrmap.task.attempts``
    unsampled terminal observations, by outcome;
``mrmap.task.observations``
    the coverage denominator: stamped / unstamped / invalid stamp / dropped.

Two promises decide the design:

*   **independent of trace sampling.** These instruments live on the meter
    provider, not on a span, so a task whose span was never sampled is still
    counted and still in the histogram. The test suite asserts exactly that.
*   **nothing on the task path but a counter add.** No I/O, no database, no
    broker call, no lock around a network. Recording is the SDK's own in-memory
    aggregation, and the only exporter is the bounded periodic reader of
    :mod:`MrMap.telemetry.lifecycle`.

Task names and queue names are mapped through the allowlists before they reach the
instrument: an unknown task is ``other``, not a new time series.
"""

from django.conf import settings

from MrMap.telemetry import naming

#: the outcome values of the contract - the same vocabulary as
#: ``system.models.AttemptOutcome``, so the metric and the attempt table of
#: #1330 describe one attempt the same way
OUTCOME_SUCCESS = "success"
OUTCOME_FAILURE = "failure"
OUTCOME_RETRY = "retry"
OUTCOME_REVOKED = "revoked"
OUTCOME_UNKNOWN = "unknown"
OUTCOMES = (OUTCOME_SUCCESS, OUTCOME_FAILURE, OUTCOME_RETRY, OUTCOME_REVOKED,
            OUTCOME_UNKNOWN)

#: coverage qualities of :data:`OBSERVATIONS`
QUALITY_STAMPED = "stamped"
QUALITY_UNSTAMPED = "unstamped"
QUALITY_INVALID_STAMP = "invalid_stamp"
QUALITY_DROPPED = "dropped"

#: what :func:`count_dropped` can name as the signal which lost something
SIGNAL_TRACES = "traces"
SIGNAL_METRICS = "metrics"
SIGNAL_LOGS = "logs"
DROP_REASONS = ("queue_full", "export_error", "cardinality", "dropped")

#: one attempt observation per (task class, queue, outcome) - the instrument
#: names of ADR-0003's signal contract, which the views of policy.py project
ATTEMPT_DURATION = "mrmap.task.attempt.duration"
QUEUE_WAIT = "mrmap.task.queue.wait"
ATTEMPTS = "mrmap.task.attempts"
OBSERVATIONS = "mrmap.task.observations"
TELEMETRY_DROPPED = "mrmap.telemetry.dropped"

#: instrument name -> (kind, unit, allowed attributes), the single place the
#: names of the contract exist in code
INSTRUMENTS = {
    ATTEMPT_DURATION: ("histogram", "s", ("mrmap.task.class", "mrmap.queue",
                                          "mrmap.task.outcome")),
    QUEUE_WAIT: ("histogram", "s", ("mrmap.task.class", "mrmap.queue")),
    ATTEMPTS: ("counter", "{attempt}", ("mrmap.task.class", "mrmap.queue",
                                        "mrmap.task.outcome")),
    OBSERVATIONS: ("counter", "{observation}", ("mrmap.task.class",
                                                "mrmap.queue",
                                                "mrmap.observation.quality")),
    TELEMETRY_DROPPED: ("counter", "{item}", ("mrmap.signal",
                                              "mrmap.drop.reason")),
}

_meter = None
_instruments = {}


def attach(meter):
    """Create the instruments of one process from its meter.

    Called once by the lifecycle after the provider exists; calling it again with
    a new meter replaces the set, which is what a test isolation seam needs.
    """
    global _meter, _instruments
    _meter = meter
    _instruments = {}
    if meter is None:
        return
    for name, (kind, unit, _allowed) in INSTRUMENTS.items():
        if kind == "histogram":
            _instruments[name] = meter.create_histogram(name=name, unit=unit)
        else:
            _instruments[name] = meter.create_counter(name=name, unit=unit)


def detach():
    """Forget the instruments; used by the test seams and by a shutdown."""
    attach(None)


def _task_class(task_name):
    """The reviewed class of a task name, bounded by the operator's allowlist."""
    return naming.task_class(
        task_name,
        allowed=getattr(settings, "OTEL_TASK_CLASSES", ()),
        budget=getattr(settings, "OTEL_MAX_TASK_CLASSES", 200))


def _queue(queue):
    return naming.queue(queue, budget=getattr(settings, "OTEL_MAX_QUEUES", 16))


def _instrument(name):
    instrument = _instruments.get(name)
    if instrument is None:
        # mode off, or a process which never initialized: the contract says
        # "no telemetry", and an exception here would cost the task itself
        return None
    return instrument


def record_attempt(task_name, queue, outcome, active_seconds=None,
                   wait_seconds=None, quality=None):
    """One terminal attempt: its occupancy, its wait and its count.

    ``active_seconds`` missing means the attempt never got a measured end - the
    duration and the wait are then *absent*, never guessed as zero; the counter
    still records the observation, because an attempt which ended without a
    duration is still one attempt.
    """
    attributes = {"mrmap.task.class": _task_class(task_name),
                  "mrmap.queue": _queue(queue)}
    observed = _instrument(OBSERVATIONS)
    if observed is not None:
        if quality not in (QUALITY_STAMPED, QUALITY_UNSTAMPED,
                           QUALITY_INVALID_STAMP, QUALITY_DROPPED):
            quality = (QUALITY_STAMPED if wait_seconds is not None
                       else QUALITY_UNSTAMPED)
        observed.add(1, dict(attributes, **{
            "mrmap.observation.quality": quality}))
    outcome = outcome if outcome in OUTCOMES else OUTCOME_UNKNOWN
    attempt_attributes = dict(attributes, **{"mrmap.task.outcome": outcome})
    counter = _instrument(ATTEMPTS)
    if counter is not None:
        counter.add(1, attempt_attributes)
    if active_seconds is not None:
        histogram = _instrument(ATTEMPT_DURATION)
        if histogram is not None:
            histogram.record(max(0.0, float(active_seconds)),
                             attempt_attributes)
    if wait_seconds is not None:
        histogram = _instrument(QUEUE_WAIT)
        if histogram is not None:
            histogram.record(max(0.0, float(wait_seconds)), attributes)


def record_unmeasured(task_name, queue, quality=QUALITY_UNSTAMPED):
    """An attempt which will never have a duration: coverage, nothing else.

    The coverage series is what stops an empty histogram from reading as "no
    slow tasks" - the denominator of #1390's coverage verdict, expressed as a
    metric instead of a table scan.
    """
    instrument = _instrument(OBSERVATIONS)
    if instrument is None:
        return
    instrument.add(1, {"mrmap.task.class": _task_class(task_name),
                       "mrmap.queue": _queue(queue),
                       "mrmap.observation.quality": quality})


def record_invalid_stamp(task_name, queue):
    """A message whose publish stamp exists but cannot be read."""
    record_unmeasured(task_name, queue, QUALITY_INVALID_STAMP)


def count_dropped(signal, reason):
    """Telemetry this process could not keep, observable without the store.

    The drop counter is the only number which stays truthful when the collector
    is down: a deployment must be able to see that coverage is *unknown* rather
    than read a silent store as a healthy zero.
    """
    instrument = _instrument(TELEMETRY_DROPPED)
    if instrument is None:
        return
    instrument.add(1, {
        "mrmap.signal": signal if signal in (SIGNAL_TRACES, SIGNAL_METRICS,
                                             SIGNAL_LOGS) else SIGNAL_TRACES,
        "mrmap.drop.reason": reason if reason in DROP_REASONS else "dropped",
    })
