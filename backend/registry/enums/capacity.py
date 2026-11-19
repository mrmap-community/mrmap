"""The typed vocabulary of the periodic capacity estimator (#1325).

The estimator answers what the runs a deployment already made say about the
schedule which makes them. Its contract is that three durations which share
the word "duration" but never share a meaning are kept apart by their type:

- the **elapsed** time of a run: creation to terminal completion, including
  every moment the run waited for a worker, for a callback of a fan-out or for
  a remote service. This is what `harvest_durations()` (#693) measures and
  what a schedule has to be compared with.
- the **queue wait** of a task: enqueue to actual start. Only an
  authoritative per-task pair of these moments answers it - job timestamps
  of different kinds are not such a pair.
- the **worker slot** time: the execution durations of the individual tasks
  and attempts a run is made of, summed. A run whose wall clock elapsed is
  four hours may occupy a worker for two seconds of probing and two seconds
  of scheduling, because it waited hours before its probe fired.

The quality of the evidence behind a number is answered by
`EvidenceQualityEnum` together with the number, so a consumer cannot mistake
an estimate for a measurement. `EstimateGapEnum` names, machine-readable,
why a metric answers nothing - an unavailable metric is a stated gap and
never a zero-cost schedule.
"""
from django.db.models.enums import TextChoices
from django.utils.translation import gettext_lazy as _


class RunOperationEnum(TextChoices):
    """Which periodic operation a schedule and its runs stand for."""

    MONITORING = "monitoring", _("monitoring")
    UPDATE = "update", _("update")
    HARVEST = "harvest", _("harvest")


class EvidenceQualityEnum(TextChoices):
    """How well the number behind an estimate is underpinned (#1325).

    The value names the kind of evidence, not its size. `MEASURED_ELAPSED`
    answers an end-to-end duration measured by the completed runs within the
    lookback window; `MEASURED_WORKER` is reserved for the real task worker
    time the phase-2 instrumentation of #1330 will make available - the MVP
    never answers it. `ESTIMATED_PRIOR` is a value derived from comparable
    observations which all lie outside the lookback window: a prior, not a
    current measurement. `UNKNOWN` goes with a null number and a reason; it
    is never a zero-cost schedule.
    """

    MEASURED_ELAPSED = "measured_elapsed", _("measured elapsed time")
    MEASURED_WORKER = "measured_worker", _("measured worker time")
    ESTIMATED_PRIOR = "estimated_prior", _("estimated from older observations")
    UNKNOWN = "unknown", _("unknown")


class EstimateGapEnum(TextChoices):
    """Why a capacity metric answers nothing, in machine-readable terms.

    The label is the human-readable reason the issue of #1325 asks for; the
    value is what a consumer such as #1327 matches on.
    """

    NOT_CONFIGURED = "not_configured", _(
        "no setting and no schedule proposal was answered to the estimator")
    NO_CRONTAB = "no_crontab", _(
        "the setting has no crontab schedule configured")
    SCHEDULE_DISABLED = "schedule_disabled", _(
        "the schedule is disabled and dispatches no run")
    ONE_OFF_RAN = "one_off_ran", _(
        "the one-off schedule already ran and will not fire again")
    NO_COMPLETED_RUNS = "no_completed_runs", _(
        "no comparable run of this service has finished successfully")
    INSUFFICIENT_SAMPLES = "insufficient_samples", _(
        "too few completed runs to answer a p95 without guessing")
    OUTSIDE_LOOKBACK = "outside_lookback", _(
        "the completed runs are all older than the observation window")
    MISSING_TIMESTAMPS = "missing_timestamps", _(
        "the completed runs of the window answer no measurable duration")
    UNKNOWN_SERVICE = "unknown_service", _(
        "no service of this kind answers under this id")
    UNSUPPORTED_OPERATION = "unsupported_operation", _(
        "this kind of service has no runs of this periodic operation")
    INVALID_SETTING = "invalid_setting", _(
        "the answered setting is not the setting of this service and operation")
    INVALID_PROPOSAL = "invalid_proposal", _(
        "the proposed crontab or timezone cannot be parsed")
    QUEUE_PAIR_MISSING = "queue_pair_missing", _(
        "no authoritative enqueue-to-start pair is recorded per task")
    WORKER_TELEMETRY_MISSING = "worker_telemetry_missing", _(
        "no durable per-task worker events are recorded to attribute "
        "a run's slot occupancy to")


class SuggestionGapEnum(TextChoices):
    """Why the cadence suggestions of #1328 answer nothing, machine readable.

    A refusal is the honest answer of the suggestion engine: it never
    invents an "empty-looking" minute when the cadence cannot be preserved
    or the deployment capacity was not verified. The label is the reason an
    administrator reads; the value is what a screen matches on.
    """

    NOT_PERIODIC = "not_periodic", _(
        "the answered schedule is disabled, one-off or carries no crontab: "
        "there is no periodic cadence whose alternative could be suggested")
    SCHEDULE_ENDED = "schedule_end_before_horizon", _(
        "the schedule ends before the evaluated horizon begins: nothing is "
        "scheduled left to re-time")
    CADENCE_NO_SPACE = "cadence_no_candidate_space", _(
        "the minute field of the schedule leaves no cadence-preserving "
        "minute shift to evaluate")
    CADENCE_UNVERIFIABLE = "cadence_not_verifiable", _(
        "no alternative fired the same number of times as the schedule "
        "within the evaluated horizon, so no cadence-preserving alternative "
        "could be verified")
    CAPACITY_UNVERIFIED = "capacity_unverified", _(
        "the deployment capacity snapshot answers no verified cost and "
        "worker topology for the queue of this schedule: no reliable "
        "capacity-based suggestion")
    NO_MEASURED_IMPROVEMENT = "no_measured_improvement", _(
        "no cadence-preserving alternative measured a lower expected queue "
        "occupancy within the evaluated horizon")
