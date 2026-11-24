"""Bounded opt-in root-cause profiling for slow Celery tasks (#1389).

The attempt telemetry of #1330 (``system.capacity_telemetry``) answers *how
long* an attempt occupied a worker; this module answers *why* it took that
long, by splitting the attempt's active time into coarse cost categories:

*   ``sql_seconds`` / ``sql_queries`` - time inside database cursors and the
    number of statements, attributed via the connection's execute wrappers;
*   ``http_seconds`` / ``http_calls`` - time inside an outgoing ``requests``
    send (remote OGC waiting included), attributed via the ``requests``
    signal, never by patching the transport;
*   memory (#1620) - the movement of this process's resident set across the
    span of the attempt: how far the attempt pushed the kernel's high water
    mark, how many bytes it still held at the end, and what the worker alone
    occupies against the cgroup's ceiling. Procfs is the only source read, so
    a platform without it simply reports no memory numbers.
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


#: the two /proc reads of a memory sample, in the order they are worth
#: paying for: the high water mark is one line of status, the private dirty
#: set is the (heavier) rollup of every mapping of this process.
_PROC_STATUS = "/proc/self/status"
_PROC_SMAPS_ROLLUP = "/proc/self/smaps_rollup"
_CGROUP_LIMIT_V2 = "/sys/fs/cgroup/memory.max"
_CGROUP_LIMIT_V1 = "/sys/fs/cgroup/memory/memory.limit_in_bytes"


def _read_first_value(path, key):
    """The integer of ``key`` from a ``key: value kB`` style proc file."""
    try:
        with open(path, "r") as handle:
            for line in handle:
                if line.startswith(key):
                    return int(line.split()[1]) * 1024
    except (OSError, ValueError, IndexError):
        pass
    return None


def memory_snapshot():
    """The memory of this process right now, or None without procfs.

    Three numbers, each answering a different question, read in one place so
    a caller cannot mix a start sample with an end sample of another kind:

    ``high_water``
        ``VmHWM`` - the highest the resident set ever reached in this process.
        The kernel keeps it monotonically, so an attempt which grew and shrank
        between two samples cannot hide its peak; the price is that the number
        belongs to the worker, which is why an attempt is judged by how far it
        moved it rather than by its absolute value.
    ``resident``
        ``VmRSS`` - what is held right now, the difference of two of which is
        the retained-object growth of the measured span.
    ``private_dirty``
        Resident pages private to this process, the closest procfs answers to
        "what this worker alone occupies": shared and clean file-backed pages
        belong to the machine, and charging them to an attempt would blame
        every task for the interpreter's own mappings.
    """
    high_water = _read_first_value(_PROC_STATUS, "VmHWM:")
    resident = _read_first_value(_PROC_STATUS, "VmRSS:")
    private_dirty = private_dirty_bytes()
    if high_water is None and resident is None and private_dirty is None:
        return None
    return {
        "high_water": high_water,
        "resident": resident,
        "private_dirty": private_dirty,
    }


def private_dirty_bytes():
    """Resident pages private to this process, in bytes (None if unknown)."""
    return _read_first_value(_PROC_SMAPS_ROLLUP, "Private_Dirty:")


def cgroup_limit_bytes():
    """The memory ceiling of this container in bytes, or None.

    A peak without its limit is a number nobody can act on, and inside a
    container the ceiling is the cgroup's, never the host's ``MemTotal``.
    Read on every call and never cached (#1620 review): a prefork worker
    lives across deploys and operator actions, and ``docker update --memory``
    - which is exactly what an operator reaches for during the incident an
    OOM report is read in - moves the ceiling under the running process. A
    cached reading would then keep judging every peak against the old
    ceiling, self-consistent enough to look trustworthy. The read is one
    small file, in the same class as the procfs reads of the samples.
    """
    return _first_cgroup_limit((_CGROUP_LIMIT_V2, _CGROUP_LIMIT_V1))


def _first_cgroup_limit(paths):
    """The first of ``paths`` which names a real ceiling, or None.

    cgroup v1 answers "unlimited" with a page-aligned giant, which is no more
    of a ceiling than v2's "max" and must not read as one.
    """
    for path in paths:
        number = _read_cgroup_limit(path)
        if number is not None and 0 < number <= 2 ** 62:
            return number
    return None


def _read_cgroup_limit(path):
    """The integer a cgroup limit file holds, or None if it cannot answer."""
    try:
        with open(path, "r") as handle:
            value = handle.read().strip()
    except OSError:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _mib(value):
    """A byte count in MiB, the granularity a report is read at."""
    if value is None:
        return None
    return round(value / 1024 / 1024, 2)


def _max_span(start, end, key):
    """How far a span moved a monotonic counter, never below zero."""
    if not start or not end:
        return None
    first, last = start.get(key), end.get(key)
    if first is None or last is None:
        return None
    return max(0, last - first)


def _memory_sample_seconds():
    """The seam duration from which a memory read is worth its cost."""
    return float(_setting("TASK_PROFILING_MEMORY_SAMPLE_SECONDS", 0.5) or 0.0)


def sample_memory(seconds=None):
    """Note the memory of the active attempt, if one is being profiled.

    Called when a profile closes, so the end of the attempt's span is read
    while the profile is still the active one, and from a seam which just
    spent ``seconds`` on one statement or one request. ``seconds`` is the
    cheap gate on that second caller: ``smaps_rollup`` is a read over every
    mapping of the process, so a task of ten thousand fast queries must not
    pay it per query, while the one which held the cursor for seconds is
    exactly where a peak is expected to appear. Fail-open like every other
    seam here: a broken read costs the measurement, never the attempt.
    """
    profile = _active_profile()
    if profile is None:
        return
    if seconds is not None and seconds < _memory_sample_seconds():
        return
    try:
        snapshot = memory_snapshot()
        if snapshot is None:
            return
        profile.memory_end = snapshot
    except Exception as error:  # never break or fail the task (#1330 rule)
        logger.debug("task profiling memory sample skipped: %s", error)


class _Profile:
    """The category observations of one attempt, inside one process."""

    __slots__ = ("task_id", "attempt_no", "task_name", "root_id", "parent_id",
                 "queue", "sample_rate", "mono_start", "sql_seconds",
                 "sql_queries", "slow_sql_seconds", "slow_statements",
                 "http_seconds", "http_calls", "http_errors", "outcome",
                 "closed", "partial", "memory_start", "memory_end")

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
        #: memory at the start and at the last sample of this attempt (#1620).
        #: Both are read off procfs, so either can be None where there is no
        #: procfs; the report then says nothing about memory rather than
        #: presenting the worker's own footprint as the attempt's.
        self.memory_start = None
        self.memory_end = None

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
        report.update(self.memory_report())
        if active_seconds is not None:
            report["active_seconds"] = round(active_seconds, 6)
            report["unaccounted_seconds"] = round(
                active_seconds - accounted, 6)
            report["shape"] = self.shape(active_seconds,
                                         wait_seconds=wait_seconds)
            if wait_seconds is not None:
                report["wait_seconds"] = round(wait_seconds, 6)
        return report

    def memory_report(self):
        """What this attempt did to the memory of its worker, or nothing.

        The absolute values belong to the process, not to the attempt: a
        prefork worker is reused, so its resident set already holds whatever
        earlier attempts left behind. What is attributable is therefore the
        movement inside the span of this attempt:

        ``peak_rise_mib``
            how far the attempt pushed the process's high water mark - the
            number a peak measurement is really about, because a worker's
            peak is only ever reached during some attempt's work;
        ``retained_mib``
            resident bytes still held when the attempt ended, i.e. objects
            that outlived it - the retained-object half of #1620;
        ``private_dirty_mib``
            what the process alone occupies at the last sample, against
            ``limit_mib`` of the container, because a ceiling is what turns a
            peak into a risk of an OOM kill.

        Each key is present only when the reading behind it answered: a
        hardened procfs without ``smaps_rollup`` costs
        ``private_dirty_mib``, a ceiling-less container costs ``limit_mib``
        and ``of_limit`` - and a key whose source could not answer is absent,
        never present as ``null`` (#1620 review). A reader must never see a
        memory claim the platform did not support, in the shape of a null it
        could mistake for a measured zero.

        With no procfs at all, or an attempt never sampled, this answers
        ``{}`` and the report carries no memory claim at all.
        """
        start, end = self.memory_start, self.memory_end
        if not start or not end:
            return {}
        report = {}
        peak_rise = _max_span(start, end, "high_water")
        if peak_rise is not None:
            report["memory_peak_rise_mib"] = _mib(peak_rise)
        if end.get("high_water") is not None:
            report["memory_peak_mib"] = _mib(end["high_water"])
        retained = _max_span(start, end, "resident")
        if retained is not None:
            report["memory_retained_mib"] = _mib(retained)
        if end.get("private_dirty") is not None:
            report["memory_private_dirty_mib"] = _mib(end["private_dirty"])
        limit = cgroup_limit_bytes()
        if limit and end.get("high_water"):
            report["memory_limit_mib"] = _mib(limit)
            report["memory_of_limit"] = round(
                end["high_water"] / limit, 4)
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
            return self._unaccounted_shape()
        return "mixed"

    def _unaccounted_shape(self):
        """Which of the two readings of an unaccounted slow attempt holds."""
        if self._memory_dominant():
            return "memory_bound"
        return "cpu_or_unaccounted"

    def _memory_dominant(self):
        """Whether this attempt's own peak rise explains an unaccounted run.

        Without this the only reading a memory-hungry task can get is
        ``cpu_or_unaccounted``, which sends a reader looking at CPU when the
        actual cost is the objects the attempt held. The threshold is an
        absolute MiB figure rather than a share of the attempt: a peak is
        worth naming because of how close it comes to the container's ceiling,
        not because of how long the attempt ran. Only ever consulted when
        neither SQL nor HTTP was dominant, so the four shapes of #1389 keep
        their meaning.
        """
        rise = _max_span(self.memory_start, self.memory_end, "high_water")
        if not rise:
            return False
        at_mib = float(_setting("TASK_PROFILING_MEMORY_MIB", 128) or 0.0)
        return at_mib > 0 and rise >= at_mib * 1024 * 1024


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
    # a statement which held the cursor for seconds is where a peak appears,
    # so this is the seam worth reading memory at - gated on its duration
    # inside sample_memory, so the fast majority pays nothing
    sample_memory(seconds)


def _record_http(seconds, error=False):
    profile = _active_profile()
    if profile is None:
        return
    profile.note_http(seconds, error=error)
    # the same reading for the remote half: a catalogue response is held in
    # memory by the caller, so a slow answer and a big answer move together
    sample_memory(seconds)


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


def _ensure_seams():
    """Install both measurement seams on a process which missed their setup.

    A connection opened before the mode was switched on never saw the
    ``connection_created`` receiver, and a worker which switched the mode on
    after import never installed the HTTP seam. Both are idempotent, so this
    runs on every profiled attempt (#1330's toggle-after-import case).
    """
    for alias in connections:
        _attach_sql_wrapper(None, connection=connections[alias])
    if not getattr(getattr(RequestsSession, "send", None),
                   "_mrmap_task_profiling", False):
        # the HTTP seam stays a no-op outside a profiled attempt
        _wrap_session_send()


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
        _ensure_seams()
        request = getattr(task, "request", None)
        attempt_no = int(getattr(request, "retries", 0) or 0)
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
        # the span begins with the attempt, not with its first chunk: an
        # attempt's memory claim is the movement between these two reads, and
        # reading it here (rather than lazily on the first sample) keeps a
        # short attempt which allocates nothing measurable honest about it.
        # Its own guard: a procfs which cannot answer must cost the memory
        # claim of this attempt, not the categories it is about to measure.
        _open_memory_span(profile)
    except Exception as error:  # never break or fail the task (#1330 rule)
        logger.debug("task profiling start skipped: %s", error)
        _current = None


def _open_memory_span(profile):
    """Read the memory span's start, or leave the attempt without one.

    The span begins with the attempt, not with its first chunk: an attempt's
    memory claim is the movement between these two reads, and reading it here
    (rather than lazily on the first sample) keeps a short attempt which
    allocates nothing measurable honest about it. Its own guard: a procfs
    which cannot answer costs this attempt's memory claim, never the
    categories the attempt is about to measure.
    """
    try:
        profile.memory_start = memory_snapshot()
        profile.memory_end = profile.memory_start
    except Exception as error:  # fail open, as every seam here does
        logger.debug("task profiling start sample skipped: %s", error)


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
            # sampled while the profile is still the active one, so the end of
            # the attempt's span is captured before the slot is cleared
            sample_memory()
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
    for (task_id, attempt_no), profile in _profiles.items():
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
