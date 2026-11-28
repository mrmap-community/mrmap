.. _capacity-snapshot:

====================================
Deployment capacity snapshot (#1326)
====================================

``GET /api/system/capacity`` answers one question for a deployment
administrator: *what is this fleet committed to over the next horizon, and
what does it cost per queue?* It is the read endpoint that #1326 asked for:
admin-only, read-only, served from a materialized snapshot, and fail-closed —
every number it answers is one it actually observed, and everything it could
not observe is named as a gap instead of being filled in.

The measurement sources are the ones #1330 built: the attempt samples of
:ref:`celery-capacity-telemetry` (per-occurrence costs) and the
``system.capacity_topology`` broker observation (who consumes which queue).
This document is the reading guide for the answer — what each section means
and what it may **not** be used to claim.

Nothing is computed per request
===============================

Walking up to 43 000 schedules costs seconds, so no HTTP request ever does
it. The build runs where it is cheap — the periodic beat row ``refresh
capacity snapshot`` (every quarter-hour, minutes 13/28/43/58, so it never
lands on the top-of-hour dispatch pile) and a stale read served stale-while-
revalidate — and the view only reads the cached answer.

A rebuild is triggered by two things:

* the snapshot's TTL (``CAPACITY_SNAPSHOT_TTL_SECONDS``, default 900 s)
  having passed, and
* the **schedule fingerprint** having moved: a cached 30 s digest over the
  enabled beat rows and the crontab/interval rows they point at. Editing a
  shared crontab row in place moves the fingerprint even though no task row
  changes — that is why the digest folds both tables' content and why no
  ``post_save`` signal is involved: django-celery-beat's ``Entry.save()``
  runs a full save on every dispatch, so signals would invalidate
  constantly. A fingerprint that is only 30 s old is reused, so a burst of
  reads never re-counts the table.

``CAPACITY_SNAPSHOT_MIN_REBUILD_SECONDS`` keeps two rebuilds a minimum
distance apart and ``CAPACITY_SNAPSHOT_BUILD_LOCK_SECONDS`` is the lock that
lets exactly one reader pay for a build while every other reader gets the
still-cached answer (``stale: true`` says so).

The response
============

One JSON:API resource ``CapacitySnapshot`` with the id ``deployment``.
The attribute names are camelize'd by the JSON:API renderers, but the
sections are JSON values and keep the keys below — the snake_case spellings
are the stable contract.

``snapshotAt`` / ``expiresAt`` / ``builtAt`` / ``stale``
    what moment the answer speaks about and how fresh it is. A served-stale
    answer sets ``stale``; it is a working snapshot that could not be
    refreshed, not a fresh one.

``available`` / ``reason``
    the fail-closed switch. When the snapshot cannot be built at all the
    answer is **a 200** with ``available: false``, a ``reason``,
    ``confidence: "unknown"`` and *no sections at all* — an answer of
    "unknown" must not leak a partially observed deployment either. Do not
    branch on HTTP codes; branch on ``available``.

``fleet``
    the worker pools that answered ``inspect``: ``workers_observed``,
    ``workersWithUnknownSlots``, ``declaredQueues``, ``zeroConsumerQueues``
    and ``uniqueWorkerSlots`` — the fleet's total worker slots, summed over
    *distinct worker names*, never over queues (a worker that consumes two
    queues is four slots, not eight). It is ``null`` when any pool failed to
    report its concurrency: a partial sum would state a fleet size the
    snapshot did not observe.

``queues``
    one entry per queue name seen anywhere (declared, demanded or consumed):
    ``queueDepth`` (an **integer count** of messages in the broker, never a
    rate), ``consumers``, ``zeroConsumers``, ``periodicOccurrences``,
    ``periodicDemandWorkerSeconds``, ``periodicDemandCoverage``,
    ``periodicCostSources``, the two per-bucket ``histogram*`` arrays,
    ``observed`` (measured wait/occupancy for the window), ``eligibleSlots``
    and ``rho``. A queue no live worker consumes is ``status:
    "degraded"`` with the #970/#1040 starvation note: depth grows, nothing
    executes, neither wait nor capacity is answerable.

``rho``
    the fleet utilization, and the section where fake precision would hurt
    most. It is answered only when both sides are comparable: the demand
    fully costed (coverage 1.0 from ``measured_worker`` samples), the
    topology observed and every pool's concurrency known. It is then
    ``basis: "periodic_only"`` — a **lower bound**, because the arrival rate
    of non-periodic work (event-driven dispatches, harvest waves, retries)
    is not observed anywhere yet: that gap is
    ``nonperiodic_arrival_rate_unobserved``, and it is why
    ``drainEstimate`` stays ``null`` with a ``drainReason``. An advisory
    threshold (``CAPACITY_RHO_ADVISORY_THRESHOLD``, default 0.7) travels
    with the value; crossing it is a reason to look, not an alert.

``schedules`` / ``demand``
    how the counting went: ``walked``, ``excluded`` counts per reason
    (``disabled``, ``expired``, ``one_off_ran``, ``no_schedule``,
    ``unreadable``), ``unreadableExamples`` naming up to 20 rows whose
    definition Celery cannot build, and the horizon with its buckets. A
    single broken row is excluded and named; it never takes the snapshot
    down.

``gaps``
    the machine-readable list of everything the snapshot knows it does not
    know — see the vocabulary below. A reader that wants an absolute
    statement checks this list first.

``otherWorkload``
    says in ``reason`` that the demand is a lower bound, and carries
    ``recentObserved``: the measured wait/occupancy answers of #1330 for the
    window, which *do* include non-periodic executions that already happened
    — observation of the past, never a forward rate.

``scheduleFingerprint``
    the fingerprint the snapshot was built over. A reader comparing it
    against the live one knows whether the answer is still about *these*
    definitions.

``reachability``
    the schedule-side answer of #1827, and the section which asks the
    question the demand side cannot: a beat schedule whose runs need longer
    than the interval its own row fires on never meets its own cadence. The
    fires are still dispatched — beat honours the interval — but the
    ``SingletonTask`` lock of #837 refuses every second one, and a refused
    fire contributes no occurrence to any demand count. One entry per
    short-interval enabled row (``interval_seconds`` at most
    ``TASK_PERFORMANCE_REACHABILITY_MAX_INTERVAL_SECONDS``):

    ``interval_seconds``
        what the ``PeriodicTask`` row says, converted from whatever
        ``IntervalSchedule``/``CrontabSchedule`` it points at;
    ``samples`` / ``active_p95`` / ``overrun_ratio``
        the measured completed duration of the attempts *that row*
        dispatched (``periodic_name``), and the p95 over its interval. No
        samples, or fewer than ``CAPACITY_REACHABILITY_MIN_SAMPLES``, answers
        ``verdict: "unknown"`` with both at ``null`` — absence of a
        measurement is never an answer of "reachable";
    ``fires`` / ``dropped_fires`` / ``skipped_share``
        the attempt rows of the same window for that row, of which the ones
        whose fire the lock refused (``outcome: "skipped"``, #1827), and
        their share;
    ``verdict``
        ``reachable``, ``tight`` (it fits with less than
        ``CAPACITY_REACHABILITY_HEADROOM`` to spare) or ``unreachable`` —
        ``unreachable`` also adds the ``schedule_interval_unreachable`` gap.

    The same read backs the ``schedule_overrun`` incident of the #1390
    detector, so a schedule is never reachable in one screen and an incident
    in the other.

The occurrence walk
===================

``system.capacity_demand`` counts each schedule's fire instants inside the
horizon with the same step Beat itself takes —
``extras.scheduling.next_run_after`` is Beat's own stepping, made public —
so the count is Beat's count, including the oddities:

* on a day whose zone changes its UTC offset the walk follows Beat's
  stepping, so ``30 2 * * *`` in Europe/Berlin fires **once** on the spring
  day (at 01:30 UTC, the 02:30 local slot being skipped) and once on the
  autumn day (at 00:30 UTC, on the first 02:30); this was verified against
  celery 5.7 in a real interpreter, not derived from the docs,
* a crontab with both day-of-month and day-of-week restricted fires on the
  **AND of the field matches** (verified against celery 5.7, unlike Vixie
  cron's OR rule), and the module reproduces exactly that,
* a wall-clock-grid fast path replaces the per-occurrence step for the
  ordinary days; it is disabled on offset-changing days and proven
  equivalent to the canonical step by tests over both DST windows.

Budgets bound every walk: at most ``CAPACITY_SNAPSHOT_MAX_SCHEDULES`` rows,
``CAPACITY_SNAPSHOT_MAX_OCCURRENCES_PER_SETTING`` per row and
``CAPACITY_SNAPSHOT_MAX_OCCURRENCES`` overall; hitting one is a stated gap
(``schedules_truncated``, ``walk_occurrence_budget_exhausted``), not a
silent short count.

Costs come from #1330 samples only: a schedule costs the mean of its
terminal attempts keyed by ``periodic_name`` (at least
``CAPACITY_COST_MIN_SAMPLES``), else the mean of its task name, each
labelled in ``periodicCostSources`` (``periodic_name`` / ``task_average`` /
``unknown``), and an entirely uncosted schedule contributes occurrences with
``demandWorkerSeconds: null`` — coverage says how much of the demand is
money, the rest stays a labeled lower bound.

Per-queue ``rho``
=================

A queue's own ``rho`` is answered only when its worker set is exclusive
(every consumer consumes *only* this queue — checkable from the same
topology, not assumed) or every other queue those workers consume
verifiably has zero occurrences in the horizon. Otherwise it is ``null``:
two busy queues must not both claim the same four slots.

The gaps vocabulary
===================

``topology_unavailable``
    no worker answered the broadcast — consumers, slots and per-queue rho
    are unknown, not zero.
``queue_depth_unobserved`` / ``message_backlog_unobserved``
    the broker itself (or its backlog keys) could not be read; depth stays
    null.
``worker_slots_unknown`` / ``worker_routing_unknown``
    a pool answered but not its concurrency / subscriptions; fleet sums
    that would include it are null.
``zero_consumer_queue``
    the starvation shape: declared demand (or messages) with no live
    consumer.
``periodic_cost_not_measured``
    some occurrences had no measured cost; the demand keeps its lower-bound
    label and fleet rho stays null.
``walk_occurrence_budget_exhausted`` / ``schedules_truncated``
    a budget cut the walk short; the counts are a stated prefix.
``schedule_definition_unreadable``
    some rows' definitions Celery cannot build (they can never dispatch
    either — see the ``day_of_week: 7`` upstream finding below); named in
    ``unreadableExamples``.
``no_measured_samples_in_window``
    the #1330 window held no terminal samples; nothing is measured, as
    distinct from measured-zero.
``nonperiodic_arrival_rate_unobserved``
    permanent today: no source observes non-periodic arrivals forward, so
    drain estimates stay null.
``schedule_interval_unreachable``
    a beat schedule whose measured p95 costs more than the interval its own
    row fires on (#1827): the singleton lock drops the fires between two
    runs, so the deployment's rows are current at half the cadence its
    settings name. Named per schedule in ``reachability``; the #1390
    detector publishes the same reading as an incident.

Settings
========

===================================================================================================  =================
``CAPACITY_SNAPSHOT_TTL_SECONDS``                                                                    freshness target
                                                                                                     of the cached
                                                                                                     snapshot (900)
``CAPACITY_SNAPSHOT_HORIZON_DAYS`` / ``..._MAX_HORIZON_DAYS``                                        /
                                                                                                     ``..._MAX_HORIZON_DAYS``
                                                                                                     counted horizon
                                                                                                     (7 / 31)
``CAPACITY_SNAPSHOT_BUILD_LOCK_SECONDS`` / ``..._MIN_REBUILD_SECONDS``                               one builder at a
                                                                                                     time, minimum
                                                                                                     rebuild distance
                                                                                                     ``CAPACITY_FINGERPRINT_CACHE_SECONDS``
                                                                                                     the digest's own
                                                                                                     cache interval
                                                                                                     (30)
``CAPACITY_SNAPSHOT_BUCKET_SECONDS`` / ``..._MAX_BUCKETS``                                           histogram
                                                                                                     resolution (3600
                                                                                                     / 744)
``CAPACITY_SNAPSHOT_MAX_SCHEDULES`` / ``..._MAX_OCCURRENCES`` / ``..._MAX_OCCURRENCES_PER_SETTING``  the walk budgets
``CAPACITY_COST_LOOKBACK_DAYS`` / ``..._COST_MIN_SAMPLES`` / ``..._COST_GROUP_LIMIT``                the costing
                                                                                                     window and its
                                                                                                     bounds
``CAPACITY_RHO_ADVISORY_THRESHOLD``                                                                  the advisory line
                                                                                                     that travels with
                                                                                                     rho (0.7)
``CAPACITY_REACHABILITY_HEADROOM`` / ``..._MIN_SAMPLES`` / ``..._WINDOW_MINUTES``                     the margin, the
                                                                                                     sample floor and
                                                                                                     the window of the
                                                                                                     reachability panel
                                                                                                     of #1827 (1.1 / 5
                                                                                                     / 360)
===================================================================================================  =================

What may not be claimed
=======================

* a monthly or yearly schedule that fires outside the horizon contributes
  nothing to it — the horizon is stated, never extrapolated to a permanent
  rate;
* a one-off that dispatched between two builds stays counted until the next
  rebuild (bounded by TTL and fingerprint interval);
* ``rho`` is ``periodic_only`` — total demand is *at least* that, never
  exactly that;
* queue depth is a count at the build moment, not a rate; nothing here
  answers "how long will this backlog take to drain".
* a schedule the reachability panel calls ``unknown`` is not a reachable
  schedule — it is an unanswered one; and a ``reachable`` verdict is about
  the measured window, not a guarantee for the next one, since the duration
  moves with the size of the catalogue.

Upstream finding (not fixed here)
=================================

django-celery-beat's validators accept ``day_of_week="7"`` (and ``"0,7"``,
``"7-1"``) although its own help text says Sunday is 0 or 7 — while celery
5.7.0 raises ``ValueError: Invalid end range: 7 > 6`` when the schedule is
built. Such a stored row can therefore never dispatch. The snapshot counts it
as ``unreadable``, names it and keeps going; the upstream bug stands on its
own.

See also: :ref:`celery-capacity-telemetry`, :ref:`celery-queues`,
:ref:`development-agent-capacity`.
