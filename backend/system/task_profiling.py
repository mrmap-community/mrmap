"""Bounded opt-in root-cause profiling for slow Celery tasks (#1389).

The attempt telemetry of #1330 (``system.capacity_telemetry``) answers *how
long* an attempt occupied a worker; this module answers *why* it took that
long, by splitting the attempt's active time into coarse cost categories:

*   ``sql_seconds`` / ``sql_queries`` - time inside database cursors and the
    number of statements, attributed via the connection's execute wrappers;
*   ``http_seconds`` / ``http_calls`` - time inside an outgoing ``requests``
    send (remote OGC waiting included), attributed via the ``requests``
    signal, never by patching the transport;
*   everything else is *unaccounted* on purpose: the categories are what a
    reader can act on, and the difference to the attempt's active time is
    preserved instead of being smeared over a fake CPU bucket - wall-clock
    categories overlap and nest, so their sum is not the active time and no
    duration is ever invented to close the gap.

The mode is off by default and unsafe-by-construction to leave on broadly:
it profiles only tasks on an explicit allowlist, only a stable sample of
their attempts (derived from the task uuid, so a re-run of the same attempt
id decides identically), and the profile buffer is bounded like #1330's
attempt buffer. The hot path when profiling is *not* selected for an
attempt is one dict lookup.

Privacy is structural: categories hold durations and counts only. URLs,
arguments, headers and payloads are never read off the request, and the
correlation keys are the same task/root/parent ids #1330 already carries.

Part of epic #1387 V2; it reuses the lifecycle clock of #1330 and adds no
second one. The operator runbook - how to enable this safely, what a report
means and a sample - is the development documentation page
``celery-task-root-cause-profiling``. Persistence of profiles,
threshold/budget selection of which attempts to report and EXPLAIN-side
analysis are the following steps of the same issue - this module defines
what they read.
"""

import hashlib
import re
import time
from weakref import WeakSet

from celery.signals import (task_failure, task_postrun, task_prerun,
                            task_retry)
from django.conf import settings
from django.db import connections
from django.db.backends.signals import connection_created
from requests import PreparedRequest
from requests.sessions import Session as RequestsSession

from system.models import AttemptOutcome

logger = settings.ROOT_LOGGER

#: process-local profiles since the last report, keyed by
#: (task_id, attempt_no) exactly like #1330's attempt buffer, so a profile
#: joins its attempt row without a second identity scheme.
_profiles = {}

_stats = {"profiled": 0, "dropped": 0, "duplicate_delivery": 0,
          "partial": 0}


def _setting(name, default):
    return getattr(settings, name, default)


def profiling_enabled():
    """Whether the profiling mode is on at all (kill switch, #1389)."""
    return bool(_setting("TASK_PROFILING_ENABLED", False))


def task_is_profiled(task_name):
    """Whether this task class is on the profiling allowlist."""
    allowlist = _setting("TASK_PROFILING_TASKS", ()) or ()
    return task_name in allowlist


def attempt_is_sampled(task_id):
    """Stable sampling decision for one attempt.

    Derived from the task uuid so it is identical in every process that
    sees the same attempt, without coordinating anything.
    """
    rate = float(_setting("TASK_PROFILING_SAMPLE_RATE", 0.0) or 0.0)
    if rate >= 1.0:
        return True
    if rate <= 0.0:
        return False
    digest = hashlib.sha256(str(task_id).encode("utf-8")).digest()
    return (digest[0] / 255.0) < rate


def should_profile(task_name, task_id):
    if not profiling_enabled():
        return False
    if not task_is_profiled(task_name):
        return False
    return attempt_is_sampled(task_id)


#: literal redaction of a statement signature (#1389: attribution without
#: leaking payload). Django's own placeholders survive; quoted literals and
#: bare numbers do not, so a slow statement names its shape, never its data.
#: only single quotes carry values; double quotes carry identifiers, which
#: stay readable so a signature still names the table it is slow on. A value
#: with an apostrophe arrives doubled and matches as one literal.
_STRING_LITERAL = re.compile(r"'(?:''|[^'])*'")
_NUMBER_LITERAL = re.compile(r"\b\d+(?:\.\d+)?\b")
_WHITESPACE = re.compile(r"\s+")


def redact_sql(sql, limit=200):
    """The safe signature of a statement: structure only, never values.

    Quoted values and bare numbers become ``?``; Django's ``%s``
    placeholders and the double quoted identifiers of the ORM's own
    statements survive, so a slow statement names its shape and never its
    data. Over-redaction is the safe direction: nothing here invents
    structure the statement did not have.
    """
    signature = _STRING_LITERAL.sub("?", sql or "")
    signature = _NUMBER_LITERAL.sub("?", signature)
    signature = _WHITESPACE.sub(" ", signature).strip()
    return signature[:limit]


class _Profile:
    """The category observations of one attempt, inside one process."""

    __slots__ = ("task_id", "attempt_no", "task_name", "root_id", "parent_id",
                 "queue", "sample_rate", "mono_start", "sql_seconds",
                 "sql_queries", "slow_sql_seconds", "slow_statements",
                 "http_seconds", "http_calls", "http_errors", "outcome",
                 "closed", "partial")

    def __init__(self, task_id, attempt_no, task_name, root_id,
                 queue=None, sample_rate=0.0, parent_id=""):
        self.task_id = task_id
        self.attempt_no = attempt_no
        self.task_name = task_name
        self.root_id = root_id or ""
        self.parent_id = parent_id or ""
        self.queue = queue or ""
        self.sample_rate = sample_rate
        self.mono_start = time.monotonic()
        self.sql_seconds = 0.0
        self.sql_queries = 0
        #: the share of ``sql_seconds`` the slow statements account for, and
        #: the bounded list of their redacted signatures (#1389: slow
        #: statement attribution, parameter redaction)
        self.slow_sql_seconds = 0.0
        self.slow_statements = []
        self.http_seconds = 0.0
        self.http_calls = 0
        #: count of calls that came back with 4xx/5xx or a transport error -
        #: the difference between "the remote was slow" and "we retried it",
        #: read off the status class only, never off a URL or a body
        self.http_errors = 0
        #: outcome observed by the signal receivers ("" / "retry" /
        #: "failure"); #1330's row owns the authoritative outcome, this only
        #: marks a split as partial when its attempt did not run to the end
        self.outcome = ""
        #: whether the postrun of this attempt was seen in this process
        self.closed = False
        #: why this profile may be missing time (``duplicate_delivery``);
        #: never a number, only the reason a reader must not take the
        #: categories as the complete picture (#1389: partial stays visible)
        self.partial = []

    def note_sql(self, seconds, sql="", queries=1):
        self.sql_seconds += max(0.0, seconds)
        self.sql_queries += queries
        slow_at = float(_setting("TASK_PROFILING_SLOW_SQL_SECONDS", 0.5)
                        or 0.0)
        if slow_at <= 0 or seconds < slow_at:
            return
        self.slow_sql_seconds += max(0.0, seconds)
        limit = int(_setting("TASK_PROFILING_MAX_SLOW_STATEMENTS", 10) or 10)
        if len(self.slow_statements) < limit:
            self.slow_statements.append({
                "sql": redact_sql(sql),
                "seconds": round(seconds, 6),
            })

    def note_http(self, seconds, error=False):
        self.http_seconds += max(0.0, seconds)
        self.http_calls += 1
        if error:
            self.http_errors += 1

    def mark_partial(self, reason):
        """Record why this split cannot be the complete picture.

        Idempotent per reason: a retried attempt which also arrived twice
        reads as two reasons, the same reason twice reads as one.
        """
        if reason in self.partial:
            return False
        self.partial.append(reason)
        return True

    def report(self, active_seconds=None, wait_seconds=None):
        """The category split of this profile.

        ``unaccounted_seconds`` is what the measured categories do not
        explain; it stays a named remainder (possibly negative when
        categories nest inside each other, e.g. SQL issued from within a
        retried HTTP handler's error path) - the report never rebalances
        the categories to close the sum.

        ``sample_probability`` is the configured rate the attempt was
        selected under, so one report says how representative it is;
        ``partial`` names why time may be missing from the categories
        instead of leaving a reader to assume the split is complete.

        ``slow_statements`` carries the redacted signature of each statement
        over the slow threshold, so a reader can point at a code path without
        the report ever carrying a value that was bound into the statement.
        """
        accounted = self.sql_seconds + self.http_seconds
        report = {
            "task_id": self.task_id,
            "attempt_no": self.attempt_no,
            "task_name": self.task_name,
            "root_id": self.root_id,
            "parent_id": self.parent_id,
            "queue": self.queue,
            "sample_probability": self.sample_rate,
            "sql_seconds": round(self.sql_seconds, 6),
            "sql_queries": self.sql_queries,
            "slow_sql_seconds": round(self.slow_sql_seconds, 6),
            "slow_statements": [dict(s) for s in self.slow_statements],
            "http_seconds": round(self.http_seconds, 6),
            "http_calls": self.http_calls,
            "http_errors": self.http_errors,
            "accounted_seconds": round(accounted, 6),
            "partial": list(self.partial),
        }
        if self.outcome:
            report["outcome"] = self.outcome
        if active_seconds is not None:
            report["active_seconds"] = round(active_seconds, 6)
            report["unaccounted_seconds"] = round(
                active_seconds - accounted, 6)
            report["shape"] = self.shape(active_seconds,
                                         wait_seconds=wait_seconds)
            if wait_seconds is not None:
                report["wait_seconds"] = round(wait_seconds, 6)
        return report

    def shape(self, active_seconds, wait_seconds=None):
        """The one-word diagnosis of the attempt, or None if unknown.

        The whole point of the categories: a reader must see *which* of the
        shapes the acceptance criteria of #1389 name - slow SQL, slow
        external HTTP, CPU-bound processing, or a delay that happened
        outside the worker at all - an attempt had. The category threshold
        is a fraction of the attempt's own active time, so the reading is
        scale-free; the slow threshold (``TASK_PROFILING_SLOW_SECONDS``,
        the issue's configurable budget) is what separates "this attempt
        occupied the worker for too long" from "this attempt was fine".

        The queue shape is decided from #1330's ``wait_seconds`` rather than
        from anything measured here: an attempt whose broker wait is over
        budget while its own run is not slow was never a slow task, it was a
        message which waited - the distinction the issue asks for, and the
        reason the profiler reuses the lifecycle row instead of adding a
        second clock. Without the wait number a short attempt reads as
        ``fast``, which is all that is honestly known about it.

        A slow attempt without SQL or HTTP is CPU-bound, lock-waiting or
        bookkeeping - named ``cpu_or_unaccounted``, never renamed to a fake
        CPU total. A slow attempt whose categories are present but none
        dominates is ``mixed``. ``None`` answers for an attempt never
        measured against an active time; that stays unknown and is never
        guessed.
        """
        if active_seconds is None or active_seconds <= 0:
            return None
        slow_at = float(_setting("TASK_PROFILING_SLOW_SECONDS", 30.0) or 0.0)
        if active_seconds < slow_at:
            if wait_seconds is not None and wait_seconds >= slow_at:
                return "queue_wait"
            return "fast"
        accounted = self.sql_seconds + self.http_seconds
        threshold = active_seconds * _setting(
            "TASK_PROFILING_SHAPE_THRESHOLD", 0.5)
        if self.sql_seconds >= threshold:
            return "sql_bound"
        if self.http_seconds >= threshold:
            return "http_bound"
        if accounted <= active_seconds * 0.05:
            return "cpu_or_unaccounted"
        return "mixed"


#: the profile of the attempt this process is currently executing, or None.
#: One prefork child runs one attempt at a time, which is exactly why this
#: can be a plain module global instead of a context variable.
_current = None


def _active_profile():
    return _current


def _record_sql(seconds, sql="", queries=1):
    profile = _active_profile()
    if profile is None:
        return
    profile.note_sql(seconds, sql=sql, queries=queries)


def _record_http(seconds, error=False):
    profile = _active_profile()
    if profile is None:
        return
    profile.note_http(seconds, error=error)


def _http_was_error(result):
    """Did this call come back as 4xx/5xx? Status class only, never content."""
    status_code = getattr(result, "status_code", None)
    try:
        return status_code is not None and int(status_code) >= 400
    except (TypeError, ValueError):
        return False


class _SqlTimingWrapper:
    """``connection.execute_wrappers`` entry attributing cursor time (#1389).

    Django calls an entry as ``wrapper(execute, sql, params, many, context)``
    and returns what the wrapped executor returns. Counts and times only
    while a profiled attempt is executing; outside a profiled attempt it
    passes straight through. The statement text is handed to the profile for
    slow-statement attribution, where it is reduced to a redacted signature -
    ``params`` is never read by the profiler at all.
    """

    def __call__(self, execute, sql, params, many, context):
        if _current is None:
            return execute(sql, params, many, context)
        start = time.monotonic()
        try:
            return execute(sql, params, many, context)
        finally:
            try:
                _record_sql(time.monotonic() - start, sql)
            except Exception:  # fail open, never break the query path
                pass


def _wrap_session_send():
    """Time one ``Session.send`` into the active profile (#1389).

    Applied to the class, not to a subclass: the OWS clients of
    ``registry.ows_lib.client`` bind ``requests.Session`` directly, so a
    subclass would silently profile nothing where the epic actually needs
    the HTTP attribution. Installed once, only when the mode is enabled,
    and a no-op (one identity check, no timer) whenever no profiled attempt
    is running in this process.

    A transport error is timed too - a catalogue which answers after thirty
    seconds and one which refuses the connection are both external delay for
    the purpose of the split - and a 4xx/5xx response is counted as an error
    call so a reader can tell a slow service from a service being retried.
    """
    original = RequestsSession.send

    def send(self, request: PreparedRequest, **kwargs):
        if _current is None:
            return original(self, request, **kwargs)
        start = time.monotonic()
        try:
            result = original(self, request, **kwargs)
        except Exception:
            try:
                _record_http(time.monotonic() - start, error=True)
            except Exception:  # fail open, never break the request path
                pass
            raise
        try:
            _record_http(time.monotonic() - start,
                         error=_http_was_error(result))
        except Exception:  # fail open, never break the request path
            pass
        return result

    send._mrmap_task_profiling = True
    RequestsSession.send = send


#: connections which already carry the wrapper; weakly held, because a
#: worker closes and reopens them constantly and an id() would be recycled
_wrapped_connections = WeakSet()


def _attach_sql_wrapper(sender, connection=None, **kwargs):
    """Add the SQL timing wrapper to every new DB connection."""
    if connection is None or not profiling_enabled():
        return
    if connection in _wrapped_connections:
        return
    if not any(isinstance(w, _SqlTimingWrapper)
               for w in connection.execute_wrappers):
        connection.execute_wrappers.append(_SqlTimingWrapper())
    _wrapped_connections.add(connection)


connection_created.connect(_attach_sql_wrapper)


@task_prerun.connect
def _begin_profile(sender=None, task_id=None, task=None, **kwargs):
    """Open a profile for a sampled, allowlisted attempt (fail-open)."""
    global _current
    try:
        if task is None or not task_id:
            return
        task_name = (getattr(task, "name", None)
                     or getattr(sender, "name", None) or "unknown")
        if not should_profile(task_name, task_id):
            _current = None
            return
        # a connection opened before the mode was switched on never saw the
        # connection_created receiver - attach it here too, like the HTTP
        # seam below is installed late (#1330's toggle-after-import case)
        for alias in connections:
            _attach_sql_wrapper(None, connection=connections[alias])
        request = getattr(task, "request", None)
        attempt_no = int(getattr(request, "retries", 0) or 0)
        if not getattr(getattr(RequestsSession, "send", None),
                       "_mrmap_task_profiling", False):
            # the mode was switched on after import (settings override, a
            # worker which reloaded its config): install the HTTP seam now,
            # once - it stays a no-op outside a profiled attempt
            _wrap_session_send()
        delivery = getattr(request, "delivery_info", None) or {}
        profile = _Profile(
            str(task_id)[:64], attempt_no, task_name[:255],
            str(getattr(request, "root_id", "") or ""),
            queue=delivery.get("routing_key") or "",
            sample_rate=float(_setting("TASK_PROFILING_SAMPLE_RATE", 0.0)
                              or 0.0),
            parent_id=str(getattr(request, "parent_id", "") or ""))
        key = (profile.task_id, profile.attempt_no)
        if len(_profiles) >= int(
                _setting("TASK_PROFILING_BUFFER_LIMIT", 200) or 200):
            # full buffer: this attempt runs unprofiled. Its time costs one
            # counter and nothing else - like #1330's dropping buffer, the
            # profiler degrades its own coverage before anything else
            _stats["dropped"] += 1
            _current = None
            return
        previous = _profiles.get(key)
        if previous is not None:
            # same attempt identity seen twice in one process: a duplicate
            # delivery. This profile covers only this observation's run, so
            # saying so beats presenting a partial split as the complete one
            # (#1389: partial stays visible, never silently merged)
            profile.mark_partial("duplicate_delivery")
            _stats["duplicate_delivery"] += 1
            _stats["partial"] += 1
        _profiles[key] = profile
        _stats["profiled"] += 1
        _current = profile
    except Exception as error:  # never break or fail the task (#1330 rule)
        logger.debug("task profiling start skipped: %s", error)
        _current = None


@task_postrun.connect
def _end_profile(sender=None, task=None, **kwargs):
    """Close the profile of the attempt which just ran.

    ``task_postrun`` fires for success and failure alike, so a failed
    attempt's already measured categories stay readable in the buffer
    instead of dangling as the active profile of the slot.
    """
    global _current
    try:
        profile = _current
        if profile is not None:
            profile.closed = True
        _current = None
    except Exception as error:  # never break the task (#1330 rule)
        logger.debug("task profiling end skipped: %s", error)


@task_retry.connect
def _note_retry(sender=None, request=None, **kwargs):
    """Mark the profile of an attempt which asked for its retry.

    Celery fires ``task_retry`` before ``task_postrun``, so the retry is seen
    while the profile is still active. A retried attempt's split is complete
    for itself and incomplete for the task: it stops mid-work and the next
    attempt redoes the parts before its idempotent seam. That difference is
    recorded, not smoothed over - and the next attempt is a profile of its
    own under the same task uuid with a raised attempt counter, which is what
    lets a retry chain be read per attempt instead of blurred into one
    execution (#1330's rule, kept).
    """
    try:
        profile = _current
        if profile is None:
            return
        profile.outcome = AttemptOutcome.RETRY.value
        if profile.mark_partial("retry"):
            _stats["partial"] += 1
    except Exception as error:  # never break or fail the task (#1330 rule)
        logger.debug("task profiling retry skipped: %s", error)


@task_failure.connect
def _note_failure(sender=None, **kwargs):
    """Mark a profile whose attempt raised.

    The categories measured up to the raise stay readable - that is the
    partial answer a crashing task still gives - so the split is marked
    partial and kept rather than discarded (#1389: partial stays visible).
    """
    try:
        profile = _current
        if profile is None:
            return
        profile.outcome = AttemptOutcome.FAILURE.value
        if profile.mark_partial("failure"):
            _stats["partial"] += 1
    except Exception as error:  # never break or fail the task (#1330 rule)
        logger.debug("task profiling failure skipped: %s", error)


def active_profile():
    """The profile of the attempt running in this process, for reporting.

    #1389's follow-up steps (threshold selection, persistence, runbook
    output) read profiles through this seam; nothing here writes to the
    database and nothing writes synchronously per task.
    """
    return _current


def profile_report(active_seconds=None):
    """The category report of the active profile, or None."""
    profile = _current
    if profile is None:
        return None
    return profile.report(active_seconds=active_seconds)


def drain_reports(lifecycle=None):
    """Return and forget the buffered reports of this process (#1389).

    The batched read side of the bounded mode, mirroring #1330's flush: a
    report is produced per buffered profile. ``lifecycle`` maps an attempt
    identity ``(task_id, attempt_no)`` to the pair
    ``(active_seconds, wait_seconds)`` of #1330's attempt row; those two
    numbers close the split with a named *unaccounted* remainder and decide
    whether a slow attempt was slow in the worker or slow waiting for one. A
    caller without the row drains without them and gets the categories
    without a shape, which is honest about what it does not know. Attempts
    dropped by a full buffer are counted in :func:`profiling_stats`, never
    silently missing.
    """
    lifecycle = lifecycle or {}
    reports = []
    for (task_id, attempt_no), profile in list(_profiles.items()):
        active_seconds, wait_seconds = lifecycle.get(
            (task_id, attempt_no), (None, None))
        reports.append(profile.report(
            active_seconds=active_seconds, wait_seconds=wait_seconds))
    _profiles.clear()
    return reports


def lifecycle_map(rows):
    """Attempt identity to ``(active_seconds, wait_seconds)`` of #1330's rows.

    The join the issue asks for: the profiler's categories read against the
    lifecycle row of the same attempt, keyed exactly as both buffers are
    keyed. Accepts model instances or ``values()`` dicts.
    """
    out = {}
    for row in rows or ():
        if isinstance(row, dict):
            task_id = row.get("task_id")
            attempt_no = row.get("attempt_no")
            active = row.get("active_seconds")
            wait = row.get("wait_seconds")
        else:
            task_id = getattr(row, "task_id", None)
            attempt_no = getattr(row, "attempt_no", None)
            active = getattr(row, "active_seconds", None)
            wait = getattr(row, "wait_seconds", None)
        if task_id is None or attempt_no is None:
            continue
        out[(str(task_id)[:64], int(attempt_no))] = (active, wait)
    return out


def profiling_stats():
    """Process-local counters of what the profiler itself did."""
    return dict(_stats)


def reset_profiling_state():
    """Forget every buffered profile, the active one and the counters.

    The counters describe what this process's profiler did since the last
    reset, so a reset which left them standing would let one test read the
    drops of its predecessors.
    """
    global _current
    _profiles.clear()
    _current = None
    for key in _stats:
        _stats[key] = 0


if profiling_enabled():
    # installed at import when the mode is configured on; the prerun
    # receiver covers a deployment which turned it on only later
    _wrap_session_send()
