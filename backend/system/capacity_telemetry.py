"""The bounded attempt telemetry of the Celery workers (#1330).

This module is the *measurement source* the capacity snapshots of #1326 read.
It answers exactly two duration classes for one task attempt and labels them
apart, because epic #1324's central evidence rule says they must never be
mixed:

*   **occupied worker slot seconds** - ``active_seconds`` of
    ``system.models.CeleryTaskAttempt``: what the attempt really ran inside a
    worker slot (remote HTTP waiting included), measured with the monotonic
    clock between ``task_prerun`` and the terminal signal of the *same*
    worker process. Queue waiting is never part of it.
*   **queue waiting** - ``started_at`` minus ``published_at``: the message
    carries the wall time of its publish as a header stamp (see
    ``stamp_publish_time``), so the worker reads the stamp off the message it
    actually executed. A message published before this feature, or by a
    foreign producer, carries no stamp and the wait stays *unknown* for it.

The end-to-end elapsed duration of a job is deliberately **not** measured
here - the existing run tables answer that class (``harvest_durations()`` of
#693, the monitoring runs, the update jobs) and this module only carries the
correlation keys (``root_id``, ``periodic_name``) to join them.

How the writes are bounded (the issue's "no synchronous write storm"): a
worker process collects attempts in a small in-process buffer and writes it
with one ``INSERT ... ON CONFLICT DO NOTHING`` statement per batch. Buffer
size, batch size, flush age, retention and a row cap are settings; on a
failing or slow database the collector goes quiet for a cooldown instead of
retrying per task. What the collector never does is block or fail the task it
observes: every receiver swallows its own error into a log line, the same
rule #1320's incident publishers live by.

Data quality of what this leaves behind (#1330's acceptance criteria):

*   A lost worker loses its un-flushed buffer - those attempts are *absent*,
    and open rows already flushed become ``abandoned`` by the sweep of
    ``system.tasks`` after a grace window. No completed duration is ever
    guessed for them, and open attempts are never summed as occupied time.
*   ``Task.retry`` re-publishes under the same task uuid; the attempt counter
    of the request separates the attempts, and each counted attempt's active
    time is measured for itself.
*   A fire of a ``SingletonTask`` which found the lock taken never ran, so it
    measured nothing: it is recorded as the outcome ``skipped`` with a NULL
    duration, which keeps it out of every distribution and makes its count
    the answer to "how many fires of this schedule did the deployment drop"
    (#1827). It is not a terminal sample - the reads of this module count it
    separately, because "the fire is over" and "the attempt executed" are
    different statements.
*   Duplicate events and concurrent redelivery collapse onto the attempt's
    partial unique keys - the duplicate is dropped, never double counted.
"""

import time
from datetime import UTC, datetime
from logging import Logger

from celery.signals import (before_task_publish, task_failure, task_postrun,
                            task_prerun, task_retry, task_revoked,
                            task_success, worker_process_init,
                            worker_process_shutdown)
from django.conf import settings
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from extras.tasks import task_skipped
from system.models import (AttemptOutcome, AttemptQuality,
                           CeleryTaskAttempt)

logger: Logger = settings.ROOT_LOGGER

#: the message header carrying the publish wall time, stamped per *publish*
#: (so a retry's message carries the moment its own attempt was enqueued)
PUBLISH_STAMP_HEADER = "mrmap-published-at"

#: outcome precedence: a signal of a higher class replaces a lower one for
#: the same attempt, the first finish time stays. A retried attempt reports
#: ``task_failure`` too when the retry budget ran out - the terminal failure
#: of an exhausted budget outranks the last scheduled retry.
#:
#: A ``skipped`` fire is not in this table because it does not compete: the
#: answer of a skip is final (see ``_mark_terminal``), because celery fires
#: ``task_success`` and ``task_postrun`` for it too - the fire returned its
#: "skipped" text to celery as an ordinary return value - and those arrive
#: after the skip was announced (#1827).
_OUTCOME_RANK = {
    "": 0,
    AttemptOutcome.SUCCESS.value: 1,
    AttemptOutcome.REVOKED.value: 2,
    AttemptOutcome.RETRY.value: 3,
    AttemptOutcome.FAILURE.value: 4,
}


class _Attempt:
    """One attempt observed by one worker process, not yet (or not only) in the database."""

    __slots__ = ("task_id", "attempt_no", "task_name", "queue", "worker",
                 "root_id", "parent_id", "periodic_name", "published_at",
                 "started_at", "finished_at", "active_seconds", "outcome",
                 "quality", "mono_start", "skipped")

    def __init__(self, task_id, attempt_no, task_name, queue, worker,
                 root_id, parent_id, periodic_name, published_at, started_at,
                 mono_start):
        self.task_id = task_id
        self.attempt_no = attempt_no
        self.task_name = task_name
        self.queue = queue
        self.worker = worker
        self.root_id = root_id or ""
        self.parent_id = parent_id or ""
        self.periodic_name = periodic_name or ""
        self.published_at = published_at
        self.started_at = started_at
        self.finished_at = None
        self.active_seconds = None
        self.outcome = ""
        self.quality = set()
        self.mono_start = mono_start
        #: set by ``note_skipped_fire``: the fire never ran its body, so its
        #: duration stays unmeasured no matter which signal arrives next
        self.skipped = False

    @property
    def is_terminal(self):
        return self.outcome != ""

    def to_row(self):
        wait_seconds = None
        if self.published_at is not None and self.started_at is not None:
            # clock skew between a publishing web process and this worker
            # can read a hair under zero; seconds before the publish are not
            # a measurable wait, zero is
            wait_seconds = max(
                0.0, (self.started_at - self.published_at).total_seconds())
        return CeleryTaskAttempt(
            task_id=self.task_id,
            attempt_no=self.attempt_no,
            task_name=self.task_name[:255],
            queue=self.queue[:64],
            worker=self.worker[:255],
            root_id=self.root_id,
            parent_id=self.parent_id,
            periodic_name=self.periodic_name,
            published_at=self.published_at,
            started_at=self.started_at,
            finished_at=self.finished_at,
            active_seconds=self.active_seconds,
            wait_seconds=wait_seconds,
            outcome=self.outcome,
            quality=sorted(self.quality),
        )


#: attempts observed since the last flush, keyed by (task_id, attempt_no).
#: A module-level dict: prefork children each have their own copy, which is
#: exactly right - each child measured its own executions.
_buffer = {}

#: process-local counters of what the collector itself did (per worker
#: process; #1326 reads the *database*, not these, for capacity - these are
#: the "is the collector healthy" counters for the log line).
_stats = {"buffered_rows": 0, "dropped": 0, "flush_errors": 0}

_flush_due_at = None       # monotonic deadline of the next age-forced flush
_quiet_until = None        # monotonic moment flushes resume after an error
_last_drop_log_at = None   # rate limit for the overload log line


def _setting(name, default):
    return getattr(settings, name, default)


#: whether THIS process went through celery's worker process start-up.
#: Set only by the ``worker_process_init`` signal below, which no other
#: process kind fires - the argv sniff of ``MrMap.celery`` is too coarse
#: for this decision (it matches any command line mentioning
#: ``celery``/``worker``, including a ``manage.py test`` naming such a
#: test module), and collecting from a web process would be exactly the
#: wrong-process writes #1330 promises to avoid.
_worker_process_started = False


def collection_enabled():
    """Whether this process records attempts at all.

    Off by the settings kill-switch; on only in a process that went
    through celery's worker process start-up (``worker_process_init``,
    fired once per prefork child and once for solo/gevent) - a web process
    or the test runner must not accumulate or flush a buffer of task
    signals it did not execute. Tests which drive the signals by hand set
    ``CAPACITY_TELEMETRY_COLLECT_ANY_PROCESS``.
    """
    if not _setting("CAPACITY_TELEMETRY_ENABLED", False):
        return False
    if _setting("CAPACITY_TELEMETRY_COLLECT_ANY_PROCESS", False):
        return True
    return _worker_process_started


def _parsed_stamp(headers):
    """The publish wall time of a message header dict, or None.

    Reads the one header this collector stamps and nothing else; an
    unparsable value answers None, which makes the attempt's queue wait
    *unknown* without losing its measured execution time.
    """
    if not isinstance(headers, dict):
        return None
    raw = headers.get(PUBLISH_STAMP_HEADER)
    if raw is None:
        return None
    try:
        # the stamp is written as an epoch float; a deployment which
        # replaces the header by hand may write an ISO text
        return datetime.fromtimestamp(float(raw), tz=UTC)
    except (TypeError, ValueError):
        try:
            parsed = parse_datetime(str(raw))
        except (TypeError, ValueError):
            return None
        if parsed is None:
            return None
        if timezone.is_naive(parsed):
            parsed = timezone.make_aware(parsed, UTC)
        return parsed


def _begin_attempt(sender, task_id, task):
    request = getattr(task, "request", None)
    if request is None or not task_id:
        return
    task_name = (getattr(sender, "name", None)
                 or getattr(task, "name", None) or "unknown")
    delivery = getattr(request, "delivery_info", None) or {}
    queue = delivery.get("routing_key") or ""
    headers = getattr(request, "headers", None)
    periodic_name = (headers.get("periodic_task_name")
                     if isinstance(headers, dict) else None)
    entry = _Attempt(
        task_id=str(task_id)[:64],
        attempt_no=int(getattr(request, "retries", 0) or 0),
        task_name=task_name,
        queue=queue,
        worker=getattr(request, "hostname", None) or "",
        root_id=(str(request.root_id)[:64]
                 if getattr(request, "root_id", None) else None),
        parent_id=(str(request.parent_id)[:64]
                   if getattr(request, "parent_id", None) else None),
        periodic_name=(str(periodic_name)[:255] if periodic_name else None),
        published_at=_parsed_stamp(headers),
        started_at=timezone.now(),
        mono_start=time.monotonic(),
    )
    key = (entry.task_id, entry.attempt_no)
    previous = _buffer.get(key)
    if previous is not None:
        if previous.is_terminal:
            # the terminal signal of this attempt was already seen and a
            # second execution of the same identity started: a redelivery
            # after a finish. The measured terminal sample stays valid.
            previous.quality.add(AttemptQuality.REDELIVERED.value)
            return
        # a second start before any end - a concurrent duplicate delivery:
        # one merged sample, flagged, and the first observation's identity
        # and start time carry it
        entry.quality.add(AttemptQuality.REDELIVERED.value)
        entry.started_at = previous.started_at
        entry.mono_start = min(previous.mono_start, entry.mono_start)
    _buffer[key] = entry
    _enforce_buffer_limit()
    _flush_if_due()


def _finish_attempt(task, outcome):
    request = getattr(task, "request", None)
    if request is None:
        return
    task_id = str(getattr(request, "id", None) or "")[:64]
    if not task_id:
        return
    key = (task_id, int(getattr(request, "retries", 0) or 0))
    entry = _buffer.get(key)
    if entry is None:
        # a worker restart can flush the prerun of an attempt away while the
        # process keeps running; counting a finish without the matching
        # start would invent its start time, so it stays unobserved
        return
    _mark_terminal(entry, outcome)
    _flush_if_due()


def _mark_terminal(entry, outcome):
    if entry.skipped:
        # the fire answered "skipped" and celery reports that answer as an
        # ordinary successful return, so its success/postrun arrives here too
        # - and a fire which never ran its body has no duration to measure.
        # The answer of the skip is final (#1827).
        return
    moment = timezone.now()
    if entry.active_seconds is None:
        entry.active_seconds = max(
            0.0, time.monotonic() - entry.mono_start)
        entry.finished_at = moment
    if _OUTCOME_RANK.get(outcome, 0) > _OUTCOME_RANK.get(entry.outcome, 0):
        entry.outcome = outcome


def _note_skipped_fire(task, task_id, attempt_no):
    """Records one fire of a singleton task which found the lock taken.

    The fire executed nothing, so its row carries no ``active_seconds`` and
    no ``finished_at``: it is terminal - the fire is over - but it joins no
    duration distribution, only the count of what the deployment dropped
    (#1827). The row rides the same bounded batch as every other observation
    of this worker process, which is what keeps a dropped fire a number in
    the database instead of an INFO line in a log.
    """
    task_id = str(task_id or "")[:64]
    if not task_id:
        return
    key = (task_id, int(attempt_no or 0))
    entry = _buffer.get(key)
    if entry is None:
        # the prerun of this fire is not in the buffer (its id is unknown
        # here, or a flush already settled it): open an observation of the
        # skip itself rather than lose it - the start time is this moment,
        # which is when the fire was dropped
        request = getattr(task, "request", None)
        delivery = getattr(request, "delivery_info", None) or {}
        headers = getattr(request, "headers", None)
        periodic_name = (headers.get("periodic_task_name")
                         if isinstance(headers, dict) else None)
        entry = _Attempt(
            task_id=task_id,
            attempt_no=int(attempt_no or 0),
            task_name=(getattr(task, "name", None) or "unknown"),
            queue=delivery.get("routing_key") or "",
            worker=getattr(request, "hostname", None) or "",
            root_id=(str(request.root_id)[:64]
                     if getattr(request, "root_id", None) else None),
            parent_id=(str(request.parent_id)[:64]
                       if getattr(request, "parent_id", None) else None),
            periodic_name=(str(periodic_name)[:255] if periodic_name
                           else None),
            # deliberately no publish stamp: the wait of a message which was
            # dropped before it ran is not the wait of an execution, and a
            # number here would join the queue-wait distributions
            published_at=None,
            started_at=timezone.now(),
            mono_start=time.monotonic(),
        )
    entry.skipped = True
    entry.outcome = AttemptOutcome.SKIPPED.value
    _enforce_buffer_limit()
    _flush_if_due()


@task_skipped.connect(weak=False)
def note_skipped_fire(sender=None, task_id=None, attempt_no=0, **kwargs):
    """The receiver of the singleton skip seam (#1827).

    Like every other receiver here it swallows its own error into a log line:
    a diagnostic about a dropped fire must never cost the fire answering it.
    """
    if not collection_enabled():
        return
    try:
        _note_skipped_fire(sender, task_id, attempt_no)
    except Exception as error:
        logger.debug("capacity telemetry: failed to record a skipped fire: "
                     "%s", error)


def _enforce_buffer_limit():
    limit = _setting("CAPACITY_TELEMETRY_BUFFER_LIMIT", 1000)
    if limit <= 0 or len(_buffer) <= limit:
        return
    # drop the oldest open observations first (the newest are the ones about
    # to finish anyway); never below the limit, always keeping capacity
    overflow = len(_buffer) - limit
    open_entries = sorted(
        (entry for entry in _buffer.values() if not entry.is_terminal),
        key=lambda entry: entry.mono_start)
    victims = open_entries[:overflow]
    for entry in victims:
        _buffer.pop((entry.task_id, entry.attempt_no), None)
    _stats["dropped"] += len(victims)
    global _last_drop_log_at
    now = time.monotonic()
    if victims and (
            _last_drop_log_at is None
            or now - _last_drop_log_at >= _setting(
                "CAPACITY_TELEMETRY_FLUSH_SECONDS", 30)):
        _last_drop_log_at = now
        logger.warning(
            "capacity telemetry: worker buffer over its limit of %d, %d "
            "open attempts dropped and not measured (#1330; total dropped "
            "since start: %d)", limit, len(victims), _stats["dropped"])


def _flush_if_due(force=False):
    global _flush_due_at
    if not _buffer:
        return
    now = time.monotonic()
    if _quiet_until is not None and now < _quiet_until and not force:
        return
    threshold = _setting("CAPACITY_TELEMETRY_FLUSH_THRESHOLD", 100)
    if _flush_due_at is None:
        _flush_due_at = now + _setting(
            "CAPACITY_TELEMETRY_FLUSH_SECONDS", 30)
        return  # the deadline is armed by the first buffered attempt
    if not force and now < _flush_due_at and len(_buffer) < threshold:
        return
    flush_attempts()


def flush_attempts():
    """Writes the buffered attempts with one insert and trims what is settled.

    One ``INSERT ... ON CONFLICT DO NOTHING`` for the whole batch: open
    attempts are written too, so a worker lost later leaves an open row the
    sweep can close as ``abandoned`` instead of silence. Terminal entries of
    a successfully written batch leave the buffer; open ones stay until their
    own terminal event arrives and their row is written on the next flush.

    Returns a small summary (for tests and the log line); it never raises.
    """
    global _flush_due_at, _quiet_until
    batch = list(_buffer.values())
    summary = {"attempted": len(batch), "written": 0, "error": None}
    if not batch:
        return summary
    try:
        CeleryTaskAttempt.objects.bulk_create(
            [entry.to_row() for entry in batch],
            ignore_conflicts=True)
    except Exception as error:
        _stats["flush_errors"] += 1
        cooldown = _setting(
            "CAPACITY_TELEMETRY_RETRY_COOLDOWN_SECONDS", 60)
        _quiet_until = time.monotonic() + cooldown
        logger.warning(
            "capacity telemetry: flush of %d buffered attempts failed (%s); "
            "collector quiet for %s s, the attempts stay in the bounded "
            "buffer meanwhile (#1330).", len(batch), error, cooldown)
        summary["error"] = str(error)
        return summary
    _quiet_until = None
    written = 0
    for entry in batch:
        written += 1
        if entry.is_terminal:
            # settled: the row of this attempt's execution is in the
            # database and no later event of this process can change it
            _buffer.pop((entry.task_id, entry.attempt_no), None)
    _stats["buffered_rows"] += written
    _flush_due_at = time.monotonic() + _setting(
        "CAPACITY_TELEMETRY_FLUSH_SECONDS", 30)
    summary["written"] = written
    return summary


def collector_stats():
    """The health counters of this process's collector (#1330 diagnostics).

    Process-local by nature - every worker process has its own. The capacity
    numbers #1326 must aggregate come from the database, not from here; what
    these answer is whether the collection itself kept up.
    """
    return {
        "buffered": len(_buffer),
        "buffered_rows": _stats["buffered_rows"],
        "dropped": _stats["dropped"],
        "flush_errors": _stats["flush_errors"],
    }


def reset_collector():
    """Empties buffer and counters; the seam the unit tests isolate with."""
    global _flush_due_at, _quiet_until, _last_drop_log_at
    global _worker_process_started
    _buffer.clear()
    _stats.update({"buffered_rows": 0, "dropped": 0, "flush_errors": 0})
    _flush_due_at = None
    _quiet_until = None
    _last_drop_log_at = None
    _worker_process_started = False


# ---------------------------------------------------------------------------
# the celery seams
# ---------------------------------------------------------------------------

@worker_process_init.connect
def note_worker_process(**kwargs):
    """Marks this process as one that executes tasks.

    Celery fires this once per worker child process (and once in the solo
    and gevent pools), which makes it the only reliable answer to "am I a
    process whose task executions are worth measuring" - see the gate in
    ``collection_enabled``.
    """
    global _worker_process_started
    _worker_process_started = True


@before_task_publish.connect
def stamp_publish_time(sender=None, headers=None, **kwargs):
    """Puts the publish wall time onto the outgoing message.

    The stamp rides *with the message* to whichever worker executes it - no
    second broker round trip, no extra storage, and a retry's message is
    stamped again at its own re-publish (``Task.retry`` goes through the
    same publish path), which is what keeps an attempt's queue wait the wait
    of *that* attempt and not of the whole retry chain. The value is an
    epoch float and nothing else: no identity, no payload.

    Stamped in every publishing process - the web app, the workers' own
    fan-out and beat alike - which is why it is not gated on
    ``collection_enabled``; it touches no database.
    """
    if not _setting("CAPACITY_TELEMETRY_ENABLED", False):
        return
    if not isinstance(headers, dict):
        # protocol v1 messages carry no header dict; there is no safe
        # in-band place for the stamp and the wait stays unknown
        return
    try:
        headers[PUBLISH_STAMP_HEADER] = time.time()
    except Exception:  # a stamp that cannot be written must never cost a publish
        pass


@task_prerun.connect
def begin_attempt(sender=None, task_id=None, task=None, **kwargs):
    if not collection_enabled():
        return
    try:
        _begin_attempt(sender, task_id, task)
    except Exception as error:
        logger.debug("capacity telemetry: failed to begin an attempt: %s",
                     error)


@task_postrun.connect
def finish_attempt_on_postrun(sender=None, task_id=None, task=None, **kwargs):
    """The safety net of the finish: celery posts this on every execution end.

    The terminal outcome comes from ``task_success``/``task_failure``; when
    those ever stay silent (eager execution, unusual pool paths) postrun at
    least closes the attempt with a measured duration instead of leaving an
    open row, and it labels the attempt a success, which is all postrun can
    honestly say of a task that ran to its end.
    """
    if not collection_enabled():
        return
    try:
        _finish_attempt(task, AttemptOutcome.SUCCESS.value)
    except Exception as error:
        logger.debug("capacity telemetry: failed to finish an attempt: %s",
                     error)


@task_success.connect
def finish_attempt_on_success(sender=None, **kwargs):
    if not collection_enabled():
        return
    try:
        _finish_attempt(sender, AttemptOutcome.SUCCESS.value)
    except Exception as error:
        logger.debug("capacity telemetry: failed to close a success: %s",
                     error)


@task_failure.connect
def finish_attempt_on_failure(sender=None, **kwargs):
    if not collection_enabled():
        return
    try:
        _finish_attempt(sender, AttemptOutcome.FAILURE.value)
    except Exception as error:
        logger.debug("capacity telemetry: failed to close a failure: %s",
                     error)


@task_retry.connect
def finish_attempt_on_retry(sender=None, request=None, **kwargs):
    """Ends the *attempt* which asked for its retry.

    The retried attempt consumed real slot time and is done: its own row
    closes with outcome ``retry``. The next attempt rides a new message under
    the same task uuid with a raised attempt counter and is measured for
    itself - which is why retry chains sum per attempt instead of blurring
    into one long execution.
    """
    if not collection_enabled():
        return
    try:
        _finish_attempt(sender, AttemptOutcome.RETRY.value)
    except Exception as error:
        logger.debug("capacity telemetry: failed to close a retry: %s",
                     error)


@task_revoked.connect
def mark_attempt_revoked(sender=None, request=None, **kwargs):
    """Best effort on a revocation.

    Under the prefork pool the revoke is processed in the worker's *main*
    process while the attempt's buffer lives in a child, so this often finds
    nothing to close - the sweep of ``system.tasks`` is the authority for
    those attempts. Under pools without child processes (solo, threads,
    gevent) it closes the attempt truthfully here.
    """
    if not collection_enabled():
        return
    try:
        task_id = request if isinstance(request, str) else getattr(
            request, "id", None)
        if not task_id:
            return
        task_id = str(task_id)[:64]
        for (entry_task_id, _attempt_no), entry in _buffer.items():
            if entry_task_id == task_id and not entry.is_terminal:
                _mark_terminal(entry, AttemptOutcome.REVOKED.value)
    except Exception as error:
        logger.debug("capacity telemetry: failed to mark a revoke: %s",
                     error)


@worker_process_shutdown.connect
def flush_on_process_shutdown(**kwargs):
    """Writes what this process still holds before it goes away.

    Without it every graceful restart loses its buffered attempts; with it,
    a hard kill is the only loss the ``abandoned`` flag and the sweep speak
    about.
    """
    if not collection_enabled():
        return
    try:
        flush_attempts()
    except Exception as error:
        logger.debug("capacity telemetry: shutdown flush failed: %s", error)
