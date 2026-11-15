"""Cadence-preserving schedule alternatives from verified capacity data (#1328).

When the requested firing window of a periodic schedule sits on a heavily
loaded queue, an administrator deserves **entire valid alternative crontab
schedules** rather than an empty-looking single minute: an alternative that
keeps the originally desired execution frequency, timezone and allowed
window, and leaves the decision - and the save - entirely with the caller.

The honesty rules are the module:

*   **Same cadence or no suggestion.** Only the minute field is shifted;
    the hour, day-of-month, month and day-of-week fields - the whole day
    match of the schedule - carry over unchanged. Every candidate is then
    *verified by actual occurrences*: original and candidate are walked over
    one identical bounded dated horizon through the canonical Beat stepping
    (`system.capacity_demand.walk_crontab`, the same walk the capacity
    snapshot of #1326 counts saved rows with), and a candidate may fire
    exactly as often as the schedule within that horizon or it is no
    candidate. A one-off firing at another minute is never offered -
    recommending "14:37 once" instead of `*/30` silently changes the
    cadence, which is exactly what the issue forbids; one-off, disabled,
    expired or crontab-less schedules are refused as such.
*   **Documented horizon.** The evaluated horizon is the whole local days
    after the answered moment in the schedule's own timezone - seven days
    by default - because counting whole days is what makes the comparison
    of two minute fields fair at the window edges; a DST change shifts both
    schedules the same way and the walk counts the instants Beat will
    really dispatch. A schedule that fires nowhere in those days is
    re-evaluated over a documented longer horizon (by default four years,
    so monthly and leap-year patterns get a real occurrence to count); if
    neither schedule fires even there the cadence stays unverifiable and
    the answer is a refusal, not a claim.
*   **Verified capacity or no suggestion.** A candidate is ranked only by
    the *expected worker-seconds* of the snapshot histograms - the per
    firing costs measured by #1330 - and only while the deployment snapshot
    of #1326 answers the queue of this schedule with a comparable rho:
    topology observed, queue not degraded, cost coverage complete, terminal
    attempt samples present. A task-count histogram is never read as
    available capacity; without the measured costs the answer is the
    stated refusal "no reliable capacity-based suggestion". The snapshot is
    the reusable, materialized one - the candidate search never scans the
    43k schedule rows, never per candidate and not once per request.
*   **Advisory, never a guarantee.** A suggestion names no free slot and
    no first-start time; a lower expected occupancy is a measured
    preference, not a promise, and nothing here saves or re-registers a
    schedule. Only an explicit user action applies a suggestion, and the
    screen re-evaluates it through the full draft preview of #1327.

Same-service coincidences are deliberately not warned about beyond the
measured #693 rule (`schedule_tighter_than_elapsed`, carried by the
estimator with its qualifier): no verified DB lock or concurrency guard
makes two schedules of one service contend on wall-clock coincidence, and
#1273 is a `CrontabSchedule` post_migrate bug - it is no row-lock evidence.
The candidate search reads no other service's schedule at all, so a
suggestion cannot reveal a protected neighbouring service either.
"""
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from logging import Logger

from django.conf import settings
from django.utils.timezone import now
from django.utils.translation import gettext_lazy as _
from django_celery_beat.models import CrontabSchedule
from registry.enums.capacity import EstimateGapEnum, SuggestionGapEnum
from registry.querys.capacity import DraftSchedule, parse_proposal
from MrMap.celery import app
from system import capacity_demand, capacity_topology
from system.capacity_snapshot import get_capacity_snapshot

logger: Logger = getattr(settings, 'ROOT_LOGGER')

#: the whole local days after the answered moment the cadence is evaluated
#: over - the "next seven days" the issue names as the bounded horizon
DEFAULT_HORIZON_DAYS = 7

#: the documented longer horizon for patterns which fire nowhere in the
#: default one: 1461 days are four full years including a leap day, so a
#: monthly, a year-day or a 29-February schedule gets real occurrences to
#: compare by the time the horizon ends
DEFAULT_LONG_HORIZON_DAYS = 1461

#: the occurrence budget of one bounded walk; the densest crontab there is
#: (every minute) stays far below it over the default horizon, and a walk
#: which still hits it ends truncated - a partial count is treated as no
#: count, never as a verified cadence
DEFAULT_MAX_OCCURRENCES = 20_000

#: how many alternatives the answer may carry at most
DEFAULT_MAX_SUGGESTIONS = 3

#: the minute offsets a candidate shifts by - primes, none of which is a
#: divisor of a common stepping (*/5, */10, */12, */15, */20, */30 all
#: move to a genuinely different minute set)
MINUTE_OFFSETS = (5, 7, 11, 13, 17, 19, 23, 29, 31, 37, 41, 43, 47, 53)

#: the gaps of the answered schedule after which no periodic cadence is
#: left whose alternative could be suggested at all
_BLOCKING_GAPS = frozenset((
    EstimateGapEnum.NOT_CONFIGURED.value,
    EstimateGapEnum.NO_CRONTAB.value,
    EstimateGapEnum.SCHEDULE_DISABLED.value,
    EstimateGapEnum.ONE_OFF_RAN.value,
    EstimateGapEnum.INVALID_PROPOSAL.value))

#: the wording a suggestion carries: every number in it is stated together
#: with its evidence, and it claims neither a free slot nor a start time
SUGGESTION_REASON = _(
    'This alternative keeps the %(count)d firings the schedule still '
    'promises within the evaluated %(horizon)d-day horizon and, per the '
    'measured costs of the "%(queue)s" queue, expects %(expected)s worker-'
    'seconds of occupancy in their windows against %(original)s for the '
    'current minute field (%(samples)s measured terminal task samples). '
    'This is a measured preference over verified data, not a guarantee: '
    'it names no free slot and no first-start time.')


def _setting(name, default):
    return int(getattr(settings, name, default))


def _horizon_days():
    return max(1, _setting('SCHEDULING_SUGGESTIONS_HORIZON_DAYS',
                           DEFAULT_HORIZON_DAYS))


def _long_horizon_days():
    return max(_horizon_days() + 1,
               _setting('SCHEDULING_SUGGESTIONS_LONG_HORIZON_DAYS',
                        DEFAULT_LONG_HORIZON_DAYS))


def _max_occurrences():
    return max(1, _setting('SCHEDULING_SUGGESTIONS_MAX_OCCURRENCES',
                           DEFAULT_MAX_OCCURRENCES))


def _max_suggestions():
    return max(1, _setting('SCHEDULING_SUGGESTIONS_MAX',
                           DEFAULT_MAX_SUGGESTIONS))


@dataclass(frozen=True)
class CadenceSuggestion:
    """One entire alternative crontab which keeps the answered cadence.

    Args:
        crontab (str): the five fields "minute hour day-of-month month
            day-of-week" of the alternative - the schedule fields beside the
            minute field are the answered ones unchanged
        timezone (str): the name of the zone the crontab runs in - the
            answered schedule's own, a suggestion never moves the zone
        horizon_days (int): the whole local days the cadence was verified over
        horizon_start/horizon_end (datetime): the dated window of that check
        firing_count (int): the firings both schedules count inside it -
            verified equal by the canonical walk
        queue (str): the queue whose measured occupancy decided the ranking
        original_worker_seconds (float): expected occupancy of the answered
            schedule's firings inside the snapshot evidence window
        expected_worker_seconds (float): the same for this alternative
        sample_count (int): terminal attempt samples the costs rest on
        cost_coverage (float): share of the queue's horizon demand that was
            measured - 1 whenever a suggestion is answered at all
        snapshot_at (datetime): the moment the capacity evidence was observed
        reason (str): the explained preference, advisory wording
    """

    crontab: str = None
    timezone: str = None
    horizon_days: int = None
    horizon_start: datetime = None
    horizon_end: datetime = None
    firing_count: int = None
    queue: str = None
    original_worker_seconds: float = None
    expected_worker_seconds: float = None
    sample_count: int = 0
    cost_coverage: float = None
    snapshot_at: datetime = None
    reason: str = None


@dataclass(frozen=True)
class SuggestionAnswer:
    """The engine's answer: alternatives or the stated reason for none.

    `reason_code` is the stable `SuggestionGapEnum` value; `reason` carries
    its readable label plus, where it helps, the missing term in observed
    words. `horizon_days` names the evaluated horizon even for a refusal,
    so the documented horizon of the check travels with the answer.
    """

    suggestions: tuple = ()
    reason_code: str = None
    reason: str = None
    horizon_days: int = None


def _refuse(code, horizon_days=None, detail=None):
    """The refusal of a suggestion set: the gap label, never a free minute."""
    label = str(SuggestionGapEnum(code).label)
    return SuggestionAnswer(
        reason_code=code,
        reason=f'{label} {detail}' if detail else label,
        horizon_days=horizon_days)


def _as_moment(value):
    """The snapshot moment as a datetime - the cache may answer ISO text."""
    if value is None or isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


def _window(first_day, horizon_days, tz, start_time, expires):
    """The dated window of whole local days, as exclusive/inclusive bounds.

    Both bounds sit one microsecond outside the midnight-to-midnight span so
    the walk counts the whole first and the whole last day for *both*
    schedules; `start_time` and `expires` clamp the window exactly the way
    Beat's dispatch windows do. The walk is strictly after `lower`, which is
    the rule `extras.scheduling.next_run_occurrences` of the same preview
    answer follows for a schedule's baseline: a `start_time` landing on the
    answered minute costs the original that one firing at the bound, and no
    shifted minute can win it back - the engine then refuses rather than
    suggesting a schedule which fires once more than the answered one.
    """
    lower = datetime.combine(first_day, time.min, tzinfo=tz) \
        - timedelta(microseconds=1)
    upper = datetime.combine(
        first_day + timedelta(days=horizon_days), time.min, tzinfo=tz) \
        - timedelta(microseconds=1)
    if start_time is not None:
        lower = max(lower, start_time)
    if expires is not None:
        upper = min(upper, expires - timedelta(microseconds=1))
    return lower, upper


def _count(crontab, lower, upper, budget):
    """The instants of the window, or None when Celery answers no walk."""
    try:
        return capacity_demand.walk_crontab(crontab, lower, upper, budget)
    except Exception as error:
        # a definition Celery cannot step at all (the day-of-week "7" the
        # snapshot also counts unreadable) is no cadence to compare - the
        # walk raising is the answer, and it stays out of the response
        logger.debug('suggestions: crontab cannot be walked: %s', error)
        return None, True


def _answered_crontab(setting, proposal):
    """The crontab of the answered schedule - parsed or the setting's own.

    Returns:
        tuple: ``(crontab, enabled)`` or ``(None, None)`` when the draft
            answers no schedule Celery could step at all
    """
    if proposal is not None:
        parsed = parse_proposal(proposal, setting)
        if parsed is None:
            return None, None
        return parsed
    if setting is None or getattr(setting, 'crontab', None) is None:
        return None, None
    return setting.crontab, bool(setting.enabled)


def _candidates(crontab, minutes):
    """The cadence-preserving minute shifts of the answered crontab.

    Only the minute field changes: the candidate minute set is the answered
    set moved by a fixed offset modulo 60, spelled as an explicit list -
    ``*/30`` therefore yields ``7,37 * * * *`` and not a silently re-derived
    pattern. The answer is the **entire** crontab, the four fields beside the
    minute one carried over unchanged, because a screen must be able to save
    what it was shown. Candidates whose set equals the answered one (a shift
    the set is invariant under) answer nothing.

    Returns:
        list: ``(offset, crontab spelling, row)`` per usable candidate
    """
    seen = {tuple(minutes)}
    out = []
    for offset in MINUTE_OFFSETS:
        shifted = tuple(sorted({(m + offset) % 60 for m in minutes}))
        if shifted in seen:
            continue
        seen.add(shifted)
        candidate = CrontabSchedule(
            minute=','.join(str(m) for m in shifted),
            hour=crontab.hour, day_of_month=crontab.day_of_month,
            month_of_year=crontab.month_of_year,
            day_of_week=crontab.day_of_week, timezone=crontab.timezone)
        try:
            # Celery decides usability - the same rule the preview's
            # request serializer applies to a proposed crontab
            candidate.schedule
        except Exception:
            continue
        spelling = ' '.join((
            candidate.minute, candidate.hour, candidate.day_of_month,
            candidate.month_of_year, candidate.day_of_week))
        out.append((offset, spelling, candidate))
    return out


def _capacity_gap(snapshot, entry, queue):
    """Why the snapshot answers no verified capacity, in observed words.

    Returns:
        tuple: the refusal detail text or None - None only when every term
            a ranking needs is verified: comparable rho (which itself only
            exists with observed topology, complete eligible slots and full
            cost coverage), terminal attempt samples and a seconds histogram
    """
    if not snapshot.get('available'):
        reason = snapshot.get('reason') or 'the snapshot answered nothing'
        return (_('the deployment capacity snapshot is unavailable: %s')
                % reason)
    if snapshot.get('confidence') == 'unknown':
        return _('the worker fleet could not be observed')
    if entry is None:
        return _('the capacity snapshot answers no entry for the '
                 '"%(queue)s" queue of this schedule') % {'queue': queue}
    if entry.get('status') != 'ok':
        return _('the "%(queue)s" queue is in state "%(status)s"') % {
            'queue': queue, 'status': entry.get('status')}
    if entry.get('rho') is None:
        return _('no comparable rho for the "%(queue)s" queue: its periodic '
                 'cost or its eligible worker slots are not measured') % {
            'queue': queue}
    coverage = entry.get('periodic_demand_coverage')
    if coverage is None or coverage < 1:
        return _('the periodic demand of the "%(queue)s" queue is only '
                 'partially costed') % {'queue': queue}
    observed = entry.get('observed') or {}
    samples = (observed.get('coverage') or {}).get('terminal_samples') or 0
    if not samples:
        return _('no terminal task samples were measured for the '
                 '"%(queue)s" queue in the cost window') % {'queue': queue}
    if not entry.get('histogram_seconds'):
        return _('the capacity snapshot answers no seconds histogram for '
                 'the "%(queue)s" queue') % {'queue': queue}
    return None


def cadence_suggestions(setting, proposal, estimate, routing, at=None,
                        snapshot=None):
    """Entire valid alternative crontabs which keep the answered cadence.

    Read-only and fail-closed: an answer is either a suggestion set whose
    cadence was verified by a canonical occurrence walk over one identical
    dated horizon, or one stated `SuggestionGapEnum` refusal. The snapshot
    of #1326 is the only capacity source; no schedule table is scanned, no
    other service is read, nothing is saved.

    Args:
        setting: the saved setting the draft edits, or None for a new one
        proposal: the answered `ScheduleProposal`, or None to answer from
            the saved values of `setting`
        estimate: the `PeriodicCapacityEstimate` answered for this draft -
            its schedule gaps decide the cadence refusals before any
            capacity is consulted
        routing: a `PeriodicTask`-shaped row (the saved setting, or a fresh
            unsaved instance of the setting model) whose ``queue`` and
            ``task`` answer which queue a dispatch of this schedule lands
            on - the same decision the snapshot's demand side makes
        at (datetime): the moment to evaluate from, now by default
        snapshot (dict): the capacity snapshot to decide on; read through
            the bounded reader of #1326 when not given (tests inject theirs)

    Returns:
        SuggestionAnswer: the alternatives or the refusal with its reason
    """
    at = at or now()
    if _BLOCKING_GAPS.intersection(estimate.schedule.gaps):
        return _refuse(SuggestionGapEnum.NOT_PERIODIC.value)
    try:
        return _suggestions(setting, proposal, estimate, routing, at,
                            snapshot)
    except Exception as error:
        # the preview must keep answering its #1327 contract whatever the
        # suggestion engine does: fail closed into the stated nothing
        logger.warning('suggestions: engine failed closed: %s', error)
        return _refuse(SuggestionGapEnum.CAPACITY_UNVERIFIED.value)


def _suggestions(setting, proposal, estimate, routing, at, snapshot):
    """The engine body, after the blocking-gap decision."""
    crontab, enabled = _answered_crontab(setting, proposal)
    if crontab is None or not enabled:
        return _refuse(SuggestionGapEnum.NOT_PERIODIC.value)
    draft = DraftSchedule(setting, crontab, enabled, at, proposal)
    if draft.one_off:
        # a one-off has no cadence to preserve: another single moment would
        # change what the administrator asked for, not only when it happens
        return _refuse(SuggestionGapEnum.NOT_PERIODIC.value)

    tz = crontab.timezone
    first_day = at.astimezone(tz).date() + timedelta(days=1)
    horizon_days = _horizon_days()
    budget = _max_occurrences()
    lower, upper = _window(first_day, horizon_days, tz,
                           draft.start_time, draft.expires)
    if upper <= lower:
        return _refuse(SuggestionGapEnum.SCHEDULE_ENDED.value, horizon_days)
    original, truncated = _count(crontab, lower, upper, budget)
    if original is None:
        return _refuse(SuggestionGapEnum.CADENCE_UNVERIFIABLE.value,
                       horizon_days)
    if not original and not truncated and horizon_days < _long_horizon_days():
        # a rare pattern is re-evaluated over the documented longer horizon
        # before its cadence counts unverifiable
        horizon_days = _long_horizon_days()
        lower, upper = _window(first_day, horizon_days, tz,
                               draft.start_time, draft.expires)
        original, truncated = _count(crontab, lower, upper, budget)
        if original is None:
            return _refuse(SuggestionGapEnum.CADENCE_UNVERIFIABLE.value,
                           horizon_days)
    if truncated or not original:
        # no occurrence to compare by - equivalence stays unproven
        return _refuse(SuggestionGapEnum.CADENCE_UNVERIFIABLE.value,
                       horizon_days)

    candidates = _candidates(crontab, sorted(crontab.schedule.minute))
    if not candidates:
        return _refuse(SuggestionGapEnum.CADENCE_NO_SPACE.value, horizon_days)
    equivalent = []
    for offset, spelling, candidate in candidates:
        instants, cand_truncated = _count(candidate, lower, upper, budget)
        if cand_truncated or instants is None:
            continue
        if len(instants) == len(original):
            equivalent.append((offset, spelling, candidate, instants))
    if not equivalent:
        return _refuse(SuggestionGapEnum.CADENCE_UNVERIFIABLE.value,
                       horizon_days)

    if snapshot is None:
        try:
            snapshot = get_capacity_snapshot()
        except Exception as error:
            logger.warning('suggestions: snapshot unreadable: %s', error)
            snapshot = {'available': False,
                        'reason': 'the snapshot reader could not be asked'}
    if not isinstance(snapshot, dict):
        snapshot = {'available': False,
                    'reason': 'the snapshot reader answered no verdict'}
    queue = _queue_of(routing)
    entry = (snapshot.get('queues') or {}).get(queue)
    detail = _capacity_gap(snapshot, entry, queue)
    if detail is not None:
        return _refuse(SuggestionGapEnum.CAPACITY_UNVERIFIED.value,
                       horizon_days, str(detail))

    histogram = entry['histogram_seconds']
    horizon_meta = snapshot.get('horizon') or {}
    evidence_start = _as_moment(horizon_meta.get('start'))
    evidence_end = _as_moment(horizon_meta.get('end'))
    bucket_seconds = horizon_meta.get('bucket_seconds')
    buckets = len(histogram)
    if evidence_start is None or evidence_end is None or not bucket_seconds:
        return _refuse(SuggestionGapEnum.CAPACITY_UNVERIFIED.value,
                       horizon_days, str(
                           _('the capacity snapshot answers no usable '
                             'horizon for its histograms')))

    def expected_seconds(moments):
        """The histogram seconds the firings of one schedule expect.

        Firings past the snapshot's evidence window stay out for both
        schedules alike - the comparison never charges one side a bucket
        the snapshot did not observe.
        """
        return sum(
            histogram[capacity_demand.bucket_of(
                moment, evidence_start, bucket_seconds, buckets)]
            for moment in moments if moment <= evidence_end)

    original_seconds = expected_seconds(original)
    if not any(moment <= evidence_end for moment in original):
        return _refuse(SuggestionGapEnum.CAPACITY_UNVERIFIED.value,
                       horizon_days, str(_(
                           'the evaluated horizon lies outside the evidence '
                           'window of the capacity snapshot')))
    samples = ((entry.get('observed') or {}).get('coverage') or {}).get(
        'terminal_samples') or 0

    scored = []
    for offset, spelling, _candidate, instants in equivalent:
        seconds = expected_seconds(instants)
        if seconds < original_seconds:
            scored.append((original_seconds - seconds, offset, spelling,
                           seconds))
    if not scored:
        return _refuse(SuggestionGapEnum.NO_MEASURED_IMPROVEMENT.value,
                       horizon_days)
    scored.sort(key=lambda row: (-row[0], row[1]))
    coverage = entry.get('periodic_demand_coverage')
    snapshot_at = _as_moment(snapshot.get('snapshot_at')) or at
    timezone_name = getattr(tz, 'key', str(tz))
    suggestions = tuple(
        CadenceSuggestion(
            crontab=spelling,
            timezone=timezone_name,
            horizon_days=horizon_days,
            horizon_start=lower + timedelta(microseconds=1),
            horizon_end=upper + timedelta(microseconds=1),
            firing_count=len(original),
            queue=queue,
            original_worker_seconds=round(original_seconds, 3),
            expected_worker_seconds=round(seconds, 3),
            sample_count=samples,
            cost_coverage=coverage,
            snapshot_at=snapshot_at,
            reason=str(SUGGESTION_REASON % {
                'count': len(original), 'horizon': horizon_days,
                'queue': queue, 'expected': round(seconds, 1),
                'original': round(original_seconds, 1),
                'samples': samples}))
        for _improvement, _offset, spelling, seconds
        in scored[:_max_suggestions()])
    return SuggestionAnswer(suggestions=suggestions,
                            horizon_days=horizon_days)


def _queue_of(routing):
    """The queue a dispatch of the answered schedule lands on.

    The same decision the demand side of the snapshot makes for a saved
    row: the row's own queue, else the task's declared route, else the
    broker default. For a schedule which does not exist yet the caller
    hands in a draft routing row built through the setting family's own
    initialisation - the one place which knows the task and queue the save
    path would dispatch with; no schedule row is read or written for this.
    """
    capacity_demand.ensure_task_registry()
    return capacity_demand.queue_of(
        routing, capacity_topology.task_routes(),
        app.conf.task_default_queue)
