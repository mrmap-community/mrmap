"""Bounded records of what the deployment accumulated on its own.

The models of this app are the persisted side of the deployment's own
observability. ``CeleryTaskAttempt`` (#1330) is one row per *attempt* of a
Celery task - the measurement source the capacity snapshots of #1326 read;
everything which kept this file to a mere ``pass`` before was the note below,
which still holds for the post_migrate receivers of ``system/apps.py``.
"""

from django.db import models


class AttemptOutcome(models.TextChoices):
    """How one attempt of a task ended, as the worker signals reported it.

    The empty value means *no terminal event was seen yet*: either the attempt
    is still running when its process flushed its buffer, or the worker died
    before the end. An empty outcome is never counted as a finished execution
    (#1330) - the aggregation reads active seconds only from attempts with a
    terminal outcome.
    """

    SUCCESS = "success", "Success"
    FAILURE = "failure", "Failure"
    RETRY = "retry", "Retry"
    REVOKED = "revoked", "Revoked"


#: every outcome which closes an attempt; the empty outcome is deliberately
#: not in it - see ``AttemptOutcome``
TERMINAL_OUTCOMES = frozenset(
    value for value, _ in AttemptOutcome.choices)


class AttemptQuality(models.TextChoices):
    """Flags which say what an attempt's row is *not* proof of (#1330).

    A row only ever carries what a worker really signalled; these flags tell
    the reader where that was less than a complete observation, so an absent
    or partial number is labelled instead of invented:

    ``abandoned``
        The sweep closed an attempt which never reported an end within the
        grace window - a lost worker, a hard time limit or a killed process.
        The attempt consumed slot time nobody measured; it contributes to
        neither the occupied seconds nor the finished-attempt counts.
    ``redelivered``
        The same attempt started a second time in the observing worker - a
        duplicate delivery of one message. Its observations are one merged
        sample, not two counted executions.
    """

    ABANDONED = "abandoned", "Abandoned"
    REDELIVERED = "redelivered", "Redelivered"


class CeleryTaskAttempt(models.Model):
    """One measured attempt of one Celery task (#1330).

    The row is written by the telemetry collector of ``system/
    capacity_telemetry.py`` from the celery signals of the worker which ran
    the attempt, in bounded batches - never synchronously per task. It
    answers three durations which the epic #1324 insists on keeping apart:

    *   the *occupied worker slot seconds* are ``active_seconds``: what the
        attempt really ran inside a worker slot, remote HTTP waiting
        included, and nothing of the time the message spent in the broker;
    *   the *queue waiting* is ``started_at`` minus ``published_at``, readable
        only when the publish stamp rode along with the message;
    *   the *end-to-end elapsed* duration of the job behind the attempt is
        **not** answered here - the run tables (``HarvestingJob``, the
        ``*MonitoringRun``, the update jobs) and #693's durations own that
        class; this row only names its correlation keys (``root_id``,
        ``periodic_name``) so a reader can join them.

    Privacy is structural, not a filter: the model has no field which could
    hold an argument, a URL, a header value or a payload - the collector
    never reads those off the request and a column which could store them
    does not exist.

    ``task_id`` alone is not an attempt: celery's ``Task.retry`` re-publishes
    the task under the *same* uuid, so the attempt counter which the retry
    raises is what tells two attempts apart; a redelivered message of one
    attempt keeps both. Rows are written insert-only and the two partial
    unique constraints are the deduplication: one open row and one terminal
    row per attempt identity, no matter how often an event arrives twice.
    Aggregations sum only the terminal rows, so an attempt is counted at most
    once even when two workers run one redelivered message concurrently -
    the second finish is dropped, which under-counts and never double-counts.
    """

    task_id = models.CharField(max_length=64)
    attempt_no = models.PositiveIntegerField(default=0)

    task_name = models.CharField(max_length=255)
    queue = models.CharField(max_length=64, blank=True, default="")
    worker = models.CharField(max_length=255, blank=True, default="")

    root_id = models.CharField(max_length=64, blank=True, null=True)
    parent_id = models.CharField(max_length=64, blank=True, null=True)
    periodic_name = models.CharField(max_length=255, blank=True, null=True)

    published_at = models.DateTimeField(null=True, blank=True)
    started_at = models.DateTimeField()
    finished_at = models.DateTimeField(null=True, blank=True)
    active_seconds = models.FloatField(null=True, blank=True)
    #: ``started_at - published_at`` in seconds, kept as a number so the
    #: aggregates read broker waiting without interval arithmetic; None
    #: whenever the message carried no publish stamp (queue wait unknown)
    wait_seconds = models.FloatField(null=True, blank=True)

    outcome = models.CharField(
        max_length=16, blank=True, default="",
        choices=AttemptOutcome.choices)
    quality = models.JSONField(default=list, blank=True)

    recorded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            # the deduplication of the insert-only writes (#1330): an attempt
            # identity may have ONE open row (what a lost worker leaves
            # behind) and ONE terminal row (the counted execution), no matter
            # how often its events are flushed or arrive a second time
            models.UniqueConstraint(
                fields=("task_id", "attempt_no"),
                condition=models.Q(outcome=""),
                name="unique_open_celery_attempt"),
            models.UniqueConstraint(
                fields=("task_id", "attempt_no"),
                condition=~models.Q(outcome=""),
                name="unique_terminal_celery_attempt"),
        ]
        indexes = [
            # every question #1326 asks is a windowed one, and most are
            # windowed *per queue* - both start with the time bound
            models.Index(fields=("started_at",),
                         name="attempt_started_idx"),
            models.Index(fields=("queue", "started_at"),
                         name="attempt_queue_started_idx"),
        ]

    def __str__(self):
        # names the attempt and nothing else: no argument, no url, no
        # identity beyond the task uuid (#1330's privacy boundary)
        return f"{self.task_name}#{self.task_id}/{self.attempt_no}"

    @property
    def is_terminal(self):
        """Whether this attempt reported an end the aggregation may count."""
        return (self.outcome in TERMINAL_OUTCOMES
                and self.active_seconds is not None)
