"""What the runs a deployment made say about the schedule which makes them (#1325).

The estimator answers, for an existing or draft periodic monitoring, update
or harvesting setting, two things without writing anything: the schedule's
next occurrences and the **end-to-end** durations the comparable runs of the
same service and operation measured behind it. It is read-only: it uses the
run tables the deployment already keeps and invents no new model, task hook
or log ingestion (#1327 consumes the typed result as a code contract).

The three durations the issue of #1325 distinguishes are answered apart on
purpose:

- `ElapsedEstimate` is creation to terminal completion of a run. It includes
  every moment the run waited - for a worker, for the callback which closes
  a fan-out, for a remote service - and it is the duration a schedule has to
  be compared with. For monitoring the pair `date_created` to `date_done`
  answers it, which is elapsed time and **not** worker time. For harvesting
  the runs are measured the way #693 measures them (`harvest_durations()`
  reads the recorded creation and `done_at` of a run), for updates the
  verified equivalent pair `date_created` to `done_at`.
- `QueueWaitEstimate` would need an authoritative per-task pair of enqueue
  and actual start. The deployment records no such pair, so the MVP answers
  it unknown - never a subtraction of arbitrary job timestamps.
- `WorkerSlotEstimate` would need the execution durations of the individual
  tasks and attempts a run occupies a worker with, fan-out children,
  callbacks and retries included. These events are no durable, reliably
  attributable rows yet; #1330 owns recording them. Until then the answer
  is null with `unknown` - a parallel run's elapsed wall clock is never
  presented as slot occupancy, and the ~2.4s / ~0.6s live-rig guesses of the
  epic discussion are no measurements to reuse.

The MVP telemetry gap the phase-2 handoff has to close is minimal: per task
attempt one durable, attributable event pair (start, finish) carrying the
run it belongs to and its attempt number, including fan-out children and
chord callbacks. Nothing beyond that pair is needed to turn
`worker_slot_seconds` from null into a measured distribution in #1326.

Deterministic policy, stated because the acceptance criteria ask for it:

- the lookback window is `LOOKBACK_DAYS` days back from the answered moment,
  decided on the terminal completion of a run; very old observations leave
  the baseline entirely - the windowed median and p95 are only ever answered
  from inside the window, older comparable runs only keep feeding the
  #693-compatible average, which is labeled as an average and answered with
  the evidence `estimated_prior`, never as a p95 and never as a worker cost.
- a p95 is answered from at least `P95_MIN_SAMPLES` completed observations;
  fewer answer null with the `insufficient_samples` gap.
- percentiles are the nearest-rank of the sorted durations: the value at
  ``ceil(rank * n)`` of the ascending list, no interpolation.
- completed runs whose stored timestamps answer no non-negative duration (a
  completion before their creation - clock skew or a repaired row) are no
  observation; they are counted with the incomplete ones.
- failed and incomplete runs never enter the baseline; their counts are
  answered separately. The counts are not windowed - they say how often the
  operation went wrong, which no lookback would make fairer.
- a schedule is flagged as potentially overlapping by the rule #693 warns
  with (`schedule_is_tighter_than`) and only from a measured p50/p95; the
  flag always carries the qualifier that concurrency and lock behaviour is
  task-specific and was not verified against any guard.
"""
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from math import ceil
from zoneinfo import ZoneInfo

from django.core.exceptions import ValidationError
from django.db.models import (Avg, Count, DurationField, ExpressionWrapper,
                              F, Max, Q)
from django.utils.timezone import now
from django.utils.translation import gettext_lazy as _
from django_celery_beat.models import CrontabSchedule
from extras.scheduling import (next_run_expected_at, run_interval,
                               schedule_is_tighter_than)
from notify.enums import ProcessStatusEnum
from registry.enums.capacity import (EstimateGapEnum, EvidenceQualityEnum,
                                     RunOperationEnum)
from registry.enums.harvesting import HarvestingPhaseEnum
from registry.enums.update import UpdateJobStatusEnum
from registry.models.harvest import PeriodicHarvestingJob
from registry.models.monitoring import (CatalogueServiceMonitoringSetting,
                                        CatalogueServiceMonitoringRun,
                                        WebFeatureServiceMonitoringSetting,
                                        WebFeatureServiceMonitoringRun,
                                        WebMapServiceMonitoringSetting,
                                        WebMapServiceMonitoringRun)
from registry.models.service import (CatalogueService, WebFeatureService,
                                     WebMapService)
from registry.models.update import (CatalogueServiceUpdateJob,
                                    CatalogueServiceUpdateSetting,
                                    WebFeatureServiceUpdateJob,
                                    WebFeatureServiceUpdateSetting,
                                    WebMapServiceUpdateJob,
                                    WebMapServiceUpdateSetting)
from registry.querys.alerts import SERVICE_KIND_OF
from registry.querys.harvest_history import harvest_durations
from registry.querys.havesting import run_created_at

#: the days of history the measured median and p95 are answered from. A
#: weekly schedule fills the p95 minimum within this window, and a
#: deployment which changed its remote services can let a stale year age
#: out of the measured baseline by itself.
LOOKBACK_DAYS = 180

#: completed observations a p95 needs before it stops being a guess
P95_MIN_SAMPLES = 20

#: the qualifier which travels with every potential-overlap flag (#1325).
#: An elapsed which exceeds the next interval says a dispatch can land
#: while the run of the previous dispatch still works - whether the task
#: then overlaps its predecessor or a dispatch is skipped is decided by the
#: task's own concurrency and locking guards, which no estimator reads.
OVERLAP_QUALIFIER = _(
    "potential overlap or skipped dispatch: the measured elapsed time of "
    "completed runs exceeds the wait of the schedule until its next run. "
    "Whether runs really overlap or a dispatch is skipped is task-specific "
    "and depends on concurrency and locking guards which this estimate "
    "does not verify.")

#: what #1330 has to record before `worker_slot_seconds` can be measured:
#: the minimal observed telemetry gap, stated instead of an invented value.
WORKER_TELEMETRY_GAP = _(
    "no durable per-task worker events exist to sum: measuring worker slot "
    "occupancy needs a durable, reliably attributable start/finish event "
    "pair per task attempt - fan-out children and chord callbacks included "
    "- which the phase-2 instrumentation of #1330 will record")

#: why `queue_wait_seconds` answers nothing today: the deployment has no
#: authoritative enqueue-to-start pair per task to measure.
QUEUE_PAIR_GAP = _(
    "queue wait needs the recorded pair of task enqueue and actual task "
    "start; the deployment records neither, so no pair exists to measure")


@dataclass(frozen=True)
class ScheduleProposal:
    """A schedule as an administrator proposes it, without saving it (#1325).

    Args:
        enabled (bool): whether the proposed schedule dispatches
        crontab (str): the crontab as the screen writes it - five fields
            "minute hour day-of-month month day-of-week"
        timezone (str): the name of the timezone to run the crontab in; the
            timezone of the current schedule by default, UTC without one
    """

    enabled: bool = True
    crontab: str = None
    timezone: str = None


@dataclass(frozen=True)
class ScheduleAnswer:
    """The schedule side of an estimate, decided with canonical Celery semantics."""

    enabled: bool = False
    crontab: str = None
    next_run_expected_at: datetime = None
    run_interval_seconds: float = None
    gaps: tuple = ()


@dataclass(frozen=True)
class ElapsedEstimate:
    """End-to-end durations of completed comparable runs - never worker time.

    `median_seconds` and `p95_seconds` are measured inside the lookback
    window and answered only while the evidence allows it. `average_seconds`
    is the #693-compatible average over all completed comparable runs of any
    age: an average - never a p95 and never a worker cost.
    """

    evidence: str = EvidenceQualityEnum.UNKNOWN.value
    median_seconds: float = None
    p95_seconds: float = None
    average_seconds: float = None
    sample_count: int = 0
    p95_minimum_samples: int = P95_MIN_SAMPLES
    failed_count: int = 0
    incomplete_count: int = 0
    lookback_days: int = LOOKBACK_DAYS
    last_measurement_at: datetime = None
    gaps: tuple = ()


@dataclass(frozen=True)
class QueueWaitEstimate:
    """Enqueue to task start. Null unless an authoritative pair exists."""

    seconds: float = None
    evidence: str = EvidenceQualityEnum.UNKNOWN.value
    gap: str = EstimateGapEnum.QUEUE_PAIR_MISSING.value
    reason: str = QUEUE_PAIR_GAP


@dataclass(frozen=True)
class WorkerSlotEstimate:
    """Occupied worker seconds summed over tasks and attempts.

    Null with `unknown` until #1330 makes the task events durable; the
    elapsed time of a run is never answered here.
    """

    seconds: float = None
    evidence: str = EvidenceQualityEnum.UNKNOWN.value
    gap: str = EstimateGapEnum.WORKER_TELEMETRY_MISSING.value
    reason: str = WORKER_TELEMETRY_GAP


@dataclass(frozen=True)
class OverlapRisk:
    """Whether the schedule waits less than the measured elapsed time needs.

    `basis` names which elapsed observation was compared - the p95 or the
    median - so the qualifier is never read as a guarantee.
    """

    potential_overlap: bool = None
    basis: str = None
    interval_seconds: float = None
    qualifier: str = OVERLAP_QUALIFIER
    gaps: tuple = ()


@dataclass(frozen=True)
class PeriodicCapacityEstimate:
    """The answer of the estimator: one setting, one operation, no writes.

    `scope` carries the resource tags the caller asked about; the run
    history is kept per service, so the scope travels with the answer and
    never filters the observations.
    """

    operation: str = None
    service_kind: str = None
    service_id: str = None
    setting_id: int = None
    scope: tuple = ()
    schedule: ScheduleAnswer = field(default_factory=ScheduleAnswer)
    elapsed: ElapsedEstimate = field(default_factory=ElapsedEstimate)
    queue_wait: QueueWaitEstimate = field(default_factory=QueueWaitEstimate)
    worker_slot: WorkerSlotEstimate = field(default_factory=WorkerSlotEstimate)
    overlap: OverlapRisk = field(default_factory=OverlapRisk)


#: the setting model which schedules the operation of a kind of service
SETTING_MODEL_OF = {
    (WebMapService, RunOperationEnum.MONITORING):
        WebMapServiceMonitoringSetting,
    (WebFeatureService, RunOperationEnum.MONITORING):
        WebFeatureServiceMonitoringSetting,
    (CatalogueService, RunOperationEnum.MONITORING):
        CatalogueServiceMonitoringSetting,
    (WebMapService, RunOperationEnum.UPDATE):
        WebMapServiceUpdateSetting,
    (WebFeatureService, RunOperationEnum.UPDATE):
        WebFeatureServiceUpdateSetting,
    (CatalogueService, RunOperationEnum.UPDATE):
        CatalogueServiceUpdateSetting,
    (CatalogueService, RunOperationEnum.HARVEST):
        PeriodicHarvestingJob,
}

#: the run table which answers the comparable runs of an operation; the
#: harvesting runs come from `SERVICE_KIND_OF` itself
RUN_MODEL_OF = {
    RunOperationEnum.MONITORING: {
        WebMapService: WebMapServiceMonitoringRun,
        WebFeatureService: WebFeatureServiceMonitoringRun,
        CatalogueService: CatalogueServiceMonitoringRun,
    },
    RunOperationEnum.UPDATE: {
        WebMapService: WebMapServiceUpdateJob,
        WebFeatureService: WebFeatureServiceUpdateJob,
        CatalogueService: CatalogueServiceUpdateJob,
    },
}

#: a truthy stand-in for a crontab which is carried in memory and never
#: stored; `extras.scheduling` only asks whether the setting has a crontab
UNSAVED_CRONTAB_ID = -1


class _EffectiveSchedule:
    """A draft or proposed schedule, answering what `extras.scheduling` reads.

    `next_run_expected_at` and `run_interval` are the canonical decision of
    Celery's schedule semantics, which #1325 reuses, and they read exactly
    these attributes off a `PeriodicTask`. A proposal or a draft is handed
    to them through this stand-in, which carries the proposed crontab - an
    unsaved `CrontabSchedule`, whose `schedule` property needs no database -
    and the timing baseline of the real setting whenever it has one.
    """

    def __init__(self, setting, crontab, enabled, current_time):
        self.crontab = crontab
        if crontab is None:
            self.crontab_id = None
        elif crontab.pk is not None:
            self.crontab_id = crontab.pk
        else:
            self.crontab_id = UNSAVED_CRONTAB_ID
        self.enabled = enabled
        self.one_off = bool(getattr(setting, 'one_off', False))
        self.total_run_count = getattr(setting, 'total_run_count', 0) or 0
        self.last_run_at = getattr(setting, 'last_run_at', None)
        self.date_changed = (getattr(setting, 'date_changed', None)
                             if setting is not None else current_time)
        self.start_time = getattr(setting, 'start_time', None)
        self.expires = getattr(setting, 'expires', None)


@dataclass(frozen=True)
class _RunHistory:
    """The raw answer of the run tables of one service and operation."""

    durations: tuple = ()   # measurable durations of completed runs inside the window
    unmeasurable: int = 0   # completed runs whose timestamps measure no duration
    average: timedelta = None   # #693-compatible average over all completed runs
    last_done: datetime = None  # newest terminal completion, any age
    completed_total: int = 0    # completed comparable runs, any age
    failed: int = 0             # runs which ended failing, any age
    incomplete: int = 0         # runs which did not reach a terminal state


def _seconds(duration):
    """The duration in seconds, or None for a duration which answers nothing."""
    if duration is None:
        return None
    return duration.total_seconds()


def _percentile(sorted_durations, rank):
    """The nearest-rank percentile of ascending durations, no interpolation."""
    return sorted_durations[max(ceil(rank * len(sorted_durations)) - 1, 0)]


def _resolve_service_kind(service_kind):
    """The `SERVICE_KIND_OF` entry and service model for a class or a name."""
    if isinstance(service_kind, str):
        for model in SERVICE_KIND_OF:
            if model.__name__ == service_kind:
                return SERVICE_KIND_OF[model], model
        return None, None
    return SERVICE_KIND_OF.get(service_kind), service_kind


def _degraded(operation, service_kind, service_id, setting, scope, gap):
    """An estimate which answers gaps and nothing else, without raising."""
    return PeriodicCapacityEstimate(
        operation=str(operation), service_kind=str(service_kind),
        service_id=str(service_id), setting_id=getattr(setting, 'pk', None),
        scope=tuple(scope),
        schedule=ScheduleAnswer(gaps=(gap,)),
        elapsed=ElapsedEstimate(gaps=(gap,)))


def _schedule(setting, proposal, current_time):
    """The schedule side of the answer, with the effective schedule behind it.

    Returns:
        tuple: the `ScheduleAnswer` and the setting whose interval the
            overlap risk is decided from - None when no schedule answers
    """
    gaps = []
    enabled = False
    crontab = None
    if proposal is not None:
        parsed = _parse_proposal(proposal, setting)
        if parsed is None:
            gaps.append(EstimateGapEnum.INVALID_PROPOSAL.value)
            return ScheduleAnswer(gaps=tuple(gaps)), None
        crontab, enabled = parsed
    elif setting is not None:
        enabled = bool(setting.enabled)
        crontab = setting.crontab
    else:
        gaps.append(EstimateGapEnum.NOT_CONFIGURED.value)

    if crontab is None:
        if EstimateGapEnum.NOT_CONFIGURED.value not in gaps:
            gaps.append(EstimateGapEnum.NO_CRONTAB.value)
        return ScheduleAnswer(enabled=enabled, gaps=tuple(gaps)), None

    effective = setting if (
        setting is not None and proposal is None and setting.pk is not None
        and setting.crontab_id is not None) else _EffectiveSchedule(
            setting, crontab, enabled, current_time)

    if not enabled:
        gaps.append(EstimateGapEnum.SCHEDULE_DISABLED.value)
    elif effective.one_off and effective.total_run_count > 0:
        gaps.append(EstimateGapEnum.ONE_OFF_RAN.value)

    expected_at = next_run_expected_at(effective)
    interval = run_interval(effective)
    return ScheduleAnswer(
        enabled=enabled, crontab=str(crontab),
        next_run_expected_at=expected_at,
        run_interval_seconds=_seconds(interval), gaps=tuple(gaps)), effective


def _parse_proposal(proposal, setting):
    """The unsaved `CrontabSchedule` of a proposal, or None when unparsable.

    The crontab string is taken the way the api of a schedule takes it: the
    five fields "minute hour day-of-month month day-of-week". The timezone
    falls back to the one of the setting's current crontab, then to UTC. A
    proposal without a crontab keeps the fields of the current schedule, so
    it can propose only a new timezone or a changed `enabled`.
    """
    if proposal.crontab:
        parts = proposal.crontab.strip().split()
        if len(parts) != 5:
            return None
        minute, hour, day_of_month, month_of_year, day_of_week = parts
    elif setting is not None and setting.crontab is not None:
        current = setting.crontab
        minute, hour = current.minute, current.hour
        day_of_month, month_of_year = current.day_of_month, current.month_of_year
        day_of_week = current.day_of_week
    else:
        return None
    timezone_name = proposal.timezone
    if timezone_name is None:
        timezone_name = (str(setting.crontab.timezone)
                         if setting is not None and setting.crontab is not None
                         else 'UTC')
    try:
        timezone = ZoneInfo(timezone_name)
    except Exception:
        return None
    crontab = CrontabSchedule(
        minute=minute, hour=hour, day_of_week=day_of_week,
        day_of_month=day_of_month, month_of_year=month_of_year,
        timezone=timezone)
    try:
        # a crontab whose fields Celery rejects parses no schedule - the
        # proposal is then answered degraded, never half accepted
        crontab.schedule
    except Exception:
        return None
    return crontab, bool(proposal.enabled)


def _monitoring_history(kind, setting, service_id, window_start):
    """What the monitoring runs of the service answer, in bounded queries.

    A monitoring run reached its end when the background process which
    reports it reported completion: the `finish_run` task writes `date_done`
    at exactly that moment. Runs whose probes failed are the failed ones -
    the success annotation answers them - because a failing probe made the
    run finish with something to say, while a run whose process still runs,
    failed hard or lost its process never reached that terminal completion.
    """
    run_model = RUN_MODEL_OF[RunOperationEnum.MONITORING][kind.service]
    scope = (Q(setting_id=setting.pk)
             if setting is not None and setting.pk
             else Q(setting__service_id=service_id))
    elapsed = ExpressionWrapper(
        F('date_done') - F('date_created'), output_field=DurationField())
    completed = Q(background_process__status=ProcessStatusEnum.COMPLETED,
                  date_done__isnull=False)
    succeeded = completed & Q(success=True)
    failed = (Q(background_process__status=ProcessStatusEnum.FAILED)
              | (Q(background_process__status=ProcessStatusEnum.COMPLETED)
                 & Q(success=False)))
    not_reached = (
        Q(background_process__isnull=True)
        | Q(background_process__status__in=[
            ProcessStatusEnum.PENDING, ProcessStatusEnum.RUNNING,
            ProcessStatusEnum.ABORTED])
        | Q(background_process__status=ProcessStatusEnum.COMPLETED,
            date_done__isnull=True, success=True))
    base = run_model.objects.with_is_successful().filter(scope)
    durations, unmeasurable = _split_measurable(
        base.filter(succeeded, date_done__gte=window_start)
        .annotate(elapsed=elapsed).values_list('elapsed', flat=True))
    aggregate = base.filter(succeeded).annotate(elapsed=elapsed).filter(
        elapsed__gte=timedelta(0)).aggregate(
            average=Avg('elapsed'), last_done=Max('date_done'),
            completed_total=Count('pk'))
    return _RunHistory(
        durations=durations, unmeasurable=unmeasurable,
        average=aggregate['average'], last_done=aggregate['last_done'],
        completed_total=aggregate['completed_total'],
        failed=base.filter(failed).count(),
        incomplete=base.filter(not_reached).count())


def _update_history(kind, setting, service_id, window_start):
    """What the update jobs of the service answer.

    The verified pair of an update is `date_created` to `done_at`; a job
    which waits for a review is not finished until a decision ends it, so
    only the terminal statuses - updated or no update needed - together with
    a `done_at` answer a completed observation.
    """
    job_model = RUN_MODEL_OF[RunOperationEnum.UPDATE][kind.service]
    base = job_model.objects.filter(service_id=service_id)
    elapsed = ExpressionWrapper(
        F('done_at') - F('date_created'), output_field=DurationField())
    succeeded = Q(done_at__isnull=False, status__in=[
        UpdateJobStatusEnum.UPDATED.value,
        UpdateJobStatusEnum.NO_UPDATE_NEEDED.value])
    durations, unmeasurable = _split_measurable(
        base.filter(succeeded, done_at__gte=window_start)
        .annotate(elapsed=elapsed).values_list('elapsed', flat=True))
    aggregate = base.filter(succeeded).annotate(elapsed=elapsed).filter(
        elapsed__gte=timedelta(0)).aggregate(
            average=Avg('elapsed'), last_done=Max('done_at'),
            completed_total=Count('pk'))
    return _RunHistory(
        durations=durations, unmeasurable=unmeasurable,
        average=aggregate['average'], last_done=aggregate['last_done'],
        completed_total=aggregate['completed_total'],
        failed=base.filter(
            status=UpdateJobStatusEnum.ERROR.value).count(),
        incomplete=base.filter(done_at__isnull=True).exclude(
            status=UpdateJobStatusEnum.ERROR.value).count())


def _harvest_history(kind, setting, service_id, window_start):
    """What the harvesting runs of the catalogue answer.

    Completed runs are measured exactly the way #693 measures them - the
    `harvest_durations()` average stays the source of the average - and the
    windowed durations read the same pair: the recorded creation, with its
    change-log fallback, to `done_at`.
    """
    job_model = kind.harvesting_job
    base = job_model.objects.filter(service_id=service_id)
    completed = Q(phase=HarvestingPhaseEnum.COMPLETED.value,
                  done_at__isnull=False)
    durations, unmeasurable = _split_measurable(
        base.filter(completed, done_at__gte=window_start)
        .annotate(elapsed=ExpressionWrapper(
            F('done_at') - run_created_at(),
            output_field=DurationField())).values_list('elapsed', flat=True))
    durations_row = harvest_durations([service_id])
    # the row is keyed by the service id as the database answers it, which
    # for a UUID primary key is not necessarily the object the caller named
    key = next((k for k in durations_row
                if str(k) == str(service_id)), None)
    estimate = durations_row[key] if key else {}
    return _RunHistory(
        durations=durations, unmeasurable=unmeasurable,
        average=estimate.get('average'), last_done=estimate.get('last_done'),
        completed_total=base.filter(completed).count(),
        failed=base.filter(phase__in=[
            HarvestingPhaseEnum.ABORTED.value,
            HarvestingPhaseEnum.ABORT.value]).count(),
        incomplete=base.exclude(phase__in=[
            HarvestingPhaseEnum.COMPLETED.value,
            HarvestingPhaseEnum.ABORTED.value,
            HarvestingPhaseEnum.ABORT.value]).count())


def _split_measurable(measured):
    """The durations which are observations, apart from the timestamps which are not.

    A stored completion before the stored creation is no observation - the
    deterministic policy for the skewed row of a repaired deployment.
    """
    durations, unmeasurable = [], 0
    for duration in measured:
        if duration is None or duration < timedelta(0):
            unmeasurable += 1
        else:
            durations.append(duration)
    return tuple(durations), unmeasurable


def _elapsed_estimate(history):
    """The typed elapsed metric from the raw answer of the run tables."""
    gaps = []
    durations = sorted(history.durations)
    median = p95 = None
    if durations:
        evidence = EvidenceQualityEnum.MEASURED_ELAPSED.value
        median = _percentile(durations, 0.5)
        if len(durations) >= P95_MIN_SAMPLES:
            p95 = _percentile(durations, 0.95)
        else:
            gaps.append(EstimateGapEnum.INSUFFICIENT_SAMPLES.value)
    elif history.average is not None:
        # comparable runs exist but all measurable ones finished outside the
        # window: the #693 average over them stays answerable as a prior -
        # the windowed percentiles are not measured and answer nothing
        evidence = EvidenceQualityEnum.ESTIMATED_PRIOR.value
        gaps.append(EstimateGapEnum.OUTSIDE_LOOKBACK.value)
    else:
        evidence = EvidenceQualityEnum.UNKNOWN.value
        if not history.completed_total:
            gaps.append(EstimateGapEnum.NO_COMPLETED_RUNS.value)
    if not durations and history.unmeasurable:
        gaps.append(EstimateGapEnum.MISSING_TIMESTAMPS.value)
    return ElapsedEstimate(
        evidence=evidence,
        median_seconds=_seconds(median),
        p95_seconds=_seconds(p95),
        average_seconds=_seconds(history.average),
        sample_count=len(durations),
        failed_count=history.failed,
        # a completed run which measures no duration is counted with the
        # runs which did not finish: both answer no elapsed to compare with
        incomplete_count=history.incomplete + history.unmeasurable,
        last_measurement_at=history.last_done,
        gaps=tuple(gaps))


def _overlap(effective, schedule, elapsed):
    """The potential overlap of the schedule with the measured elapsed time.

    Decided by `schedule_is_tighter_than` - the same rule #693 warns with -
    and only from a measured p50/p95: an average or a prior is never
    silently compared here, and the answer is a flag with a qualifier, never
    an asserted overlap guarantee.
    """
    if effective is None or schedule.run_interval_seconds is None:
        return OverlapRisk(gaps=schedule.gaps)
    if elapsed.evidence != EvidenceQualityEnum.MEASURED_ELAPSED.value:
        # the gaps of the elapsed metric are the reasons no overlap can be
        # decided: they travel to the flag instead of a guessed answer
        return OverlapRisk(
            interval_seconds=schedule.run_interval_seconds,
            gaps=elapsed.gaps)
    if elapsed.p95_seconds is not None:
        basis, compared = 'p95', timedelta(seconds=elapsed.p95_seconds)
    else:
        basis, compared = 'median', timedelta(seconds=elapsed.median_seconds)
    return OverlapRisk(
        potential_overlap=schedule_is_tighter_than(effective, compared),
        basis=basis,
        interval_seconds=schedule.run_interval_seconds)


def periodic_capacity_estimate(service_kind, service_id, operation,
                               setting=None, proposal=None, scope=(),
                               at=None):
    """What the schedule and the runs behind it answer for one service (#1325).

    Read-only: the estimator reads the schedule of the setting and the run
    tables of the service, answers the typed contract and writes nothing. An
    unknown service, an operation whose kind does not run, a setting which
    does not belong to the pair and an unparsable proposal are answered as
    degraded estimates with their gap - never as an exception and never as a
    zero-cost schedule.

    Args:
        service_kind: the service model or its name, e.g. `WebMapService`
            or "WebMapService"
        service_id: the primary key of the service
        operation: `RunOperationEnum` or its value - monitoring, update, harvest
        setting: the current setting, saved or draft, which schedules the
            operation; None asks from the proposal alone
        proposal: a `ScheduleProposal` answered for instead of the saved
            values of the setting
        scope: resource tags the caller asks about; they travel with the
            answer, the run history is kept per service
        at: the moment to answer from, now by default

    Returns:
        PeriodicCapacityEstimate: the typed answer for the pair of service
            and operation, with elapsed time, queue wait and worker slot
            time answered apart by their own evidence quality
    """
    try:
        operation = RunOperationEnum(operation)
    except ValueError:
        return _degraded(operation, service_kind, service_id, setting,
                         scope, EstimateGapEnum.UNSUPPORTED_OPERATION.value)
    current_time = at or now()
    window_start = current_time - timedelta(days=LOOKBACK_DAYS)
    kind, model = _resolve_service_kind(service_kind)
    if kind is None:
        return _degraded(operation, service_kind, service_id, setting, scope,
                         EstimateGapEnum.UNKNOWN_SERVICE.value)

    try:
        service_exists = kind.service.objects.filter(pk=service_id).exists()
    except (ValidationError, ValueError, TypeError):
        service_exists = False
    if not service_exists:
        return _degraded(operation, service_kind, service_id, setting,
                         scope, EstimateGapEnum.UNKNOWN_SERVICE.value)

    if setting is not None:
        expected = SETTING_MODEL_OF.get((model, operation))
        belongs = (type(setting) is expected
                   and str(getattr(setting, 'service_id', None))
                   == str(service_id))
        if not belongs:
            return _degraded(operation, model.__name__, service_id, setting,
                             scope, EstimateGapEnum.INVALID_SETTING.value)

    schedule, effective = _schedule(setting, proposal, current_time)
    if operation is RunOperationEnum.HARVEST:
        if kind.harvesting_job is None:
            return _degraded(operation, model.__name__, service_id, setting,
                             scope,
                             EstimateGapEnum.UNSUPPORTED_OPERATION.value)
        history = _harvest_history(kind, setting, service_id, window_start)
    elif model in RUN_MODEL_OF[operation]:
        history = (_monitoring_history if operation is RunOperationEnum.MONITORING
                   else _update_history)(kind, setting, service_id, window_start)
    else:
        return _degraded(operation, model.__name__, service_id, setting,
                         scope, EstimateGapEnum.UNSUPPORTED_OPERATION.value)

    elapsed = _elapsed_estimate(history)
    return PeriodicCapacityEstimate(
        operation=str(operation), service_kind=model.__name__,
        service_id=str(service_id),
        setting_id=getattr(setting, 'pk', None), scope=tuple(scope),
        schedule=schedule, elapsed=elapsed,
        overlap=_overlap(effective, schedule, elapsed))
