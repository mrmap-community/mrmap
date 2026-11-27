"""The Celery seams of the ``mrmap.*`` metric contract (#1779).

A separate module from :mod:`MrMap.telemetry.metrics` because the two answer
different questions: ``metrics.py`` is *what is recorded*, this module is *when a
Celery signal is allowed to record it*. The rules are the fork rules of ADR-0003
plus the honest-absence rules of #1330 - the same rules the attempt collector of
#1330 already lives by, which is why this module reads the publish stamp of that
collector rather than inventing a second one.

Two things decide whether a signal records anything:

*   **is the mode on** - ``off`` connects nothing at all: the receivers are not
    even attached, so an uninstrumented deployment pays no extra per-task call.
*   **does this process execute tasks** - a prefork parent, a web process or the
    test runner must not report queue waits for work it never ran. The answer is
    celery's own ``worker_process_init``, the same seam #1330 gates on.

The queue-wait stamp comes from the message header #1330 writes
(``mrmap-published-at``). A message from before that feature, from a foreign
producer, or with an unparsable value records *coverage* and no duration; it never
produces a zero wait, because a zero wait is a measurement and there was none.

Every receiver swallows its own error: telemetry must never change the outcome,
the retry or the acknowledgement of the task it observes.
"""

import time
from datetime import UTC, datetime

from celery.signals import (task_failure, task_postrun, task_prerun,
                            task_retry, task_revoked, task_success,
                            worker_process_init, worker_process_shutdown)
from django.conf import settings
from django.utils.dateparse import parse_datetime

from MrMap.telemetry import metrics

#: the publish stamp header of #1330 - one stamp, two consumers, so the metric
#: and the attempt table cannot disagree about the same message
PUBLISH_STAMP_HEADER = "mrmap-published-at"

#: started-but-unfinished observations of this process. A worker which loses its
#: terminal signals holds at most this many; the overflow records coverage only,
#: which is the honest reading of a process that could not keep up.
_open = {}
OPEN_LIMIT = 1000

#: whether this process went through celery's worker process start-up
_worker_process_started = False

#: monotonic moment the diagnostic extras of this process stop being recorded
_diagnostic_expires_at = None


def _setting(name, default):
    return getattr(settings, name, default)


def collection_enabled() -> bool:
    """Whether this process records task metrics at all."""
    if _setting("OTEL_MODE", "off") == "off":
        return False
    if _setting("OTEL_COLLECT_ANY_PROCESS", False):
        return True
    return _worker_process_started


def note_worker_process(**kwargs):
    """Mark this process as one which executes tasks (``worker_process_init``)."""
    global _worker_process_started
    _worker_process_started = True


def _identity(task):
    """The (name, queue, task id, attempt number) of one execution, or ``None``.

    The task id is the correlation key of #1330 and is used here only to match a
    start with its own end inside this process - it never becomes an attribute.
    """
    request = getattr(task, "request", None)
    if request is None:
        return None
    task_id = str(getattr(request, "id", None) or "")[:64]
    if not task_id:
        return None
    name = getattr(task, "name", None) or "unknown"
    delivery = getattr(request, "delivery_info", None) or {}
    queue = delivery.get("routing_key") or ""
    try:
        attempt_no = int(getattr(request, "retries", 0) or 0)
    except (TypeError, ValueError):
        attempt_no = 0
    return name, queue, task_id, attempt_no


def _published_at(request):
    """``(stamp, present)`` of the one header this project stamps.

    Read the way #1330 reads it, and with the same two answers: a message from
    before that feature or from a foreign producer is *absent*, and a header whose
    value cannot be read is *present but invalid*. The difference is what the
    coverage series of :mod:`MrMap.telemetry.metrics` counts, and neither answer
    is ever a guessed timestamp.
    """
    headers = getattr(request, "headers", None)
    if not isinstance(headers, dict):
        return None, False
    raw = headers.get(PUBLISH_STAMP_HEADER)
    if raw is None:
        return None, False
    try:
        return datetime.fromtimestamp(float(raw), tz=UTC), True
    except (TypeError, ValueError, OverflowError, OSError):
        pass
    try:
        parsed = parse_datetime(str(raw))
    except (TypeError, ValueError):
        return None, True
    if parsed is None:
        return None, True
    return (parsed.replace(tzinfo=UTC) if parsed.tzinfo is None
            else parsed), True


def begin_attempt(sender=None, task_id=None, task=None, **kwargs):
    """Record that an attempt started in this process (``task_prerun``)."""
    if not collection_enabled():
        return
    try:
        identity = _identity(task)
        if identity is None:
            return
        request = getattr(task, "request", None)
        published_at, stamped = _published_at(request)
        _open[identity[2:]] = (time.monotonic(), published_at, stamped)
        if len(_open) > OPEN_LIMIT:
            overflow = sorted(_open.items(), key=lambda item: item[1][0])
            for (key, _value) in overflow[:len(_open) - OPEN_LIMIT]:
                _open.pop(key, None)
                metrics.record_unmeasured(identity[0], identity[1])
    except Exception:
        return


def _finish(task, outcome):
    identity = _identity(task)
    if identity is None:
        return
    name, queue, task_id, attempt_no = identity
    started = _open.pop((task_id, attempt_no), None)
    if started is None:
        # no measured start for this attempt (a worker restart, a pool which
        # never fired prerun, an evicted observation): its durations stay
        # absent and only its existence is counted
        metrics.record_unmeasured(name, queue)
        return
    mono_start, published_at, stamped = started
    active_seconds = max(0.0, time.monotonic() - mono_start)
    wait_seconds = None
    quality = None
    if published_at is not None:
        # the producer's wall clock and this worker's can be a hair apart; a
        # wait before the publish is not a measurable wait, zero is
        wait_seconds = max(
            0.0, _now().timestamp() - published_at.timestamp())
    elif stamped:
        quality = metrics.QUALITY_INVALID_STAMP
    metrics.record_attempt(name, queue, outcome,
                           active_seconds=active_seconds,
                           wait_seconds=wait_seconds, quality=quality)


def _now():
    from django.utils import timezone
    return timezone.now()


def finish_attempt_on_postrun(sender=None, task_id=None, task=None, **kwargs):
    """Close an attempt no terminal signal claimed (eager execution, odd pools).

    Postrun alone cannot say *why* an attempt ended, so it says only what it
    knows: the attempt ran to the end of its body. A terminal signal which already
    closed the observation left nothing here, so this stays silent.
    """
    if not collection_enabled():
        return
    try:
        identity = _identity(task)
        if identity is None or identity[2:] not in _open:
            return
        _finish(task, metrics.OUTCOME_SUCCESS)
    except Exception:
        return


def finish_attempt_on_success(sender=None, **kwargs):
    if not collection_enabled():
        return
    try:
        _finish(sender, metrics.OUTCOME_SUCCESS)
    except Exception:
        return


def finish_attempt_on_failure(sender=None, **kwargs):
    if not collection_enabled():
        return
    try:
        _finish(sender, metrics.OUTCOME_FAILURE)
    except Exception:
        return


def finish_attempt_on_retry(sender=None, request=None, **kwargs):
    """The attempt which asked for its retry consumed real slot time (#1330)."""
    if not collection_enabled():
        return
    try:
        _finish(sender, metrics.OUTCOME_RETRY)
    except Exception:
        return


def mark_attempt_revoked(sender=None, request=None, **kwargs):
    """Best effort on a revocation, the same reading #1330 gives it.

    Under prefork the revoke arrives in the worker's *main* process while the
    observation lives in a child, so this often finds nothing; the sweep of
    ``system.tasks`` stays the authority for those attempts.
    """
    if not collection_enabled():
        return
    try:
        task_id = request if isinstance(request, str) else getattr(
            request, "id", None)
        if not task_id:
            return
        task_id = str(task_id)[:64]
        name = getattr(sender, "name", None) or "unknown"
        delivery = getattr(getattr(sender, "request", None),
                           "delivery_info", None) or {}
        queue = delivery.get("routing_key") or ""
        for key in [key for key in _open if key[0] == task_id]:
            _open.pop(key, None)
            metrics.record_attempt(name, queue, metrics.OUTCOME_REVOKED)
    except Exception:
        return


def flush_on_process_shutdown(**kwargs):
    """Close what this process still holds, so a restart is not a hole.

    One bounded pass over the open observations: no network, no database. The SDK's
    own one-shot drain of :func:`MrMap.telemetry.lifecycle.shutdown` is what
    ships the batch.
    """
    if not collection_enabled():
        return
    try:
        for key, observation in list(_open.items()):
            mono_start = observation[0]
            _open.pop(key, None)
            metrics.record_attempt(
                "unknown", "", metrics.OUTCOME_UNKNOWN,
                active_seconds=max(0.0, time.monotonic() - mono_start))
    except Exception:
        return


def reset_collector():
    """Empty the process-local state; the seam the unit tests isolate with."""
    global _worker_process_started, _diagnostic_expires_at
    _open.clear()
    _worker_process_started = False
    _diagnostic_expires_at = None


def open_observations():
    """The attempts of this process which have not ended; for the tests."""
    return dict(_open)


def connect():
    """Attach the receivers of one worker process.

    Idempotent, and called only from the lifecycle once the providers exist:
    while the mode is ``off`` this function is never called at all, which is how
    "disabled means no instrumentation" is a property of the call graph and not a
    check inside a hot path.
    """
    worker_process_init.connect(note_worker_process, weak=False)
    worker_process_shutdown.connect(flush_on_process_shutdown, weak=False)
    task_prerun.connect(begin_attempt, weak=False)
    task_postrun.connect(finish_attempt_on_postrun, weak=False)
    task_success.connect(finish_attempt_on_success, weak=False)
    task_failure.connect(finish_attempt_on_failure, weak=False)
    task_retry.connect(finish_attempt_on_retry, weak=False)
    task_revoked.connect(mark_attempt_revoked, weak=False)


def disconnect():
    """Detach every receiver this module attached (the shutdown path)."""
    worker_process_init.disconnect(note_worker_process, weak=False)
    worker_process_shutdown.disconnect(flush_on_process_shutdown, weak=False)
    task_prerun.disconnect(begin_attempt, weak=False)
    task_postrun.disconnect(finish_attempt_on_postrun, weak=False)
    task_success.disconnect(finish_attempt_on_success, weak=False)
    task_failure.disconnect(finish_attempt_on_failure, weak=False)
    task_retry.disconnect(finish_attempt_on_retry, weak=False)
    task_revoked.disconnect(mark_attempt_revoked, weak=False)


def diagnostic_window_open(values) -> bool:
    """Whether the diagnostic extras of this process are still inside their bound.

    A forgotten ``diagnostic`` deployment must not run hot forever: the extras
    (outbound client spans, SQL spans) stop on their own after
    ``MRMAP_OTEL_DEBUG_MAX_MINUTES``, while the standard contract keeps working.
    The answer is process-local and monotonic-clock based, so a wall-clock change
    cannot extend a debug window.
    """
    if not values.get("diagnostic"):
        return False
    global _diagnostic_expires_at
    if _diagnostic_expires_at is None:
        _diagnostic_expires_at = (
            time.monotonic() + float(values.get("debug_max_minutes", 15.0))
            * 60.0)
        return True
    return time.monotonic() < _diagnostic_expires_at
