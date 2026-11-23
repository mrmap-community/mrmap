"""Continuous detection of slow, regressing and long-running Celery tasks (#1390).

Epic #1387's V1 made tasks cheap to run and proved it with deterministic query
counts; this module is the V2 question no static guard can answer: *is this
deployment running its tasks slowly right now, and which class got measurably
slower since its own previous window*. The issue's central warnings are the
design, so the evaluation is four separate condition types, each with its own
evidence rule:

``completed_slow``
    A *finished* attempt occupied a worker slot longer than the active-time
    budget of its class. Read from ``active_seconds`` only, so the acceptance
    example of #1390 holds by construction: 4 h of queue waiting in front of a
    2 s execution is 2 active seconds and a 4 h *wait* sample. Queue waiting
    belongs to the capacity side (#1324/#1326); it is reported as its own
    separately-labelled condition and is never actionable here.
``regression``
    The p95 of the active seconds of a class moved beyond a factor of the
    *same class and queue's own* comparable baseline window - and the p50
    moved with it, which is what separates a shifted distribution from a
    heavier tail. Both windows need their minimum sample count and a baseline
    long enough for a ratio to mean anything. When no p95 ratio is computable
    the total occupied slot cost answers the same question. An isolated spike
    is not a regression: with the middle of the window unmoved and the share
    of attempts beyond the class' own old p95 inside its spike allowance, the
    spike is already what ``completed_slow`` called it.
``long_running``
    An attempt which is *still open*, has already run past the long-running
    budget of its class, and is reported active by a worker the inspection
    reached. Terminal and open samples alone cannot prove current activity, so
    the worker's own answer is part of the evidence: without it the verdict is
    a labelled suspicion which publishes no incident, and a worker which does
    not answer at all is *unknown* - never healthy, never a confirmed long task.
``coverage``
    The telemetry which cannot see what it should: attempts without a publish
    stamp, attempts which stood open past the abandon grace without ever
    closing, or collection switched off while operations stand open. This is
    the only condition #1390 allows to be reported about missing data.

Nothing is reported because data is missing in the other direction either: an
empty window answers ``no_data``, an under-sampled one answers ``insufficient``
and neither publishes anything nor drags a baseline down; a class whose last
sample went too old stops being claimed about at all, in either direction. A
fire which reaches no worker at all publishes nothing at all.

Boundedness is the other half of the promise. One evaluation costs two grouped
windowed aggregates plus one bounded read of open attempts, one bounded
exceedance count per judged class and one broker inspection - never a query
per task, never anything on a request path - and publishes at most
``TASK_PERFORMANCE_MAX_VERDICTS_PER_FIRE`` incidents on a beat schedule which
runs as a ``SingletonTask``. Failure-wise this module is the collector of #1330
and the publishers of #1320: it swallows its own errors into a log line,
because detection which delays or fails an execution is worse than none.

Incidents are the existing records of #1319 - published through
``notify.incident_reporting``, deduplicated by the manager's key, resolved by
evidence: recovery resolves the standing incident, and so does evidence which
cannot be re-made any longer, because a stale suspicion is not evidence. No
second incident store, no task state owned here, no ``GenericForeignKey``: the
typed-resource rule of #1320's watchdog, so a slow harvest of one service is
that service's incident and permission-filtered like every other one (#1203's
job center reads them through the same api).

Threshold runbook: ``docs/source/development/celery-task-performance.rst``.
"""

import json
from datetime import timedelta
from logging import Logger

from django.conf import settings
from django.db.models import (Count, Exists, Max, OuterRef, Q, Sum)
from django.utils.timezone import now

from system.capacity_measures import (PercentileWithinGroup, _terminal_q,
                                      _uncertain_open_qs)
from system.models import CeleryTaskAttempt

logger: Logger = settings.ROOT_LOGGER

#: the code prefix of every condition of this detector, so the codes of #1390
#: hold their own namespace beside #1320's operation and watchdog families and
#: no other publisher can collide with them
TASK_PERF_CODE_PREFIX = "taskperf_"

#: the incident codes of the conditions; the resource scope of a task-class
#: verdict is part of the dedup key, not of the code, so one class names one
#: problem per resource (and one system-scoped problem without one)
CODE_COMPLETED_SLOW = f"{TASK_PERF_CODE_PREFIX}completed_slow"
CODE_REGRESSION = f"{TASK_PERF_CODE_PREFIX}regression"
CODE_LONG_RUNNING = f"{TASK_PERF_CODE_PREFIX}long_running"
CODE_COVERAGE_STAMP = f"{TASK_PERF_CODE_PREFIX}coverage_unstamped"
CODE_COVERAGE_STALE = f"{TASK_PERF_CODE_PREFIX}coverage_stale_open"
CODE_COVERAGE_DISABLED = f"{TASK_PERF_CODE_PREFIX}coverage_disabled"

#: the separately-labelled capacity reading: a congested route is visible in
#: the same answer as slow execution and labelled so it can never be mistaken
#: for it - the capacity work of #1324 owns it and this detector never acts on
#: it (#1390)
CODE_QUEUE_WAIT = f"{TASK_PERF_CODE_PREFIX}queue_wait"

#: every code of this detector starts with the family prefix, which is how a
#: fire recognises its own standing incidents and never touches another
#: publisher's (#1320's operation and watchdog families stay untouched)
OWNED_CODE_PREFIX = TASK_PERF_CODE_PREFIX


def class_code(base, task_name, queue=""):
    """The bounded, stable code of one class' condition."""
    from notify.incident_reporting import (INCIDENT_CODE_MAX_LENGTH,
                                           OPERATION_CODE_SEPARATOR,
                                           task_code_tail)

    tail = task_code_tail(task_name)
    code = f"{base}{OPERATION_CODE_SEPARATOR}{tail}"
    if queue:
        code = f"{code}{OPERATION_CODE_SEPARATOR}{queue}"
    return code[:INCIDENT_CODE_MAX_LENGTH]


#: what a verdict measured: a number a real attempt/worker produced, or the
#: honest absence of one (#1390: measured vs unknown)
MEASURED = "measured"
UNKNOWN = "unknown"


def _setting(name, default):
    return getattr(settings, name, default)


# ---------------------------------------------------------------------------
# the settings seam: read per fire, defaulted per value (#1390)
# ---------------------------------------------------------------------------

def detection_enabled():
    """Whether the detector evaluates at all (kill switch, #1390)."""
    return bool(_setting("TASK_PERFORMANCE_ENABLED", False))


def evaluation_window():
    """The rolling window one evaluation measures (1 h / 24 h / 7 d class)."""
    return timedelta(
        hours=max(1, int(_setting("TASK_PERFORMANCE_WINDOW_HOURS", 24))))


def min_samples():
    """Terminal attempts needed to judge a class or to trust it as baseline."""
    return max(1, int(_setting("TASK_PERFORMANCE_MIN_SAMPLES", 5)))


def default_budget_seconds():
    """The completed-slow budget of a class with no policy of its own."""
    return max(1.0, float(_setting(
        "TASK_PERFORMANCE_DEFAULT_BUDGET_SECONDS", 600.0)))


def default_long_seconds():
    """The long-running budget of a class with no policy of its own."""
    return max(1.0, float(_setting(
        "TASK_PERFORMANCE_DEFAULT_LONG_SECONDS", 1800.0)))


def long_min_active_seconds():
    """No open attempt younger than this is ever called long-running."""
    return max(1.0, float(_setting(
        "TASK_PERFORMANCE_LONG_MIN_ACTIVE_SECONDS", 60.0)))


def long_grace_seconds():
    """How far past the abandon grace of #1330 an open row may still be live.

    An open attempt older than the abandon grace is crash residue which the
    bounding sweep declares ``abandoned`` - not a task still running. Judging
    it long would report a dead worker as a slow task, which #1390's worker
    death case forbids; the grace is the margin between the two readings, so
    a sweep which has not run yet cannot hide a genuinely long task either.
    """
    return max(1.0, float(_setting("TASK_PERFORMANCE_LONG_GRACE_SECONDS", 300)))


def regression_factor():
    """How much worse than its baseline a class must be to regress."""
    return max(1.0, float(_setting("TASK_PERFORMANCE_REGRESSION_FACTOR", 2.0)))


def spike_share():
    """The share of a class's samples which may exceed its budget silently."""
    share = float(_setting("TASK_PERFORMANCE_SPIKE_SHARE", 0.10))
    return min(1.0, max(0.0, share))


def regression_min_baseline_seconds():
    """The shortest baseline duration a ratio may be computed against.

    A sub-second baseline times a factor is false precision, not a
    regression: the class ran 0.4 s and now runs 0.9 s.
    """
    return max(0.0, float(_setting(
        "TASK_PERFORMANCE_REGRESSION_MIN_BASELINE_SECONDS", 1.0)))


def max_classes():
    """Task classes one fire may judge before it reports truncation."""
    return max(1, int(_setting("TASK_PERFORMANCE_MAX_CLASSES", 200)))


def max_verdicts_per_fire():
    """Incidents one fire may publish; #1320's bound, for the same reason."""
    return max(1, int(_setting("TASK_PERFORMANCE_MAX_VERDICTS_PER_FIRE", 25)))


def coverage_min_stamped():
    """The lowest share of stamped attempts still worth a silent ok."""
    return min(1.0, max(0.0, float(_setting(
        "TASK_PERFORMANCE_COVERAGE_MIN_STAMPED", 0.5))))


def abandon_grace():
    """The abandon grace of the attempt samples of #1330, as a duration."""
    return timedelta(
        hours=max(1, int(_setting(
            "CAPACITY_TELEMETRY_ABANDON_GRACE_HOURS", 48))))


def coverage_stale_after():
    """How long past the abandon grace stale open rows may go unremarked."""
    return timedelta(
        hours=max(1, int(_setting("TASK_PERFORMANCE_ABANDON_STALE_HOURS", 6))))


def stale_after():
    """A class whose last sample is older than this answers ``no_data``.

    The silent-class failure of every monitoring tool: the class stopped
    reporting altogether, so nothing may be claimed about it any more - not
    slow, and not healthy either.
    """
    return timedelta(
        hours=max(1, int(_setting("TASK_PERFORMANCE_STALE_AFTER_HOURS", 72))))


def policies():
    """The per-class policy map, from both places a deployment may set it.

    ``TASK_PERFORMANCE_POLICY`` is the settings-level dict;
    ``TASK_PERFORMANCE_POLICIES`` the env-friendly JSON form of the same map.
    The settings dict wins key by key, so a checked-in deployment policy is
    never silently overridden by an environment leftover.
    """
    merged = {}
    env_map = _setting("TASK_PERFORMANCE_POLICIES", None)
    if isinstance(env_map, str) and env_map.strip():
        try:
            parsed = json.loads(env_map)
        except ValueError:
            logger.warning(
                "task performance (#1390): TASK_PERFORMANCE_POLICIES is no "
                "JSON object; the setting is ignored.")
            parsed = None
        if isinstance(parsed, dict):
            merged.update(parsed)
    elif isinstance(env_map, dict):
        merged.update(env_map)
    settings_map = _setting("TASK_PERFORMANCE_POLICY", None)
    if isinstance(settings_map, dict):
        merged.update(settings_map)
    return merged


def policy_for(task_name, queue):
    """The policy of one class: the task entry, else its queue entry, else {}.

    Two keys may name one class on purpose: the task entry is the precise
    override, the ``queue:<name>`` entry the coarse one; the precise entry
    wins key by key, so a queue-wide budget and a per-task spike allowance
    compose instead of competing. An unknown key simply never matches - the
    graceful unknown of #1390: a typo costs a missing override, never a
    failed boot.
    """
    table = policies()
    merged = {}
    queue_entry = table.get(f"queue:{queue}") if queue else None
    if isinstance(queue_entry, dict):
        merged.update(queue_entry)
    task_entry = table.get(task_name)
    if isinstance(task_entry, dict):
        merged.update(task_entry)
    return merged


def class_budget(policy):
    """The completed-slow active-time budget of one class."""
    return float(policy.get("budget_seconds", default_budget_seconds()))


def class_long_seconds(policy):
    """The long-running budget of one class, never below the global floor."""
    configured = float(policy.get("long_running_seconds", default_long_seconds()))
    return max(long_min_active_seconds(), configured)


def class_regression_factor(policy):
    return max(1.0, float(policy.get("regression_factor", regression_factor())))


def class_spike_share(policy):
    share = float(policy.get("spike_share", spike_share()))
    return min(1.0, max(0.0, share))


def smallest_long_seconds():
    """The shortest long-running budget any policy declares, floored.

    The SQL bound of the open-attempt read: no row which could be a candidate
    is missed and no row which cannot be is read.
    """
    smallest = default_long_seconds()
    for entry in policies().values():
        if not isinstance(entry, dict):
            continue
        try:
            smallest = min(smallest, float(entry.get(
                "long_running_seconds", smallest)))
        except (TypeError, ValueError):
            continue
    return max(long_min_active_seconds(), smallest)


# ---------------------------------------------------------------------------
# the bounded reads: two grouped aggregates, one open read, one count per class
# ---------------------------------------------------------------------------

def _class_windows(at):
    """The measured window and the comparable baseline window of one fire.

    Two adjacent windows of the same length: the baseline is the window
    directly before the current one, which is the comparability #1390 asks for
    - a class is judged against its own recent history, never against a global
    prior.
    """
    window = evaluation_window()
    return ({"since": at - window, "until": at},
            {"since": at - 2 * window, "until": at - window})


def _aggregate_classes(since, until, task_names=None):
    """The per-class distributions of one bounded window, as one query.

    One grouped aggregate over ``(task_name, queue)`` of the terminal rows of
    the window - the window index of #1330/#1394 answers it - ordered by the
    heaviest class first and cut at ``max_classes()``. ``task_names`` scopes
    the read to classes another window already named, which is how the
    baseline stays a bounded read beside the current window instead of a
    second full scan.

    Returns:
        tuple: (rows, truncated) with ``truncated`` answering that the cut bit
    """
    qs = (CeleryTaskAttempt.objects
          .filter(started_at__gte=since, started_at__lte=until)
          .filter(_terminal_q())
          .values("task_name", "queue")
          .annotate(
              samples=Count("pk"),
              slot_seconds=Sum("active_seconds"),
              active_max=Max("active_seconds"),
              active_p50=PercentileWithinGroup("active_seconds", 0.5),
              active_p95=PercentileWithinGroup("active_seconds", 0.95),
              wait_p95=PercentileWithinGroup("wait_seconds", 0.95),
              wait_max=Max("wait_seconds",
                           filter=Q(wait_seconds__isnull=False)),
              last_started=Max("started_at"))
          .order_by("-slot_seconds"))
    if task_names is not None:
        qs = qs.filter(task_name__in=list(task_names))
    rows = list(qs[:max_classes() + 1])
    return rows[:max_classes()], len(rows) > max_classes()


def count_exceeding(task_name, queue, since, until, budget):
    """How many measured attempts of one class ran over ``budget``.

    The share is what separates an isolated spike from a shifted distribution
    in #1390's regression rule, and no aggregate answers it - so this is one
    bounded count, and only for a class actually judged.
    """
    total = (CeleryTaskAttempt.objects
             .filter(task_name=task_name, queue=queue)
             .filter(started_at__gte=since, started_at__lte=until)
             .filter(_terminal_q())
             .filter(active_seconds__gt=budget)
             .count())
    return total


# ---------------------------------------------------------------------------
# the pure decision functions: the deterministic core the tests drive
# ---------------------------------------------------------------------------

def judge_completed_slow(row, budget, samples_over, stale=False):
    """The completed-slow decision of one class, from its window numbers.

    ``row`` is the aggregate row of the class; ``samples_over`` the count of
    attempts which exceeded ``budget``. Pure on purpose: the acceptance cases
    of #1390 (a 4 h wait in front of a 2 s execution, an isolated spike, a
    normal heavy tail, a small sample) are decided here without a database.
    """
    samples = row.get("samples") or 0
    if samples < min_samples():
        return {"condition": "insufficient", "measured": MEASURED,
                "samples": samples, "min_samples": min_samples(),
                "budget_seconds": budget}
    if stale:
        return {"condition": "no_data", "measured": MEASURED,
                "samples": samples,
                "last_started": _iso(row.get("last_started"))}
    observed = row.get("active_max")
    if observed is None:
        return {"condition": "no_data", "measured": MEASURED,
                "samples": samples}
    share = (samples_over / samples) if samples else None
    return {
        "condition": "completed_slow" if observed > budget else "healthy",
        "measured": MEASURED,
        "samples": samples,
        "budget_seconds": budget,
        "observed_max_active_seconds": observed,
        "active_p50": row.get("active_p50"),
        "active_p95": row.get("active_p95"),
        "samples_over_budget": samples_over,
        "exceeded_share": share,
        "max_wait_seconds": row.get("wait_max"),
        "last_started": _iso(row.get("last_started")),
    }


def _comparable_ratio(value, baseline_value, min_baseline):
    """The ratio of two durations, or None when either side is too short.

    A sub-second baseline times a factor is false precision, and so is a
    class which stayed sub-second in absolute terms (#1390).
    """
    if value is None or baseline_value is None:
        return None
    if value < min_baseline or baseline_value < min_baseline:
        return None
    return value / baseline_value


def _per_attempt_cost(slot_seconds, samples):
    """The occupied slot cost per attempt, or None for an empty window."""
    if not slot_seconds or not samples:
        return None
    return slot_seconds / samples


def _long_enough(values, min_baseline):
    """Whether every value is a duration long enough to compare."""
    return all(value is not None and value >= min_baseline
               for value in values)


def _regression_evidence(current, baseline, factor, spike_allowance,
                         current_samples, baseline_samples, min_baseline):
    """The comparable numbers of one regression comparison, ratios included.

    The p95 of the active seconds answers the question; the total occupied
    slot cost answers the same way, as a cost PER ATTEMPT, because the two
    windows may hold different sample counts - and only while an attempt of
    either window is long enough for a ratio to mean anything.
    """
    baseline = baseline or {}
    evidence = {
        "measured": MEASURED,
        "samples": current_samples,
        "baseline_samples": baseline_samples,
        "active_p50": current.get("active_p50"),
        "active_p95": current.get("active_p95"),
        "baseline_active_p50": baseline.get("active_p50"),
        "baseline_active_p95": baseline.get("active_p95"),
        "regression_factor": factor,
        "spike_share_allowance": spike_allowance,
    }
    p95_ratio = _comparable_ratio(evidence["active_p95"],
                                  evidence["baseline_active_p95"],
                                  min_baseline)
    slot = current.get("slot_seconds")
    baseline_slot = baseline.get("slot_seconds")
    cost_ratio = None
    if baseline_slot and _long_enough(
            (slot, baseline_slot,
             _per_attempt_cost(slot, current_samples),
             _per_attempt_cost(baseline_slot, baseline_samples)),
            min_baseline):
        cost_ratio = slot / baseline_slot
    evidence.update({"p95_ratio": p95_ratio, "slot_cost_ratio": cost_ratio})
    return evidence


def _p50_moved(evidence, factor, min_baseline):
    """Whether the middle of the window moved beyond the factor as well."""
    p50 = evidence["active_p50"]
    baseline_p50 = evidence["baseline_active_p50"]
    if p50 is None or not baseline_p50 or baseline_p50 < min_baseline:
        return False
    return (p50 / baseline_p50) > factor


def _p95_verdict(evidence, current_samples, samples_over_baseline,
                 spike_allowance, min_baseline, factor):
    """What a p95 beyond the factor means: a shifted distribution or a spike.

    #1390 asks for the p50 and p95 to be reported either way, and the p50 is
    what separates a shifted distribution from a heavier tail. If the middle
    of the window moved too, the class runs slower than it did; if it stayed
    inside the factor, only the tail moved - a handful of executions beyond
    the class' own old range. That is the spike, already named by
    completed_slow, which #1390 refuses to also call a regression.
    """
    share = ((samples_over_baseline / current_samples)
             if samples_over_baseline is not None and current_samples
             else None)
    if not _p50_moved(evidence, factor, min_baseline) \
            and (share is None or share <= spike_allowance):
        # the tail alone moved, inside the class' own spike allowance
        return {"condition": "healthy", "spike_only": True,
                "exceeded_share": share, **evidence}
    # nothing (or a growing share of everything) exceeded the budget, so
    # the move is the distribution itself, not its tail
    return {"condition": "regression", "comparison": "active_p95",
            "exceeded_share": share, **evidence}


def judge_regression(current, baseline, factor, min_baseline, spike_allowance,
                     samples_over_baseline=None):
    """The regression decision: p95 first, total slot cost when no ratio exists.

    The comparison is #1390's "compare against validated comparable
    baselines": same class, same queue, adjacent window, both windows over the
    minimum sample count, baseline long enough for a ratio to mean anything.
    p50 and p95 travel with every answer so a shifted middle stays
    distinguishable from a heavier tail; the verdict needs the p95 (or, when
    no p95 ratio is computable, the total occupied slot cost) beyond the
    factor AND an exceedance share above the class' spike allowance - which is
    what keeps an isolated spike, already called ``completed_slow``, from
    becoming a regression as well. Never any false precision: an unvalidated
    comparison answers ``insufficient``, not a number.
    """
    current_samples = current.get("samples") or 0
    baseline_samples = (baseline or {}).get("samples") or 0
    needed = min_samples()
    if current_samples < needed or baseline_samples < needed:
        return {"condition": "insufficient", "measured": MEASURED,
                "samples": current_samples,
                "baseline_samples": baseline_samples,
                "min_samples": needed}
    evidence = _regression_evidence(
        current, baseline, factor, spike_allowance, current_samples,
        baseline_samples, min_baseline)
    p95_ratio = evidence["p95_ratio"]
    cost_ratio = evidence["slot_cost_ratio"]
    if p95_ratio is not None and p95_ratio > factor:
        return _p95_verdict(evidence, current_samples, samples_over_baseline,
                            spike_allowance, min_baseline, factor)
    if p95_ratio is not None:
        return {"condition": "healthy", **evidence}
    if cost_ratio is not None and cost_ratio > factor:
        # no usable p95 ratio, but a total occupied slot cost which moved:
        # the total-slot-cost form of the same question
        return {"condition": "regression", "comparison": "slot_cost",
                **evidence}
    if cost_ratio is None:
        return {"condition": "insufficient", "reason":
                "no comparable baseline duration", **evidence}
    return {"condition": "healthy", **evidence}


def judge_queue_wait(current, baseline, factor):
    """The separately-labelled capacity reading of one class (#1324's own).

    Reported so a congested route is visible exactly where slow execution is
    visible, and labelled so it can never be read as one: never actionable
    here, because the capacity work of #1324 owns queue waiting.
    """
    wait = current.get("wait_p95")
    baseline_wait = (baseline or {}).get("wait_p95")
    if wait is None or baseline_wait is None or baseline_wait <= 0:
        return None
    if wait <= baseline_wait * factor:
        return None
    return {
        "condition": "queue_wait",
        "measured": MEASURED,
        "actionable": False,
        "owner": "#1324",
        "wait_p95": wait,
        "wait_max": current.get("wait_max"),
        "baseline_wait_p95": baseline_wait,
    }


def judge_long_running(running_seconds, budget, reported_active,
                       own_worker_answered):
    """The currently-active decision for one open attempt.

    Four states, and only one of them is actionable (#1390's long-running
    cases, including the delayed inspection, the unreachable worker, the
    retry redelivery and the completion race):

    *   the worker reports the attempt active -> a confirmed long execution;
    *   the worker answers and does not report it -> the attempt already
        finished or died between the row and the inspection: no verdict;
    *   the worker did not answer at all -> ``unknown``, never healthy and
        never a confirmed long task;
    *   nothing answered at all -> the caller publishes nothing for the fire.
    """
    if running_seconds < budget:
        return {"condition": "healthy", "measured": MEASURED,
                "active_seconds": running_seconds,
                "long_running_seconds": budget}
    if reported_active:
        return {"condition": "long_running", "measured": MEASURED,
                "confidence": "high",
                "active_seconds": running_seconds,
                "long_running_seconds": budget}
    if own_worker_answered:
        # the worker which owns this attempt answered and does not report it:
        # the attempt finished or died between the row and the inspection -
        # the completion race of #1390, which must not keep a verdict alive
        return {"condition": "healthy", "measured": MEASURED,
                "reason": "finished_or_died",
                "active_seconds": running_seconds,
                "long_running_seconds": budget}
    return {"condition": "long_running", "measured": UNKNOWN,
            "confidence": "low", "reason": "worker_unreachable",
            "active_seconds": running_seconds,
            "long_running_seconds": budget}


# ---------------------------------------------------------------------------
# the currently-active side: one bounded inspection of the fleet
# ---------------------------------------------------------------------------

def _inspection():
    """One bounded inspection of the fleet, or None when it is dark.

    The rule of #1320's watchdog, which #1390 inherits: an inspection which
    reached no worker at all answers unknown for the whole fire and the fire
    publishes nothing about current activity. A partial answer is kept per
    key; only what answered is read below.
    """
    from MrMap.celery import app

    control = app.control.inspect()
    answers = {}
    for name in ("active", "conf"):
        answers[name] = getattr(control, name)()
    if all(answer is None for answer in answers.values()):
        return None
    return answers


def _hostname(node):
    """The host part of a ``celery@host`` node name, as the rows store it."""
    node = str(node or "")
    return node.split("@")[-1] if "@" in node else node


def _active_request_ids(answers):
    """The task ids the answering workers report as their current work."""
    ids = set()
    for workers in (answers.get("active") or {}).values():
        for task in workers or []:
            request = task.get("request") or {}
            task_id = request.get("id") or task.get("id")
            if task_id:
                ids.add(str(task_id))
    return ids


def _answered_hosts(answers):
    """The hosts which answered, or None when nothing declared anything."""
    if answers.get("conf") is None:
        return None
    return {_hostname(node) for node in answers["conf"]}


def long_running_candidates(at):
    """Open attempts which could be long-running, in one bounded read.

    Bound from below by ``smallest_long_seconds()`` - no class' candidate is
    missed and no ordinary execution is read - and from above by the abandon
    grace plus its margin, which is the worker-death case: a row older than
    that is crash residue for the coverage condition, never a running task.
    The attempt identity's terminal twin is excluded for the reason #1326's
    measures give it: an attempt which finished wrote its terminal row beside
    its open one, and that pair is a completed execution.
    """
    floor = smallest_long_seconds()
    since = at - abandon_grace() - timedelta(seconds=long_grace_seconds())
    until = at - timedelta(seconds=floor)
    terminal_twin = CeleryTaskAttempt.objects.filter(
        task_id=OuterRef("task_id"),
        attempt_no=OuterRef("attempt_no")).exclude(outcome="")
    return list(
        CeleryTaskAttempt.objects
        .filter(outcome="", started_at__gte=since, started_at__lte=until)
        .annotate(has_terminal=Exists(terminal_twin))
        .filter(~Q(has_terminal=True))
        .order_by("started_at")[:max_classes()])


def _worker_answered_owner(hosts, worker):
    """Whether the worker owning an attempt answered the inspection.

    Only the answer of the worker which owns the attempt can prove it still
    runs: another worker answering says nothing about this one, so an
    un-reachable owner stays unknown (#1390).
    """
    if hosts is None or not worker:
        return None
    return _hostname(worker) in hosts


def _long_running_verdict(row, running, budget, decision, at):
    """The verdict of one confirmed or suspected long-running attempt."""
    confirmed_confidence = decision["confidence"] == "high"
    verdict = {
        "code": class_code(CODE_LONG_RUNNING, row.task_name, row.queue),
        "condition": "long_running",
        "task_name": row.task_name,
        "queue": row.queue,
        "task_id": row.task_id,
        "attempt_no": row.attempt_no,
        "worker": row.worker,
        "started_at": _iso(row.started_at),
        "task_tail": _tail(row.task_name),
        "window": {"since": _iso(row.started_at), "until": _iso(at)},
        **decision,
        "severity": "error" if confirmed_confidence else "warning",
    }
    verdict["summary"] = (
        f"The task '{row.task_name}' has run {int(running)} s"
        f"{' on ' + row.worker if row.worker else ''} - beyond its "
        f"long-running budget of {int(budget)} s - and "
        + ("the worker still reports it active."
           if confirmed_confidence
           else "no answering worker reports it as its own, so its "
                "current state is unknown."))
    return verdict


def evaluate_long_running(at, answers):
    """The currently-active condition of every open candidate.

    The class budget is applied in python (the SQL bound is the smallest of
    all policies) and each candidate is decided by ``judge_long_running``
    together with the worker's own answer. Confirmed verdicts and labelled
    suspicions come back apart: only the confirmed ones publish.
    """
    confirmed, suspicions = [], []
    active_ids = _active_request_ids(answers)
    hosts = _answered_hosts(answers)
    for row in long_running_candidates(at):
        policy = policy_for(row.task_name, row.queue)
        if policy.get("disabled"):
            continue
        budget = class_long_seconds(policy)
        running = (at - row.started_at).total_seconds()
        decision = judge_long_running(
            running, budget, str(row.task_id) in active_ids,
            _worker_answered_owner(hosts, row.worker))
        if decision["condition"] != "long_running":
            continue
        verdict = _long_running_verdict(row, running, budget, decision, at)
        (confirmed if decision["measured"] == MEASURED
         else suspicions).append(verdict)
    return confirmed, suspicions


# ---------------------------------------------------------------------------
# the coverage condition: what the telemetry cannot see (#1390's fourth type)
# ---------------------------------------------------------------------------

def evaluate_coverage(since, until, at):
    """The coverage verdicts of one window: unstamped, stale, switched off.

    Three ways the measurement stops being measurement, each with a code of
    its own so they never merge into one another's story. All three name the
    deployment and no user resource, so they publish as system incidents -
    administrators alone, which is #1319's one rule and where #1390 wants the
    cannot-see verdict.
    """
    verdicts = []
    totals = (CeleryTaskAttempt.objects
              .filter(started_at__gte=since, started_at__lte=until)
              .filter(_terminal_q())
              .aggregate(terminal=Count("pk"),
                         stamped=Count("pk",
                                       filter=Q(wait_seconds__isnull=False))))
    terminal = totals["terminal"] or 0
    stamped = totals["stamped"] or 0
    if terminal:
        share = stamped / terminal
        if share < coverage_min_stamped():
            verdicts.append({
                "code": CODE_COVERAGE_STAMP,
                "condition": "coverage",
                "measured": MEASURED,
                "actionable": True,
                "severity": "warning",
                "stamped_share": share,
                "min_stamped_share": coverage_min_stamped(),
                "terminal_samples": terminal,
                "summary": (
                    f"Only {stamped} of {terminal} measured task attempts "
                    "carry a publish stamp, so their queue waiting is "
                    "unknown and the capacity answers of #1326 are blind "
                    "for them."),
            })

    # The stale threshold is the abandon grace plus the stale margin: a row
    # which crossed the grace only just now still has that margin before its
    # openness is worth an incident. Every older open row counts - a reading
    # bounded on both sides would silently forget the rows which went stale
    # between two fires. The lower bound is the retention horizon of the
    # samples themselves (#1330): past it the rows are gone from the table,
    # so the read stays bounded by the data's own lifetime and never grows
    # with the age of the deployment.
    threshold = abandon_grace() + coverage_stale_after()
    retention = timedelta(
        days=max(1, int(_setting("CAPACITY_TELEMETRY_RETENTION_DAYS", 14))))
    stale = (_uncertain_open_qs(since=at - retention)
             .filter(started_at__lt=at - threshold)
             .count())
    if stale:
        verdicts.append({
            "code": CODE_COVERAGE_STALE,
            "condition": "coverage",
            "measured": MEASURED,
            "actionable": True,
            "severity": "warning",
            "stale_open_attempts": stale,
            "stale_threshold_hours": int(threshold.total_seconds() // 3600),
            "sample_retention_days": int(retention.total_seconds() // 86400),
            "summary": (
                f"{stale} task attempts stand open past the abandon grace "
                "without ever reporting an end; their execution time is "
                "unmeasured and no performance or capacity answer covers "
                "them."),
        })

    # the deployment-level kill switch of the collector (#1330), read as the
    # setting and not via collection_enabled(): that answer is per process
    # (only worker processes collect), and the question here is whether the
    # deployment turns collection on at all
    # the deployment-level kill switch of the collector (#1330), read as the
    # setting and not via collection_enabled(): that answer is per process
    # (only worker processes collect), and the question here is whether the
    # deployment turns collection on at all. Telemetry off while operations
    # stand open IS the inadequate-coverage condition, and the dedup key of
    # #1319 keeps it to one standing incident, not one per fire.
    if not _setting("CAPACITY_TELEMETRY_ENABLED", False):
        from notify.models import BackgroundProcess

        if BackgroundProcess.objects.filter(done_at__isnull=True).exists():
            verdicts.append({
                "code": CODE_COVERAGE_DISABLED,
                "condition": "coverage",
                "measured": UNKNOWN,
                "actionable": True,
                "severity": "warning",
                "summary": (
                    "Celery attempt telemetry is switched off while "
                    "operations stand open; nothing in this deployment can "
                    "say whether its tasks are slow."),
            })
    return verdicts


# ---------------------------------------------------------------------------
# incidents: the existing records of #1319, never a second store
# ---------------------------------------------------------------------------

def _tail(task_name):
    from notify.incident_reporting import task_code_tail

    return task_code_tail(task_name)


def process_of_attempt(task_id):
    """The operation an attempt belongs to, when one names it (#1203 link).

    A ``BackgroundProcess`` keeps the ids it published (#1179), so that array
    is the one join from an attempt to the typed resource an incident may
    name. One indexed array containment per confirmed verdict - never per
    task, never per attempt of a fire.
    """
    if not task_id:
        return None
    from notify.models import BackgroundProcess

    try:
        return (BackgroundProcess.objects
                .select_related("related_resource_type")
                .filter(celery_task_ids__contains=[str(task_id)])
                .order_by("-date_created")
                .first())
    except Exception as error:
        logger.debug(
            "task performance (#1390): the operation of an attempt could "
            "not be read: %s", error)
        return None


def scope_verdict(verdict):
    """Attach the background process a confirmed verdict belongs to.

    A confirmed long execution whose task id a process published names that
    process's resource, so its incident is permission-filtered like every
    resource incident of #1319 and reachable from the job center of #1203 by
    the people who may see the service. Without a process the verdict keeps
    the system scope: one shared key per class, which is the truthful
    statement of "somebody's attempt of this class is long" and never a merge
    of two services' stories (the watchdog's rule, #1320).
    """
    process = process_of_attempt(verdict.get("task_id"))
    if process is not None:
        verdict["resource_process"] = process
        verdict["background_process"] = str(process.pk)
    return process


def publish_verdicts(verdicts):
    """Publish the actionable verdicts of one fire as incidents (#1319).

    Resource-scoped where the evidence names a resource, system-scoped
    otherwise, bounded by ``max_verdicts_per_fire`` so an event which slows
    the whole fleet at once is a bounded number of incidents. A verdict whose
    publication fails costs a log line, never the fire: an incident which
    cannot be written is no reason to break the detector (#1320's rule).

    Returns:
        list: one readable line per published verdict, like #1320's watchdog
    """
    from notify.incident_reporting import (publish_watchdog_verdict,
                                           system_verdict)

    lines = []
    ceiling = max_verdicts_per_fire()
    for verdict in verdicts[:ceiling]:
        code = verdict.get("code")
        if not code:
            continue
        details = {key: value for key, value in verdict.items()
                   if key not in ("code", "severity", "summary",
                                  "resource_process")}
        severity = verdict.get("severity", "warning")
        process = verdict.get("resource_process")
        incident = created = None
        try:
            if process is not None:
                incident, created = publish_watchdog_verdict(
                    code, process, severity, verdict["summary"], details)
            if incident is None:
                # nothing names a typed resource here - or the process's type
                # has no incident source (#1319): the system scope is the
                # truthful fallback and the verdict is never lost silently
                incident, created = system_verdict(
                    code, severity, verdict["summary"], details)
        except Exception as error:
            logger.warning(
                "task performance (#1390): the verdict %s could not be "
                "published: %s", code, error)
            continue
        if incident is not None:
            lines.append(
                f"{incident.dedup_key} ({'new' if created else 'standing'})")
    if len(verdicts) > ceiling:
        logger.warning(
            "task performance (#1390): the fire had %s actionable verdicts "
            "and published at its ceiling of %s; the rest is the next fire's "
            "question (#1390's storm bound).", len(verdicts), ceiling)
    return lines


def _coverage_code_family(code):
    """The coverage code a standing incident belongs to, or None.

    The three coverage families share the resolve rule - a coverage verdict
    which reads complete again resolves - but keep their own codes so they
    never merge into one another's story.
    """
    for family in (CODE_COVERAGE_STAMP, CODE_COVERAGE_STALE,
                   CODE_COVERAGE_DISABLED):
        if code.startswith(family):
            return family
    return None


def _resolves_standing(incident, classes, confirmed_ids, live_codes):
    """Whether one standing incident's evidence moved on (#1390)."""
    code = incident.code
    evidence = incident.details or {}
    if code.startswith(CODE_LONG_RUNNING):
        return evidence.get("task_id") not in confirmed_ids
    if _coverage_code_family(code) is not None:
        return code not in live_codes
    task_name = evidence.get("task_name")
    if not task_name:
        return False
    verdict = classes.get((task_name, evidence.get("queue")))
    return verdict is None or verdict.get("condition") in (
        "healthy", "no_data", "insufficient")


def resolve_verdicts(classes, confirmed, coverage, at):
    """Resolve this module's standing incidents whose evidence moved on.

    Every direction is evidence-side, never a timeout guess (#1390):

    *   a class whose window answers ``healthy``, or which no longer appears
        in the window at all, resolves its ``completed_slow`` and
        ``regression`` incidents - recovery proved it, or its evidence is
        gone and a verdict without evidence is no verdict;
    *   a long-running incident whose attempt is no longer confirmed
        (completed, died, redelivered elsewhere, its worker gone) resolves;
    *   a coverage verdict which reads complete again resolves.

    All of it runs over #1319's ``resolve``: one conditional update per key,
    idempotent, the single ACTIVE -> RESOLVED transition, so a fire which
    finds nothing to resolve costs one bounded read of its own code family.
    """
    from notify.enums import IncidentStatusEnum
    from notify.models import OperationalIncident

    confirmed_ids = {item["task_id"] for item in confirmed}
    live_codes = {item.get("code") for item in coverage}
    resolved = 0
    standing = OperationalIncident.objects.filter(
        code__startswith=OWNED_CODE_PREFIX,
        status=IncidentStatusEnum.ACTIVE.value)
    for incident in standing.iterator():
        if _resolves_standing(incident, classes, confirmed_ids, live_codes):
            resolved += OperationalIncident.objects.resolve(
                incident.dedup_key, at=at)
    return resolved


# ---------------------------------------------------------------------------
# the fire
# ---------------------------------------------------------------------------

def _iso(value):
    return value.isoformat() if value is not None else None


def _window_dict(window):
    return {"since": _iso(window["since"]), "until": _iso(window["until"])}


def _ratio_text(regressed):
    ratio = (regressed.get("p95_ratio")
             if regressed.get("comparison") == "active_p95"
             else regressed.get("slot_cost_ratio"))
    return "?" if ratio is None else f"{round(ratio, 2)}x"


def _class_verdict(row, slow, regressed, latency, window, baseline_window,
                   budget):
    """The actionable verdict of one judged class, or None."""
    base = {
        "task_name": row["task_name"], "queue": row["queue"],
        "task_tail": _tail(row["task_name"]),
        "window": _window_dict(window),
        "suspected_external_latency": latency,
    }
    if slow["condition"] == "completed_slow":
        return {
            "code": class_code(CODE_COMPLETED_SLOW, row["task_name"],
                               row["queue"]),
            "condition": "completed_slow",
            "severity": "warning",
            **base,
            **slow,
            "summary": (
                f"The task '{row['task_name']}' ran "
                f"{int(slow['observed_max_active_seconds'])} s on queue "
                f"'{row['queue'] or 'default'}' - over its active time "
                f"budget of {int(budget)} s - measured from "
                f"{slow['samples']} attempts."),
        }
    if regressed["condition"] == "regression":
        return {
            "code": class_code(CODE_REGRESSION, row["task_name"],
                               row["queue"]),
            "condition": "regression",
            "severity": "warning",
            **base,
            "baseline_window": _window_dict(baseline_window),
            **regressed,
            "summary": (
                f"The task '{row['task_name']}' on queue "
                f"'{row['queue'] or 'default'}' got measurably slower: "
                f"its {regressed['comparison']} is "
                f"{_ratio_text(regressed)} its own previous window "
                f"({regressed['samples']} vs "
                f"{regressed['baseline_samples']} samples)."),
        }
    return None


def _evaluate_class(row, baseline, window, baseline_window, at, stale_bound):
    """Judge one aggregated class and answer its entry and verdict.

    A disabled policy is healthy by declaration and costs no count of its
    own; everything else runs the three judges of the window, of which only
    ``completed_slow`` and ``regression`` can make a verdict - queue waiting
    is #1324's question and travels with the answer as the suspected
    external latency, never as a slow task.
    """
    key = (row["task_name"], row["queue"])
    policy = policy_for(*key)
    entry = {"task_name": row["task_name"], "queue": row["queue"],
             "samples": row["samples"],
             "window": _window_dict(window),
             "baseline_window": _window_dict(baseline_window)}
    if policy.get("disabled"):
        entry.update({"condition": "healthy", "policy": "disabled"})
        return key, entry, None
    budget = class_budget(policy)
    judged = (row["samples"] or 0) >= min_samples()
    samples_over = (count_exceeding(*key, window["since"], window["until"],
                                    budget)
                    if judged else 0)
    # the spike allowance is the share of attempts which ran over the
    # class' own OLD p95: a handful of them is a spike, most of them is a
    # shifted distribution (#1390)
    baseline_p95 = (baseline or {}).get("active_p95")
    over_baseline = (
        count_exceeding(*key, window["since"], window["until"], baseline_p95)
        if judged and baseline_p95 is not None else None)
    stale = (row["last_started"] is not None
             and (at - row["last_started"]) > stale_bound)
    slow = judge_completed_slow(row, budget, samples_over, stale=stale)
    regressed = judge_regression(
        row, baseline, class_regression_factor(policy),
        regression_min_baseline_seconds(), class_spike_share(policy),
        samples_over_baseline=over_baseline)
    entry["completed_slow"] = slow
    entry["regression"] = regressed
    waiting = judge_queue_wait(row, baseline, regression_factor())
    entry["queue_wait"] = waiting
    # #1390's evidence list asks for a suspected external latency: the
    # class' own queue-wait reading IS that hint - it says whether the
    # route in front of the execution moved as well. It travels with the
    # verdict labelled as #1324's question and costs no read of its own.
    latency = (None if waiting is None else
               {"suspected": "queue_backlog", "owner": "#1324",
                "wait_p95": waiting["wait_p95"],
                "baseline_wait_p95": waiting["baseline_wait_p95"]})
    entry["suspected_external_latency"] = latency
    entry["condition"] = (
        "completed_slow" if slow["condition"] == "completed_slow"
        else regressed["condition"])
    return key, entry, _class_verdict(row, slow, regressed, latency, window,
                                      baseline_window, budget)


def _read_windows(window, baseline_window, at):
    """The samples, coverage verdicts and baselines of one fire.

    One bounded read of the active window, its baseline and the coverage
    question; the fire's error path is the caller's, as the read of an
    unhealthy collector must never break the schedule (#1390).
    """
    rows, truncated = _aggregate_classes(window["since"], window["until"])
    names = {row["task_name"] for row in rows}
    baseline_rows, _ = _aggregate_classes(
        baseline_window["since"], baseline_window["until"], task_names=names)
    coverage = evaluate_coverage(window["since"], window["until"], at)
    baselines = {(row["task_name"], row["queue"]): row
                 for row in baseline_rows}
    return rows, truncated, coverage, baselines


def _failed_read(at, window, baseline_window, error):
    """What a fire answers when its samples could not be read."""
    return {"status": "evaluated", "at": _iso(at), "error": str(error),
            "window": _window_dict(window),
            "baseline_window": _window_dict(baseline_window),
            "classes": 0, "truncated": False, "conditions": [],
            "verdicts": [], "published": [], "resolved": 0,
            "worker_inspection": UNKNOWN, "unknown": ["sample_read"]}


def _worker_verdicts(at, answers):
    """The currently-active verdicts of one fire, and what stays unknown.

    A dark broker answers no verdict at all: nothing about current activity
    may be claimed then, and unknown is neither healthy nor broken (#1390).
    Only a confirmed long execution names an operation, so only those get
    #1203's resource scope; a suspicion stays a system statement.
    """
    if answers is None:
        return [], [], ["worker_inspection"]
    confirmed, suspicions = evaluate_long_running(at, answers)
    for item in suspicions:
        item["actionable"] = False
    for item in confirmed:
        scope_verdict(item)
    return confirmed, suspicions, []


def _actionable(verdicts):
    """The verdicts of one fire which may become an incident.

    A reading which measured nothing, a labelled suspicion and a low-
    confidence verdict are all evidence for a reader and none for an
    administrator (#1390's storm bound starts here).
    """
    return [item for item in verdicts
            if item.get("code")
            and item.get("actionable", item.get("measured") == MEASURED)
            and item.get("confidence", "high") == "high"]


def _summary(verdicts, classes, truncated, window, baseline_window, at,
             published, resolved, answers, unknown):
    """What one fire answers, including the non-actionable readings."""
    return {
        "status": "evaluated",
        "at": _iso(at),
        "window": _window_dict(window),
        "baseline_window": _window_dict(baseline_window),
        "classes": len(classes),
        "truncated": truncated,
        "conditions": sorted({item["condition"] for item in classes.values()}),
        "verdicts": [{key: value for key, value in item.items()
                      if key != "resource_process"} for item in verdicts],
        "published": published,
        "resolved": resolved,
        "worker_inspection": MEASURED if answers is not None else UNKNOWN,
        "unknown": unknown,
    }


def evaluate_task_performance(at=None, publish=True):
    """One bounded evaluation of the deployment's task performance (#1390).

    The entry of the beat task and of the deterministic tests: reads the
    attempt samples of #1330 over the rolling window and its comparable
    baseline window, decides the conditions per task class and queue,
    publishes the actionable verdicts through #1319's manager, resolves the
    standing ones whose evidence moved on, and answers everything it decided -
    including the non-actionable readings, so a reader always learns *why*
    nothing was published. ``publish=False`` is the look-without-writing form.

    Returns:
        dict: the summary of the fire; ``status`` is ``disabled`` or
            ``evaluated``, ``worker_inspection`` says whether the currently-
            active answers are measured or unknown, and ``unknown`` names
            every answer which is unknown instead of healthy
    """
    at = at or now()
    if not detection_enabled():
        return {"status": "disabled", "verdicts": [], "published": [],
                "resolved": 0, "classes": 0, "truncated": False,
                "unknown": ["detection_disabled"]}

    window, baseline_window = _class_windows(at)
    try:
        window_read = _read_windows(window, baseline_window, at)
    except Exception as error:
        # the collector or the database is unhealthy: this fire says so and
        # costs nobody anything - the tasks it observes never notice it at
        # all (#1390's outage criterion), and its next fire is the retry
        logger.warning(
            "task performance (#1390): the evaluation could not read its "
            "samples (%s); this fire publishes nothing.", error)
        return _failed_read(at, window, baseline_window, error)
    rows, truncated, coverage, baseline_by_class = window_read

    classes = {}
    verdicts = []
    stale_bound = stale_after()
    for row in rows:
        key, entry, verdict = _evaluate_class(
            row, baseline_by_class.get((row["task_name"], row["queue"])),
            window, baseline_window, at, stale_bound)
        classes[key] = entry
        if verdict is not None:
            verdicts.append(verdict)

    verdicts.extend(coverage)

    answers = _inspection()
    confirmed, suspicions, unknown = _worker_verdicts(at, answers)
    verdicts.extend(confirmed)
    verdicts.extend(suspicions)

    published = []
    resolved = 0
    if publish:
        published = publish_verdicts(_actionable(verdicts))
        resolved = resolve_verdicts(classes, confirmed, coverage, at)

    if published or resolved or suspicions:
        logger.info(
            "task performance (#1390): %s classes evaluated, %s verdicts "
            "published, %s incidents resolved, %s unconfirmed long-running "
            "suspicions labelled.", len(classes), len(published), resolved,
            len(suspicions))
    return _summary(verdicts, classes, truncated, window, baseline_window, at,
                    published, resolved, answers, unknown)
