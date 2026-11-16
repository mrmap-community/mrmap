"""Who could execute what, right now (#1330, consumed by #1326).

The occupancy samples of ``capacity_telemetry`` answer *what was consumed*;
a capacity snapshot is only honest when it also knows *what could serve* the
work. This module reads that off the running fleet with celery's own
inspection commands and keeps the epic #1324 accounting rules:

*   A worker is **one pool of slots**. A worker consuming ``monitoring``,
    ``update`` and ``default`` is one pool with three routing entries, not
    three pools - #1326 must never multiply its slots per queue.
*   Task→queue assignment (what the app *publishes* to) and worker→queue
    subscription (what a worker *reads*) are separate answers:
    ``task_routes`` versus ``consumed_by``.
*   A declared queue no live worker consumes is **unhealthy** - the
    starvation of #970/#1040. The per-worker view of that already exists and
    stays the proof at worker start (``MrMap.celery.check_consumed_queues``);
    this is the fleet-wide, api-readable counterpart.
*   Anything that cannot be observed answers ``unknown`` - an unreachable
    control console yields ``{"available": False, "reason": ...}``, never a
    silently empty fleet that a reader would compute ``rho`` against.

The observation costs a broadcast round trip over the broker, so the result
is cached for ``CAPACITY_TOPOLOGY_CACHE_SECONDS`` and every caller
shares it; the cache never hides the *unavailable* verdict for long.
"""

from logging import Logger

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

from MrMap.celery import app

logger: Logger = settings.ROOT_LOGGER

#: the cache key #1326 must know, so an invalidation on a topology change
#: (a deployment which starts a narrowed worker) has one documented place
TOPOLOGY_CACHE_KEY = "mrmap-capacity-topology"


def task_routes():
    """The task name → queue map the app publishes by.

    This project routes through the ``queue=`` of the task declarations
    (there are no ``CELERY_TASK_ROUTES`` - see ``MrMap/celery_queues.py``),
    so the declaration attribute answers the route; a task without one is
    published to the default queue.
    """
    default_queue = app.conf.task_default_queue
    routes = {}
    for name, task in app.tasks.items():
        routes[name] = getattr(task, "queue", None) or default_queue
    return routes


def _worker_node_name(stats_entry, fallback):
    return str(stats_entry.get("hostname") or fallback)


def _worker_slots(stats_entry):
    """The concurrent slots one worker reports, or None for unknown.

    The prefork pool answers ``pool.max-concurrency``; the threads and solo
    pools do not always fill it. A missing answer stays *unknown* - the
    configured ``CELERY_WORKER_CONCURRENCY`` is what a deployment asked for,
    not what a running worker confirmed, and #1326 must be able to tell
    those apart.
    """
    pool = stats_entry.get("pool") or {}
    if isinstance(pool, dict):
        slots = pool.get("max-concurrency")
        if isinstance(slots, int) and slots > 0:
            return slots
    return None


def _observed_workers(stats, active):
    """One entry per live worker: the slots its ``stats`` answer states and
    the queues its ``active_queues`` answer names - None queues whenever
    that second answer stayed out."""
    workers = {}
    for node, entry in stats.items():
        if not isinstance(entry, dict):
            entry = {}
        queues = None
        if active:
            replies = active.get(node)
            if replies is not None:
                queues = sorted({
                    queue.get("name") for queue in replies
                    if isinstance(queue, dict) and queue.get("name")})
        workers[str(node)] = {
            "slots": _worker_slots(entry),
            "queues": queues,
        }
    return workers


def _routing_of(workers, declared):
    """Which queue which worker consumes: every declared queue gets a
    (possibly empty) consumer list, workers without routing answer are
    reported apart - the fleet of #1326 must not spread them anywhere."""
    consumed_by = {name: [] for name in declared}
    unknown_routing = []
    for node, entry in sorted(workers.items()):
        if entry["queues"] is None:
            unknown_routing.append(node)
            continue
        for queue in entry["queues"]:
            consumed_by.setdefault(queue, []).append(node)
    zero_consumer = [name for name, nodes in consumed_by.items()
                     if not nodes]
    return consumed_by, zero_consumer, unknown_routing


def observe_topology(force=False):
    """The live worker/queue topology, fail-closed, briefly cached.

    Returns a dict shaped like::

        {"available": True,
         "observed_at": <aware datetime>,
         "workers": {  # one entry per live worker = one capacity POOL
           "celery@host": {"slots": 4 | None,
                           "queues": ["default", "monitoring"] | None}, ...},
         "declared_queues": ["db-routines", "default", ...],
         "consumed_by": {"monitoring": ["celery@host"], ...},
         "zero_consumer_queues": ["update"],         # unhealthy, #970's shape
         "task_routes": {"registry.tasks.monitoring.run_probe_check": "monitoring", ...}}

    or, when the fleet cannot be reached::

        {"available": False, "reason": "...", "observed_at": <...>}

    ``queues`` is None for a worker whose ``active_queues`` reply is missing:
    a worker that answers ``stats`` but not ``active_queues`` contributes
    slots of *unknown* routing, which #1326 must not silently spread over
    every queue.
    """
    ttl = max(1, int(getattr(
        settings, "CAPACITY_TOPOLOGY_CACHE_SECONDS", 60)))
    if not force:
        cached = cache.get(TOPOLOGY_CACHE_KEY)
        if cached is not None:
            return cached

    observed_at = timezone.now()
    timeout = float(getattr(
        settings, "CAPACITY_TOPOLOGY_TIMEOUT_SECONDS", 1.0))
    inspect = app.control.inspect(timeout=timeout)
    try:
        stats = inspect.stats() or {}
        active = inspect.active_queues() or {}
    except Exception as error:
        logger.debug("capacity topology: inspect failed: %s", error)
        stats = {}
        active = None  # nothing heard at all: the verdict will be unavailable

    if not stats:
        # no live worker answered - or the console could not be reached.
        # Either way an empty fleet is NOT reported as a fleet of zero
        # workers: #1326 reads this as unknown and shows no rho (#1324).
        verdict = {"available": False,
                   "reason": "no worker answered the inspect broadcast",
                   "observed_at": observed_at}
        cache.set(TOPOLOGY_CACHE_KEY, verdict, ttl)
        return verdict

    workers = _observed_workers(stats, active)

    declared = [queue.name for queue in app.conf.task_queues]
    consumed_by, zero_consumer, unknown_routing = _routing_of(
        workers, declared)

    verdict = {
        "available": True,
        "observed_at": observed_at,
        "workers": workers,
        "declared_queues": declared,
        "consumed_by": consumed_by,
        "zero_consumer_queues": sorted(zero_consumer),
        "unknown_routing_workers": sorted(unknown_routing),
        "task_routes": task_routes(),
        # the fleet verdict beside the per-worker start-up error of #1040:
        # a narrowed worker logs there, the snapshot reads it here
        "observed_with": "celery inspect stats/active_queues",
    }
    cache.set(TOPOLOGY_CACHE_KEY, verdict, ttl)
    return verdict


def reset_topology_cache():
    """Drops the cached verdict (a topology change, or a test seam)."""
    cache.delete(TOPOLOGY_CACHE_KEY)
