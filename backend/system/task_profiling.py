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
second one. Persistence of profiles, threshold/budget selection of which
attempts to report, EXPLAIN-side analysis and the operator runbook are the
following steps of the same issue - this module defines what they read.
"""

import hashlib
import time

from celery.signals import task_postrun, task_prerun
from django.conf import settings
from django.db.backends.signals import connection_created
from requests import PreparedRequest
from requests.sessions import Session as RequestsSession

logger = settings.ROOT_LOGGER

#: process-local profiles since the last report, keyed by
#: (task_id, attempt_no) exactly like #1330's attempt buffer, so a profile
#: joins its attempt row without a second identity scheme.
_profiles = {}

_stats = {"profiled": 0, "dropped": 0}


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


class _Profile:
    """The category observations of one attempt, inside one process."""

    __slots__ = ("task_id", "attempt_no", "task_name", "root_id",
                 "mono_start", "sql_seconds", "sql_queries",
                 "http_seconds", "http_calls", "partial")

    def __init__(self, task_id, attempt_no, task_name, root_id):
        self.task_id = task_id
        self.attempt_no = attempt_no
        self.task_name = task_name
        self.root_id = root_id or ""
        self.mono_start = time.monotonic()
        self.sql_seconds = 0.0
        self.sql_queries = 0
        self.http_seconds = 0.0
        self.http_calls = 0
        #: True when the profile stopped observing (buffer overflow) or
        #: never saw its attempt's end - a report over it is visibly partial
        self.partial = False

    def report(self, active_seconds=None):
        """The category split of this profile.

        ``unaccounted_seconds`` is what the measured categories do not
        explain; it stays a named remainder (possibly negative when
        categories nest inside each other, e.g. SQL issued from within a
        retried HTTP handler's error path) - the report never rebalances
        the categories to close the sum.
        """
        accounted = self.sql_seconds + self.http_seconds
        report = {
            "task_id": self.task_id,
            "attempt_no": self.attempt_no,
            "task_name": self.task_name,
            "root_id": self.root_id,
            "sql_seconds": round(self.sql_seconds, 6),
            "sql_queries": self.sql_queries,
            "http_seconds": round(self.http_seconds, 6),
            "http_calls": self.http_calls,
            "accounted_seconds": round(accounted, 6),
            "partial": self.partial,
        }
        if active_seconds is not None:
            report["active_seconds"] = round(active_seconds, 6)
            report["unaccounted_seconds"] = round(
                active_seconds - accounted, 6)
        return report


#: the profile of the attempt this process is currently executing, or None.
#: One prefork child runs one attempt at a time, which is exactly why this
#: can be a plain module global instead of a context variable.
_current = None


def _active_profile():
    return _current if _current is not None and not _current.partial else None


def _record_sql(seconds, queries=1):
    profile = _active_profile()
    if profile is None:
        return
    profile.sql_seconds += max(0.0, seconds)
    profile.sql_queries += queries


def _record_http(seconds):
    profile = _active_profile()
    if profile is None:
        return
    profile.http_seconds += max(0.0, seconds)
    profile.http_calls += 1


class _SqlTimingWrapper:
    """``connection.execute_wrappers`` entry attributing cursor time (#1389).

    Counts and times only while a profiled attempt is executing; outside a
    profiled attempt it passes straight through.
    """

    def execute(self, sql, params, many, context):
        if _current is None:
            return context["executor"](sql, params, many, context)
        start = time.monotonic()
        try:
            return context["executor"](sql, params, many, context)
        finally:
            try:
                _record_sql(time.monotonic() - start)
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
    """
    original = RequestsSession.send

    def send(self, request: PreparedRequest, **kwargs):
        if _current is None:
            return original(self, request, **kwargs)
        start = time.monotonic()
        try:
            return original(self, request, **kwargs)
        finally:
            try:
                _record_http(time.monotonic() - start)
            except Exception:  # fail open, never break the request path
                pass

    send._mrmap_task_profiling = True
    RequestsSession.send = send


_wrapped_connections = set()


def _attach_sql_wrapper(sender, connection=None, **kwargs):
    """Add the SQL timing wrapper to every new DB connection."""
    if connection is None or not profiling_enabled():
        return
    if id(connection) in _wrapped_connections:
        return
    if not any(isinstance(w, _SqlTimingWrapper)
               for w in connection.execute_wrappers):
        connection.execute_wrappers.append(_SqlTimingWrapper())
    _wrapped_connections.add(id(connection))


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
        request = getattr(task, "request", None)
        attempt_no = int(getattr(request, "retries", 0) or 0)
        if not getattr(getattr(RequestsSession, "send", None),
                       "_mrmap_task_profiling", False):
            # the mode was switched on after import (settings override, a
            # worker which reloaded its config): install the HTTP seam now,
            # once - it stays a no-op outside a profiled attempt
            _wrap_session_send()
        profile = _Profile(
            str(task_id)[:64], attempt_no, task_name[:255],
            str(getattr(request, "root_id", "") or ""))
        key = (profile.task_id, profile.attempt_no)
        if len(_profiles) >= int(
                _setting("TASK_PROFILING_BUFFER_LIMIT", 200) or 200):
            profile.partial = True
            _stats["dropped"] += 1
        _profiles[key] = profile
        _stats["profiled"] += 1
        _current = profile if not profile.partial else None
    except Exception as error:  # never break or fail the task (#1330 rule)
        logger.debug("task profiling start skipped: %s", error)
        _current = None


@task_postrun.connect
def _end_profile(sender=None, **kwargs):
    """Close the profile of the attempt which just ran.

    ``task_postrun`` fires for success and failure alike, so a failed
    attempt's already measured categories stay readable in the buffer
    instead of dangling as the active profile of the slot.
    """
    global _current
    try:
        _current = None
    except Exception as error:  # never break the task (#1330 rule)
        logger.debug("task profiling end skipped: %s", error)


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


def drain_reports(active_seconds_map=None):
    """Return and forget the buffered reports of this process (#1389).

    The batched read side of the bounded mode, mirroring #1330's flush: a
    report is produced per buffered profile, the attempt's own measured
    ``active_seconds`` (when the caller has it - #1330's row owns that
    number) closes the split with a named *unaccounted* remainder, and a
    profile which overflowed the buffer is reported as ``partial``.
    """
    active_seconds_map = active_seconds_map or {}
    reports = []
    for (task_id, attempt_no), profile in list(_profiles.items()):
        reports.append(profile.report(
            active_seconds=active_seconds_map.get((task_id, attempt_no))))
    _profiles.clear()
    return reports


def profiling_stats():
    """Process-local counters of what the profiler itself did."""
    return dict(_stats)


def reset_profiling_state():
    """Forget every buffered profile and the active one (tests, restarts)."""
    global _current
    _profiles.clear()
    _current = None


if profiling_enabled():
    # installed at import when the mode is configured on; the prerun
    # receiver covers a deployment which turned it on only later
    _wrap_session_send()
