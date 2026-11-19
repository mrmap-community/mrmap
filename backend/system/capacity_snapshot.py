"""The deployment capacity snapshot of #1326: materialized, bounded, fail-closed.

This module combines the supply side (the worker/queue topology of #1330 and
the broker observations added here) with the demand side
(:mod:`system.capacity_demand`) into one answer per deployment, and serves
it from the cache. The endpoint of ``system.views`` never scans schedules,
never broadcasts to the broker and never touches the attempt table: it reads
the materialized snapshot and may trigger **at most one** rebuild - under a
build lock, at a distance of ``CAPACITY_SNAPSHOT_MIN_REBUILD_SECONDS`` from
the last build.

What the snapshot may and may not claim (the acceptance criteria of #1326,
implemented as code):

*   **One worker is one pool of slots.** A worker consuming ``monitoring``
    and ``update`` is one pool with two routing entries: its slots are
    counted once for the fleet, and a per-queue answer may only multiply
    them when the assignment is verifiable - the pool serves that queue
    exclusively, or every other queue those consumers serve has
    demonstrably no scheduled demand in the horizon.
*   **A queue without a consumer is degraded, not infinitely fast.** Zero
    consumers is the starvation shape of #970/#1040; it yields no ``rho``,
    no drain and a named gap.
*   **``rho`` only when comparable.** A number is answered only when the
    topology was observed, every relevant pool's slots were observed, and
    the periodic demand is fully costed by measurements. Everything else is
    ``null`` with its reason - and a full ``rho`` still says
    ``periodic_only``: other workload (event-driven dispatches, harvest
    waves) is not measured forward, so the value is a **lower bound on
    total demand**, never "safe capacity available". The threshold is a
    tunable advisory, not a theorem.
*   **Queue depth is an integer count**, read off the broker; a queue the
    broker cannot answer for stays ``null`` with a reason. Drain and
    first-start ranges stay ``null`` as long as the arrival rate of
    non-periodic work is unobserved - the honest state of every deployment
    today - and a zero-consumer queue is reported degraded, never as zero
    wait.
*   **Stale is a visible state.** A snapshot whose schedule definitions
    changed (the fingerprint moved), or which outlived its TTL, is served
    with ``stale: true`` - it is never quietly re-labeled as fresh.
"""

from datetime import timedelta
from logging import Logger

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone
from MrMap.celery import app

from system import capacity_demand, capacity_measures, capacity_topology

logger: Logger = settings.ROOT_LOGGER

#: the materialized snapshot; cached longer than its TTL so a reader can
#: still be served an answer which is honestly marked stale
SNAPSHOT_CACHE_KEY = "mrmap-capacity-snapshot"

#: a short-lived marker so concurrent readers trigger one rebuild, not one
#: per reader (a crashed builder expires it with this TTL, like the
#: topology verdict of #1330)
BUILD_LOCK_KEY = SNAPSHOT_CACHE_KEY + ":build"

#: the cache key of the in-flight/reserved observation (#1326's own broker
#: round trip, shared under the topology's bounds)
MESSAGES_CACHE_KEY = "mrmap-capacity-messages"

#: the keys the redis transport parks a message under once a worker has
#: taken it out of its queue but not acked it (the driver keys of kombu, as
#: ``registry.tasks.harvest`` already reads them, #972). They are **not**
#: lists: ``unacked`` is a hash (uuid to message body) and ``unacked_index``
#: its zset index - #1423 counted the hash with ``LLEN`` and every read of a
#: busy broker died with WRONGTYPE
UNACKED_HASH_KEY = "unacked"
UNACKED_INDEX_KEY = "unacked_index"

#: the vocabulary of ``gaps`` entries a reader may match on; plain strings
#: because the endpoint's fail-closed states are a public contract
GAP_TOPOLOGY_UNAVAILABLE = "topology_unavailable"
GAP_QUEUE_DEPTH_UNOBSERVED = "queue_depth_unobserved"
GAP_MESSAGE_BACKLOG_UNOBSERVED = "message_backlog_unobserved"
GAP_WORKER_SLOTS_UNKNOWN = "worker_slots_unknown"
GAP_WORKER_ROUTING_UNKNOWN = "worker_routing_unknown"
GAP_ZERO_CONSUMER_QUEUE = "zero_consumer_queue"
GAP_COST_INCOMPLETE = "periodic_cost_not_measured"
GAP_WALK_BUDGET_EXHAUSTED = "walk_occurrence_budget_exhausted"
GAP_SCHEDULES_TRUNCATED = "schedules_truncated"
GAP_SCHEDULE_UNREADABLE = "schedule_definition_unreadable"
GAP_MEASUREMENT_WINDOW_EMPTY = "no_measured_samples_in_window"
GAP_ARRIVAL_RATE_UNOBSERVED = "nonperiodic_arrival_rate_unobserved"

#: every gap entry a build may answer - the documented vocabulary of the
#: endpoint's fail-closed states
GAPS = (
    GAP_TOPOLOGY_UNAVAILABLE, GAP_QUEUE_DEPTH_UNOBSERVED,
    GAP_MESSAGE_BACKLOG_UNOBSERVED, GAP_WORKER_SLOTS_UNKNOWN,
    GAP_WORKER_ROUTING_UNKNOWN, GAP_ZERO_CONSUMER_QUEUE,
    GAP_COST_INCOMPLETE, GAP_WALK_BUDGET_EXHAUSTED,
    GAP_SCHEDULES_TRUNCATED, GAP_SCHEDULE_UNREADABLE,
    GAP_MEASUREMENT_WINDOW_EMPTY, GAP_ARRIVAL_RATE_UNOBSERVED)

#: stated instead of measured, as the issue asks: rho below the threshold is
#: a reason to look, not a theorem of safety
RHO_STATEMENT = (
    "rho compares the measured worker-seconds of the PERIODIC schedules of "
    "the horizon to the slot-seconds of the eligible pools: other workload "
    "(event-driven dispatches, harvest waves, retries not yet scheduled) is "
    "not measured forward, so the value is a lower bound on total demand. "
    "A value below the advisory threshold is not a claim that capacity is "
    "safe; it says only that the periodic schedules alone do not exceed "
    "the observed slots.")

#: snapshot keys which stay datetime objects for the endpoint's
#: ``DateTimeField``s; everything nested is JSON text from the build on
DATETIME_KEYS = ("snapshot_at", "expires_at", "built_at")


def _setting(name, default):
    return getattr(settings, name, default)


def _ttl():
    return max(1, int(_setting("CAPACITY_SNAPSHOT_TTL_SECONDS", 900)))


def _min_rebuild():
    return max(1, int(_setting("CAPACITY_SNAPSHOT_MIN_REBUILD_SECONDS", 60)))


def _jsonable(value):
    """The value with every datetime turned into its ISO text.

    The snapshot travels through the JSON:API layer as plain JSON, so all
    nested moments are turned into text here, once, at build time - never
    per request.
    """
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def _inspect_broadcast(timeout):
    """``active`` and ``reserved`` as the fleet answered them.

    A side whose read raised (console unreachable, worker mid-start) is
    ``None`` — an unknown, not an empty answer.
    """
    inspect = app.control.inspect(timeout=timeout)
    answers = {}
    for name, read in (("active", inspect.active),
                       ("reserved", inspect.reserved)):
        try:
            answers[name] = read()
        except Exception as error:
            logger.debug("capacity messages: inspect %s failed: %s",
                         name, error)
            answers[name] = None
    return answers


def _workers_holding(answers):
    """Per-worker active/reserved counts as the fleet reported them."""
    workers = {}
    for kind in ("active", "reserved"):
        reply = answers[kind] or {}
        for node, entries in reply.items():
            if not isinstance(entries, list):
                continue
            entry = workers.setdefault(
                str(node), {"active": None, "reserved": None})
            entry[kind] = len(entries)
    return workers


def _messages_totals(answers):
    """Fleet-wide active/reserved counts; None per side never heard."""
    totals = {}
    for kind in ("active", "reserved"):
        if answers[kind] is None:
            totals[kind] = None
            continue
        totals[kind] = sum(len(entries) for entries in answers[kind].values()
                           if isinstance(entries, list))
    return totals


def observe_message_backlog(force=False):
    """What the fleet holds in hand right now: active and reserved messages.

    ``inspect active`` is what the workers are executing, ``inspect
    reserved`` what a prefork worker has fetched but not started - #1326's
    "reserved/active messages", the idle-but-reserved work its acceptance
    criterion names. Both are broadcast round trips, so the answer is
    shared for ``CAPACITY_TOPOLOGY_CACHE_SECONDS`` and every fail-closed
    answer names its reason instead of pretending an empty fleet.
    """
    ttl = max(1, int(_setting("CAPACITY_TOPOLOGY_CACHE_SECONDS", 60)))
    if not force:
        cached = cache.get(MESSAGES_CACHE_KEY)
        if cached is not None:
            return cached
    observed_at = timezone.now()
    timeout = float(_setting("CAPACITY_TOPOLOGY_TIMEOUT_SECONDS", 1.0))
    answers = _inspect_broadcast(timeout)
    if answers["active"] is None and answers["reserved"] is None:
        verdict = {
            "available": False,
            "reason": "no worker answered the active/reserved broadcast",
            "observed_at": observed_at,
        }
        cache.set(MESSAGES_CACHE_KEY, verdict, ttl)
        return verdict

    verdict = {
        "available": True,
        "observed_at": observed_at,
        "workers": _workers_holding(answers),
        "totals": _messages_totals(answers),
        "observed_with": "celery inspect active/reserved",
    }
    partial = [kind for kind in ("active", "reserved")
               if answers[kind] is None]
    if partial:
        verdict["partial"] = partial
    cache.set(MESSAGES_CACHE_KEY, verdict, ttl)
    return verdict


def _delivery_backlog(client):
    """The unacked backlog, counted with the verbs the keys actually want.

    ``unacked`` is a **hash** and ``unacked_index`` the matching **zset** of
    the redis transport, so the counts are ``HLEN`` and ``ZCARD`` - an
    ``LLEN`` against the hash raises WRONGTYPE the moment any message is
    unacked, which is exactly the live-broker case of #1423. Each key is
    read on its own: a key the broker cannot answer for stays ``null`` with
    its reason while the other key keeps its answer - and the queue depths,
    read by the caller outside this helper, are never lost to a surprise on
    one of these two keys.
    """
    backlog = {"unacked": None, "unacked_index": None, "reason": None}
    for name, key, verb in (
            ("unacked", UNACKED_HASH_KEY, "hlen"),
            ("unacked_index", UNACKED_INDEX_KEY, "zcard")):
        try:
            backlog[name] = int(getattr(client, verb)(key))
        except Exception as error:
            backlog[name] = None
            backlog["reason"] = f"the backlog key {key} could not be " \
                                f"read: {error}"
            logger.debug("capacity backlog: read of %s failed: %s",
                         key, error)
    return backlog


def observe_queue_depths(declared):
    """The integer message count of every declared queue, from the broker.

    Depth is a **count**, never seconds (#1326): seconds come from the
    measured costs, the count comes from here. The redis transport keys a
    queue by its plain name, so ``LLEN`` answers it in O(1) per queue - and
    a queue the broker cannot answer for stays null with a reason, because
    "depth zero" and "depth unknown" are different statements a reader must
    not confuse when it judges whether a queue is starved.
    """
    depths = {name: {"depth": None, "reason": None} for name in declared}
    try:
        with app.connection_for_read() as connection:
            client = getattr(connection.default_channel, "client", None)
            if client is None:
                return {
                    "available": False,
                    "reason": "the broker client of this transport answers "
                              "no queue lengths",
                    "queues": depths,
                }
            for name in declared:
                try:
                    depths[name]["depth"] = int(client.llen(name))
                except Exception as error:
                    depths[name]["reason"] = f"unreadable: {error}"
            # the backlog has its own read, and the keys their own verbs:
            # #1423 died right here, one wrong Redis verb away from
            # disabling the whole section over a correct depths read
            backlog = _delivery_backlog(client)
    except Exception as error:  # broker down: the whole section is unknown
        logger.debug("capacity depths: broker read failed: %s", error)
        return {
            "available": False,
            "reason": f"the broker could not be read: {error}",
            "queues": depths,
        }
    return {
        "available": True,
        "observed_at": timezone.now(),
        "queues": depths,
        "delivery_backlog": backlog,
    }


def _declared_queues():
    """The queues of the deployment, declared in ``MrMap/celery_queues.py``.

    Read from the app's static declarations - not from the broker - so a
    snapshot which cannot reach the fleet still knows which queues *should*
    have consumers, which is the whole point of naming zero-consumer queues.
    """
    return sorted({queue.name for queue in app.conf.task_queues})


def build_capacity_snapshot(at=None, horizon_days=None):
    """One materialized answer for the deployment, JSON-safe.

    Costs one build (everything bounded, none of it per request): two
    grouped cost queries and the per-queue measurement windows over the
    indexed attempt table, one walk over the enabled schedules, one cached
    topology verdict, one cached active/reserved broadcast and one round of
    ``LLEN`` reads. The walk budgets cap the schedule side; the caches make
    two builds inside the TTL barely more expensive than one read.

    Args:
        at (datetime): the snapshot moment, ``now`` by default (tests drive
            the clock through it)
        horizon_days (int): the horizon, default
            ``CAPACITY_SNAPSHOT_HORIZON_DAYS``
    """
    started = timezone.now()
    at = at or started
    capacity_demand.ensure_task_registry()
    routes = capacity_topology.task_routes()

    cost_window_days = int(_setting("CAPACITY_COST_LOOKBACK_DAYS", 7))
    since = at - timedelta(days=cost_window_days)
    costs = capacity_demand.measured_costs(since=since, until=at)
    demand = capacity_demand.periodic_demand(
        at, horizon_days=horizon_days, costs=costs, task_routes=routes)

    topology = capacity_topology.observe_topology()
    messages = observe_message_backlog()
    declared = _declared_queues()
    depths = observe_queue_depths(declared)

    horizon_seconds = (demand["horizon"]["end"] - at).total_seconds()
    gaps = set()
    if not messages.get("available"):
        gaps.add(GAP_MESSAGE_BACKLOG_UNOBSERVED)

    pools = _pools(topology, gaps)
    fleet_slots = _fleet_slot_seconds(pools, horizon_seconds)

    # consumption evidence per queue - measured inside the cost window, so
    # the answer about what a queue really costs travels with its samples
    observed = {}
    for name in declared:
        observed[name] = capacity_measures.attempt_measures(
            since=since, until=at, queue=name)
        if not observed[name]["coverage"]["terminal_samples"]:
            gaps.add(GAP_MEASUREMENT_WINDOW_EMPTY)

    queues = _queue_answers(declared, demand, topology, depths, messages,
                            observed, pools, horizon_seconds, gaps)
    rho = _fleet_rho(demand, fleet_slots, topology, gaps)
    if demand["walk"]["budget_exhausted"]:
        gaps.add(GAP_WALK_BUDGET_EXHAUSTED)
    if demand["walk"]["truncated_settings"]:
        gaps.add(GAP_SCHEDULES_TRUNCATED)
    if demand["schedules"]["excluded"]["unreadable"]:
        gaps.add(GAP_SCHEDULE_UNREADABLE)

    snapshot = {
        "id": "deployment",
        "available": True,
        "reason": None,
        "snapshot_at": at,
        "expires_at": at + timedelta(seconds=_ttl()),
        "built_at": started,
        "stale": False,
        "confidence": _confidence(topology, depths, messages, demand, pools),
        "horizon": demand["horizon"],
        "schedules": demand["schedules"],
        "gaps": sorted(gaps),
        "pools": pools,
        "fleet": {
            # a partial sum over the workers which did answer would state a
            # fleet size the snapshot did not observe: the number is answered
            # only when every pool's concurrency was, and
            # ``workers_with_unknown_slots`` says how many were not
            "unique_worker_slots": (
                None if not pools or any(
                    p["slots"] is None for p in pools)
                else sum(p["slots"] for p in pools)),
            "workers_observed": len(pools),
            "workers_with_unknown_slots": sum(
                1 for p in pools if p["slots"] is None),
            "declared_queues": declared,
            "zero_consumer_queues": (
                topology.get("zero_consumer_queues")
                if topology.get("available") else None),
        },
        "queues": queues,
        "messages": messages,
        "rho": rho,
        "other_workload": {
            "periodic_only": True,
            "other_workload_worker_seconds": None,
            "reason": (
                "non-periodic workload (event-driven dispatches, harvest "
                "waves, retries not yet scheduled) has no forward "
                "measurement source; the periodic demand is therefore a "
                "lower bound on total demand"),
            "recent_observed": capacity_measures.attempt_measures(
                since=since, until=at),
        },
        "demand": demand,
        "costs": costs,
        "build": {
            "cost_seconds": (timezone.now() - started).total_seconds(),
            "occurrences_counted": demand["totals"]["occurrences"],
            "occurrences_used_of_budget":
                demand["walk"]["occurrences_used"],
            "occurrences_budget": demand["walk"]["occurrences_budget"],
            "observed_with": (
                "extras.scheduling.next_run_after + celery 5.7 crontab "
                "semantics, worker occupancy samples of #1330, celery "
                "inspect, redis broker keys"),
        },
        "limitations": [
            "a monthly or yearly schedule that fires outside the horizon "
            "contributes nothing to it; the horizon is stated, never "
            "extrapolated to a permanent rate",
            "on the days a zone changes its UTC offset the occurrence walk "
            "follows Beat's stepping, so a late dispatch of that day "
            "shifts the rest of the day's answer",
            "a one-off that dispatches between two builds stays counted "
            "until the next rebuild (bounded by the snapshot TTL and the "
            "fingerprint interval)",
            RHO_STATEMENT,
        ],
        # the demand this snapshot was built over is about *these* schedule
        # definitions: readers compare the live fingerprint against this to
        # know whether the answer is still about the current deployment
        "schedule_fingerprint": capacity_demand.schedule_fingerprint(
            force=True),
    }
    for key, value in snapshot.items():
        if key not in DATETIME_KEYS:
            snapshot[key] = _jsonable(value)
    return snapshot


def _pools(topology, gaps):
    """The unique worker pools: one entry per worker, slots counted once.

    A worker which answers ``stats`` without ``active_queues`` keeps its
    routing unknown - its slots are *not* spread over every queue (the
    issue's "no extrapolation across queues without explicit assumptions"),
    and the gap names why.
    """
    if not topology.get("available"):
        gaps.add(GAP_TOPOLOGY_UNAVAILABLE)
        return []
    unknown_routing = set(topology.get("unknown_routing_workers") or [])
    pools = []
    for name, entry in sorted((topology.get("workers") or {}).items()):
        slots = entry.get("slots")
        queues = entry.get("queues")
        if slots is None:
            gaps.add(GAP_WORKER_SLOTS_UNKNOWN)
        if queues is None or name in unknown_routing:
            gaps.add(GAP_WORKER_ROUTING_UNKNOWN)
        pools.append({
            "worker": name,
            "slots": slots,
            "slots_source": "observed" if slots is not None else "unknown",
            "queues": queues,
            "routing_source": (
                "observed" if queues is not None else "unknown"),
        })
    return pools


def _fleet_slot_seconds(pools, horizon_seconds):
    """``unique slots x horizon`` - or nothing, if any pool's slots are unknown.

    A capacity answer which silently dropped the workers with unknown slots
    would *raise* rho against a smaller denominator; #1326 rather answers
    nothing than a number built on a denominator it made up.
    """
    if not pools:
        return None
    if any(p["slots"] is None for p in pools):
        return None
    total = sum(p["slots"] for p in pools)
    return total * horizon_seconds


def _queue_entry(name, declared, zero_consumers, topology_ok, consumers,
                 depth_entry, depths, demand_entry, observed):
    """One queue's answer row: depth, consumers and periodic demand.

    The capacity-dependent keys (eligible slots, status, rho) are filled
    by the caller once ``_eligible_capacity`` has been consulted.
    """
    return {
        "name": name,
        "declared": name in declared,
        "queue_depth": depth_entry.get("depth"),
        "queue_depth_reason": depth_entry.get("reason") or (
            None if depths.get("available") else depths.get("reason")),
        "consumers": consumers,
        "zero_consumers": (
            name in zero_consumers if topology_ok else None),
        "periodic_occurrences": demand_entry.get("occurrences", 0),
        "periodic_demand_worker_seconds":
            demand_entry.get("demand_worker_seconds"),
        "periodic_demand_coverage": demand_entry.get("cost_coverage"),
        "periodic_cost_sources": demand_entry.get(
            "cost_sources", {"periodic_name": 0, "task_average": 0,
                             "unknown": 0}),
        "histogram_seconds": demand_entry.get("histogram_seconds"),
        "histogram_occurrences":
            demand_entry.get("histogram_occurrences"),
        "observed": observed.get(name),
    }


def _apply_eligibility(entry, name, consumers, slots_of, queues_of, demand,
                       topology_ok, horizon_seconds):
    """The capacity a queue may verifiably count as its own: complete,
    exclusive or neither - the rho answer reads exactly these numbers."""
    slots, complete, exclusive = _eligible_capacity(
        name, consumers, slots_of, queues_of, demand, topology_ok)
    entry["eligible_workers_complete"] = complete
    entry["exclusive_workers"] = exclusive
    entry["eligible_slots"] = slots if complete else None
    entry["eligible_slot_seconds"] = (
        slots * horizon_seconds
        if complete and slots is not None else None)
    entry["other_workload_worker_seconds"] = None
    entry["rho"] = None


def _apply_health(entry, name, zero_consumers, topology_ok, gaps):
    """How this queue is living: starved, unobservable or answered - the
    verdict which decides whether rho is readable at all."""
    if name in zero_consumers:
        gaps.add(GAP_ZERO_CONSUMER_QUEUE)
        entry["status"] = "degraded"
        entry["note"] = (
            "no live worker consumes this queue: the starvation shape "
            "of #970/#1040 - messages are accepted and never executed, "
            "so neither wait nor capacity is answerable")
    elif not topology_ok:
        entry["status"] = "unknown"
        entry["note"] = (
            "the fleet could not be observed; consumers, capacity and "
            "rho are unknown, not zero")
    else:
        entry["status"] = "ok"
        entry["rho"] = _queue_rho(entry)


def _queue_answers(declared, demand, topology, depths, messages, observed,
                   pools, horizon_seconds, gaps):
    """The per-queue section: depth, consumers, demand, evidence, rho.

    ``rho`` is answered for a queue only when its eligible pools' capacity
    is assignable to it without double counting: either every consumer
    serves this queue exclusively, or every *other* queue those consumers
    serve carries verifiably zero scheduled demand in this horizon. Both
    are checkable off this snapshot's own answers - the "explicit and
    verifiable" condition of the issue, not an assumption.
    """
    topology_ok = bool(topology.get("available"))
    consumed_by = topology.get("consumed_by") or {}
    zero_consumers = set(topology.get("zero_consumer_queues") or [])
    slots_of = {pool["worker"]: pool["slots"] for pool in pools}
    queues_of = {pool["worker"]: pool["queues"] for pool in pools}

    names = sorted(set(declared) | set(demand["queues"]) | set(consumed_by))
    answers = {}
    for name in names:
        demand_entry = demand["queues"].get(name) or {}
        consumers = (sorted(consumed_by.get(name) or []) if topology_ok
                     else None)
        depth_entry = (depths.get("queues") or {}).get(name) or {}
        if not depths.get("available") or depth_entry.get("depth") is None:
            gaps.add(GAP_QUEUE_DEPTH_UNOBSERVED)

        entry = _queue_entry(name, declared, zero_consumers, topology_ok,
                             consumers, depth_entry, depths, demand_entry,
                             observed)
        _apply_eligibility(entry, name, consumers, slots_of, queues_of,
                           demand, topology_ok, horizon_seconds)
        _apply_health(entry, name, zero_consumers, topology_ok, gaps)
        entry["drain_estimate"] = None
        entry["drain_reason"] = _drain_reason(entry, messages)
        answers[name] = entry
    return answers


def _sharing_of(name, worker, queues_of, demand):
    """How one consumer shares its slots: ``(serves_only_this, shares_busy)``.

    ``shares_busy`` is the double-count guard: the worker also serves a
    queue with scheduled demand in this horizon, so no verifiable
    assignment of its slots to a single queue exists. Sharing with a
    verifiably idle queue is no guard - checkable, not assumed.
    """
    only_this = True
    shares_busy = False
    for other in (queues_of.get(worker) or []):
        if other == name:
            continue
        only_this = False
        if (demand["queues"].get(other) or {}).get("occurrences"):
            shares_busy = True
    return only_this, shares_busy


def _eligible_capacity(name, consumers, slots_of, queues_of, demand,
                       topology_ok):
    """The slots assignable to one queue, and whether that answer is whole.

    Returns:
        tuple: ``(slots_or_None, complete, exclusive)`` - ``exclusive`` is
            True when every consumer of the queue serves this queue alone;
            capacity is still assignable when the other queues those
            workers serve carry no scheduled demand in this horizon
            (zero occurrences - checkable, not assumed).
    """
    if not topology_ok or consumers is None or not consumers:
        return None, False, False
    slots = 0
    complete = True
    exclusive = True
    for worker in consumers:
        if worker not in slots_of or slots_of[worker] is None:
            complete = False
            continue
        only_this, shares_busy = _sharing_of(name, worker, queues_of, demand)
        if not only_this:
            exclusive = False
        if shares_busy:
            # this pool is shared with a queue that has real scheduled
            # demand: multiplying its slots here would double count, and
            # no verifiable assignment exists
            return None, complete, False
        slots += slots_of[worker]
    return slots, complete, exclusive


def _queue_rho(entry):
    """rho for one queue - only when both sides are whole and comparable."""
    if entry["status"] != "ok" or not entry["eligible_workers_complete"]:
        return None
    slot_seconds = entry["eligible_slot_seconds"]
    demand_seconds = entry["periodic_demand_worker_seconds"]
    if not slot_seconds or demand_seconds is None:
        return None
    if (entry["periodic_demand_coverage"] or 0) < 1:
        return None
    return _rho_value(demand_seconds, slot_seconds)


def _fleet_rho(demand, fleet_slots, topology, gaps):
    """The fleet-wide periodic-only rho, only when comparable everywhere.

    ``unique`` capacity is summed over workers - the shared-worker
    acceptance of the issue: one 4-slot worker serving two queues is 4
    slots, never 8. Any unknown slot, any uncosted occurrence or any
    missing topology keeps the answer null with its reason: a ratio built
    on partially measured terms is exactly the false precision this
    endpoint exists to avoid.
    """
    total_demand = demand["totals"]["periodic_demand_worker_seconds"]
    coverage = demand["totals"]["cost_coverage"]
    if total_demand is None:
        if demand["totals"]["occurrences"]:
            gaps.add(GAP_COST_INCOMPLETE)
        return {
            "value": None,
            "reason": (
                "the periodic demand answers no seconds: either no schedule "
                "fires in the horizon or none of its dispatches were "
                "measured to cost anything"),
        }
    if not topology.get("available"):
        return {"value": None, "reason": (
            "the worker/queue topology could not be observed")}
    if coverage is None or coverage < 1:
        gaps.add(GAP_COST_INCOMPLETE)
        return {"value": None, "reason": (
            f"only {coverage:.0%} of the expected dispatches have measured "
            "per-occurrence costs; a rho over partially costed demand is "
            "false precision")}
    if fleet_slots is None:
        return {"value": None, "reason": (
            "at least one worker did not report its concurrency; the "
            "capacity denominator would be made up, not observed")}
    threshold = float(_setting("CAPACITY_RHO_ADVISORY_THRESHOLD", 0.7))
    return {
        "value": _rho_value(total_demand, fleet_slots),
        "basis": "periodic_only",
        "periodic_demand_worker_seconds": round(total_demand, 3),
        "unique_slot_seconds": round(fleet_slots, 3),
        "advisory_threshold": threshold,
        "exceeds_advisory_threshold": (
            total_demand / fleet_slots > threshold),
        "statement": RHO_STATEMENT,
    }


def _rho_value(demand_seconds, slot_seconds):
    if not slot_seconds:
        return None
    return round(demand_seconds / slot_seconds, 4)


def _drain_reason(entry, messages):
    """Why the drain/first-start range stays null, in observed terms.

    #1326 allows a range only when eligible slots, estimated remaining
    work, arrival rate, reservations and in-flight tasks are *all*
    observed. The arrival rate of non-periodic work is observed nowhere in
    today's deployment - a harvest wave is exactly the workload a drain
    would have to predict - so every queue carries that reason, and the
    checks above it name anything else already missing. A zero-consumer
    queue is reported as degraded with an unbounded wait, never as a
    "zero wait".
    """
    reasons = []
    if entry["zero_consumers"]:
        reasons.append("degraded: no consumer, wait is unbounded")
    elif entry["status"] != "ok":
        reasons.append(f"status: {entry['status']}")
    if entry["queue_depth"] is None:
        reasons.append("queue depth unobserved")
    if not entry["eligible_workers_complete"]:
        reasons.append("eligible slot count incomplete")
    if entry["periodic_demand_worker_seconds"] is None:
        reasons.append("per-occurrence costs unmeasured")
    if not messages.get("available"):
        reasons.append("reserved/active backlog unobserved")
    reasons.append(GAP_ARRIVAL_RATE_UNOBSERVED)
    return reasons


def _confidence(topology, depths, messages, demand, pools):
    """One word for how much of the picture was observable.

    ``unknown``: the fleet itself is unobservable - the snapshot says
    nothing about capacity. ``degraded``: observable, but the deployment is
    in the starvation shape. ``partial``: a section stayed unobserved or
    uncosted. ``complete``: every section answered and the demand is fully
    costed (or nothing fires at all).
    """
    if not topology.get("available"):
        return "unknown"
    if topology.get("zero_consumer_queues"):
        return "degraded"
    complete = (
        depths.get("available")
        and messages.get("available")
        and not demand["walk"]["budget_exhausted"]
        and not demand["walk"]["truncated_settings"]
        and not demand["schedules"]["excluded"]["unreadable"]
        and not any(p["slots"] is None for p in pools)
        and not any(p["queues"] is None for p in pools)
        and not messages.get("partial")
        # coverage is a float; >= (with the None kept as "not complete")
        # is the same statement as == 1.0 without the float equality
        and (not demand["totals"]["occurrences"]
             or (demand["totals"]["cost_coverage"] is not None
                 and demand["totals"]["cost_coverage"] >= 1)))
    return "complete" if complete else "partial"


def snapshot_is_current():
    """Whether the cached snapshot is about today's schedules and fresh."""
    snapshot = cache.get(SNAPSHOT_CACHE_KEY)
    if snapshot is None:
        return False
    if snapshot["schedule_fingerprint"] != \
            capacity_demand.schedule_fingerprint():
        return False
    age = (timezone.now() - snapshot["built_at"]).total_seconds()
    return age <= _ttl()


def refresh(force=False):
    """Rebuild the snapshot if it is stale (or ``force``), under the lock.

    Returns:
        dict: a summary of what happened - the beat task logs it and the
            admin sees the state through the endpoint itself.
    """
    if not force and snapshot_is_current():
        return {"refreshed": False, "reason": "snapshot is current"}
    if not cache.add(BUILD_LOCK_KEY, True, _setting(
            "CAPACITY_SNAPSHOT_BUILD_LOCK_SECONDS", 300)):
        return {"refreshed": False, "reason": "a build is already running"}
    try:
        snapshot = build_capacity_snapshot()
        _store(snapshot)
        return {
            "refreshed": True,
            "snapshot_at": snapshot["snapshot_at"].isoformat(),
            "confidence": snapshot["confidence"],
            "horizon_days": snapshot["horizon"]["days"],
            "schedules_walked": snapshot["schedules"]["walked"],
            "occurrences": snapshot["build"]["occurrences_counted"],
            "cost_seconds": snapshot["build"]["cost_seconds"],
        }
    finally:
        cache.delete(BUILD_LOCK_KEY)


def _store(snapshot):
    """Cache the snapshot longer than its TTL, so stale can stay visible."""
    cache.set(SNAPSHOT_CACHE_KEY, snapshot, _ttl() * 3)


def _acquire_build_lock():
    """Whether this reader is the one allowed to build right now."""
    return cache.add(BUILD_LOCK_KEY, True, _setting(
        "CAPACITY_SNAPSHOT_BUILD_LOCK_SECONDS", 300))


def _build_cold_or_verdict():
    """The first snapshot of a cold cache - or an honest verdict."""
    if not _acquire_build_lock():
        return _verdict("a capacity snapshot is being built", None)
    try:
        try:
            fresh = build_capacity_snapshot()
            _store(fresh)
        except Exception as error:
            logger.warning("capacity snapshot build failed: %s", error)
            return _verdict(
                "the capacity snapshot could not be built", str(error))
        return dict(fresh, stale=False)
    finally:
        cache.delete(BUILD_LOCK_KEY)


def _serve_or_refresh(snapshot):
    """The cached answer: fresh, served stale, or rebuilt under the lock."""
    fingerprint = capacity_demand.schedule_fingerprint()
    age = (timezone.now() - snapshot["built_at"]).total_seconds()
    changed = snapshot["schedule_fingerprint"] != fingerprint
    if not changed and age <= _ttl():
        return dict(snapshot, stale=False)
    if not _acquire_build_lock():
        return dict(snapshot, stale=True)
    try:
        if not changed and age < _min_rebuild():
            # the definitions did not move; the horizon start ages
            # by less than a rebuild is worth - beat's refresh and
            # the next read past the distance will fix it
            return dict(snapshot, stale=True)
        try:
            fresh = build_capacity_snapshot()
            _store(fresh)
        except Exception as error:
            logger.warning(
                "capacity snapshot rebuild failed, serving the stale "
                "answer: %s", error)
            return dict(snapshot, stale=True)
        return dict(fresh, stale=False)
    finally:
        cache.delete(BUILD_LOCK_KEY)


def get_capacity_snapshot():
    """The reader's entry point: serve the materialized answer, honestly.

    A fresh snapshot comes straight from the cache - no schedule scan, no
    broker round trip, no attempt-table read, and one bounded fingerprint
    read at most once per its own interval. A stale or missing one may
    trigger **one** rebuild: the lock makes it one per interval no matter
    how many readers arrive, and the min-rebuild distance keeps a busy
    fleet from walking 43k schedules for a second time over the same
    definitions. A reader which arrives while another builds is served the
    stale answer with ``stale: true``; with nothing to serve yet the answer
    is a fail-closed verdict instead of a half-built number.
    """
    snapshot = cache.get(SNAPSHOT_CACHE_KEY)
    if snapshot is None:
        return _build_cold_or_verdict()
    return _serve_or_refresh(snapshot)


def _verdict(reason, detail):
    """The fail-closed answer: a stated nothing, never an invented something.

    Carries no counts, no topology and no queue section, so an answer of
    "unknown" cannot leak a partially observed deployment either.
    """
    now = timezone.now()
    return {
        "id": "deployment",
        "available": False,
        "reason": reason if detail is None else f"{reason}: {detail}",
        "snapshot_at": now,
        "expires_at": now,
        "built_at": now,
        "stale": False,
        "confidence": "unknown",
        "gaps": [],
    }
