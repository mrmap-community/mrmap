.. _celery-task-performance:

===============================================
Slow Celery task detection (continuous, V2)
===============================================

.. sidebar:: Issue #1390 · epic #1387 · **phase V2**

    Part of epic #1387 (task performance), deferred to **V2** by that epic:
    the V1 issues answer the SQL shape of a task
    (:ref:`celery-task-orm-audit`, :ref:`celery-task-sql-regression`) and the
    capacity planning of the fleet (:ref:`celery-capacity-telemetry` #1330,
    :ref:`capacity-snapshot` #1326). This page documents the *runtime*
    detection: which completed executions are slow, which task family got
    measurably slower, which execution is abnormally long **right now**, and
    whether any of that could be seen at all.

Before this existed, slow execution was only knowable from complaints, and
the loudest number on a broker - how long a message waited - was the one
most likely to be read as a slow task. Neither statement is true without
evidence, and the evidence separates. The detector of
``backend/system/task_performance.py`` reads the attempt samples #1330
already writes, decides the four questions above on a beat schedule, and
publishes its actionable verdicts as the existing ``OperationalIncident``
records of #1319/#1320. It owns no task state and no second incident table.

The four conditions, and the one thing they are not
====================================================

``completed_slow``
    A finished attempt ran over the *active time budget* of its task class
    in the evaluation window. Active time is ``active_seconds`` - worker
    slot occupancy - and **never** includes the broker. The acceptance
    example of the issue holds: a message that waited four hours and ran
    two seconds is a queue-wait sample of ~4 h and an execution of 2 s, so
    it raises nothing here; the capacity snapshot of #1326 and the capacity
    epic #1324 own queue waiting, and this verdict names it as a separate
    condition only when it is *also* congested.
``regression``
    The p95 of the active seconds - or, when no p95 ratio is computable, the
    occupied slot cost **per attempt** - of a task class measured against the
    same class' own comparable baseline moved beyond the configured factor.
    Two windows are needed to say this and minimum sample counts on both; a
    class which cannot answer them answers ``insufficient`` and publishes
    nothing. The comparison is per attempt on purpose: two windows may hold a
    different number of executions, so a class which merely ran more often,
    with byte-identical durations, did not get slower. A single slow spike
    does not move a p95 whose share is still within the spike allowance, and a
    class with a legitimate heavy tail is silenced by its own policy rather
    than being re-baselined by the tool.
``long_running``
    An attempt which is **still open** and whose active time already exceeds
    the long-running budget of its class, while **its own** worker - the one
    the attempt row names - reports it as active. Terminal samples alone
    cannot prove current activity, so without the owning worker's own report
    the verdict stays a labelled suspicion (``measured: unknown``,
    ``confidence: low``, ``reason: worker_unreachable``) and no incident is
    raised. A celery retry keeps the task uuid, so the same id running on a
    different worker confirms nothing: confirmation is matched per worker, and
    a high-confidence verdict always names the worker which gave it.
``coverage``
    The condition with no data behind it: attempts ran in the window which
    carry no publish stamp, open attempts sit past the abandon grace, or the
    collector's telemetry is switched off while operations stand open. An
    absent sample is never a healthy reading - "unknown" is what the
    detector reports - but it is also never a slow task.

Nothing is ever alerted because data is missing in the other direction
either: an empty window answers ``no_data`` and publishes nothing, and an
empty window never lowers a baseline.

Where the numbers come from
===========================

One windowed aggregate per task class per evaluation, never one query per
task and never one per request. The evaluation groups the terminal attempts
of the current window by ``(task_name, queue)``, and reads each class'
baseline from the window directly before it. Percentiles run as
``percentile_cont`` inside that single statement; the attempt table is
bounded by the retention sweep of #1330/#1394, so the read stays a bounded
index range scan. The beat task is a ``SingletonTask``: a fire still
reading costs the next fire nothing but a skip.

Configuring budgets per task class
==================================

Defaults are deliberately generous - the detection must not be the thing
that wakes people up on the week it is installed. Every value is a setting
read on every fire through a ``getattr`` seam (the value in brackets is the
default in ``backend/MrMap/settings.py``):

``TASK_PERFORMANCE_ENABLED``
    Detection at all (``off`` disables the beat task's work; the beat row
    itself stays, so switching it back on is an environment change only).
``TASK_PERFORMANCE_INTERVAL_MINUTES``
    The beat cadence (15).
``TASK_PERFORMANCE_WINDOW_HOURS``
    The current window's length (24).
``TASK_PERFORMANCE_MIN_SAMPLES``
    Terminal attempts a class needs in a window before it can be judged,
    and the same minimum for a baseline (5). Fewer answer ``insufficient``.
``TASK_PERFORMANCE_DEFAULT_BUDGET_SECONDS``
    The completed-slow budget for a class with no policy of its own (600).
``TASK_PERFORMANCE_DEFAULT_LONG_SECONDS``
    The long-running budget for a class with no policy of its own (1800).
``TASK_PERFORMANCE_LONG_MIN_ACTIVE_SECONDS``
    Floor below which no open attempt is ever called long-running (60); the
    floor keeps a class with a tiny budget from reporting every ordinary
    execution of itself.
``TASK_PERFORMANCE_LONG_GRACE_SECONDS``
    How far past the abandon grace of the attempt samples (#1330) an open
    attempt may still be called *live* (300). Past that the row is crash
    residue, not a running task - a dead worker must never keep an incident
    alive.
``TASK_PERFORMANCE_REGRESSION_FACTOR``
    How much worse the measured p95/slot cost must be than its baseline
    before it is a regression (2.0).
``TASK_PERFORMANCE_SPIKE_SHARE``
    The share of window samples which may sit beyond the class' own *old* p95
    before a moved p95 counts as a regression (0.10). With the middle of the
    window unmoved and that share inside the allowance, the moved p95 is an
    isolated spike - a ``completed_slow`` verdict, never a regression as well.
``TASK_PERFORMANCE_REGRESSION_MIN_BASELINE_SECONDS``
    The shortest baseline duration worth a ratio at all (1.0). Multiplying
    a sub-second baseline is how false precision gets invented.
``TASK_PERFORMANCE_MAX_CLASSES``
    Task classes one fire may judge (200); more answer ``truncated``,
    because a storm of classes is a capacity question for #1324, not a
    thousand incidents.
``TASK_PERFORMANCE_MAX_VERDICTS_PER_FIRE``
    Incidents one fire may publish (25), the same bound the watchdog of
    #1320 holds itself to.
``TASK_PERFORMANCE_COVERAGE_MIN_STAMPED``
    Share of stamped attempts still acceptable before coverage reports
    (0.5).
``TASK_PERFORMANCE_ABANDON_STALE_HOURS``
    The margin past the abandon grace before still-unresolved attempts become
    a coverage verdict (6). Everything older counts, down to the retention
    horizon of the samples - a row which went stale between two fires is never
    forgotten.
``TASK_PERFORMANCE_STALE_AFTER_HOURS``
    A class whose last terminal sample is older than this answers
    ``no_data`` rather than a stale ``healthy`` (72).
``TASK_PERFORMANCE_POLICY``
    The per-class policy map, empty by default. Keys are the full celery
    task name or ``queue:<name>``; values override the defaults:

    .. code-block:: python

        TASK_PERFORMANCE_POLICY = {
            # expected heavy work: no absolute budget, but a 4x p95 move
            # is still a regression, and up to a third of its samples may
            # exceed whatever it does run
            "registry.tasks.harvest.run_harvesting": {
                "regression_factor": 4.0,
                "spike_share": 0.34,
            },
            # a class which is allowed to run for hours on purpose
            "queue:harvest-import": {
                "budget_seconds": 900,
                "long_running_seconds": 7200,
            },
            # silenced entirely: it answers no incident and no regression
            "system.tasks.delete_old_slow_request_dumps": {"disabled": True},
        }

A policy is a *budget*, never a status: silencing a class says nobody is
being called about it, not that it is healthy. ``TASK_PERFORMANCE_POLICY``
merges over ``TASK_PERFORMANCE_POLICIES`` (the env-friendly JSON form,
``{"<task>": {...}}``) so an operator can ship a policy without a settings
patch, and an unknown task name in either is simply unused - a typo costs a
missing override, never a failed boot.

Verdicts, incidents and their lifecycle
=======================================

Every verdict of a fire is returned as a dict and logged; the actionable
ones become incidents through ``notify.incident_reporting``:

- codes start with ``taskperf_`` and hold their own namespace beside the
  operation and watchdog families of #1320: ``taskperf_completed_slow``,
  ``taskperf_regression``, ``taskperf_long_running``, the three coverage
  codes ``taskperf_coverage_unstamped``, ``taskperf_coverage_stale_open``,
  ``taskperf_coverage_disabled`` and the cadence code
  ``taskperf_schedule_overrun`` (#1827);
- the cadence reading of #1827 is the one condition which runs even with
  ``MRMAP_TASK_PERFORMANCE`` switched off: a beat schedule whose run does not
  fit its own interval is refused by the singleton lock and measures nothing,
  so it is invisible to every duration read and no other way of noticing it
  exists. Its numbers come from the same reachability read the capacity
  snapshot answers its schedule panel from (see
  ``capacity-snapshot.rst``), so a schedule is never *reachable* in one screen
  and an incident in another. Its summary names the measured p95, the interval
  the row fires on, the dropped fires and, when the attempts of the window
  allow it, the share of fires the lock refused.
- a verdict which names a ``BackgroundProcess`` publishes through
  ``publish_watchdog_verdict``, so its dedup key is
  ``<code>|<resource model>|<pk>`` and a slow harvest of one service is that
  service's incident, permission-filtered like every other one;
- every other verdict publishes through ``system_verdict`` with the key
  ``<code>|system`` - administrators only, as #1319 dictates. One shared
  system key per code is the truthful statement of "somebody's attempt of
  this kind is slow"; it never merges two services' stories, because a
  verdict which could name a resource does name one.

Dedup, severity lifecycle and resolution follow from #1319's manager: a
recurring condition raises the standing incident's ``occurrence_count``,
``warning`` escalates to ``error`` on the same code, ``resolve`` is the one
terminal transition. Resolution is evidence-side, not time-side:

- ``completed_slow`` of a resource resolves as soon as that resource's
  next bounded execution of the same task answers *within* its budget;
- ``long_running`` resolves when the attempt provably stopped - its own
  worker answered and no longer reports it (the completion race), a terminal
  row of the same identity exists (it completed), its row is past the abandon
  grace (a worker death, which ``coverage`` then owns) or retention removed it
  - and none of these fabricate a duration;
- ``regression`` resolves when the same comparison stops being a regression,
  which includes the honest case of the samples running out: a verdict
  whose evidence cannot be re-made is not evidence;
- ``coverage`` resolves when the telemetry reads complete again;
- ``schedule_overrun`` (#1827) resolves when the same beat row reads reachable
  again - the operator widened the interval or the run got cheaper - or when
  its row is gone from the live schedules. The reading which publishes it runs
  with the detector switched off, so its recovery runs there too: widening the
  interval must not require ``MRMAP_TASK_PERFORMANCE`` to be on before the
  incident closes. A fire whose reachability read itself failed resolves
  nothing of the family - an unread schedule is not a reachable one;
- every condition resolves when its evidence ages out of the window
  (``TASK_PERFORMANCE_STALE_AFTER_HOURS``) so a fixed problem cannot leave
  an incident standing forever;
- each code resolves on the answer of *its own* condition, never on the
  class' merged state: a class which stopped being slow but still regressed
  resolves its ``completed_slow`` and keeps its ``regression``;
- a fire which reaches no worker at all publishes nothing about current
  activity and resolves no standing ``long_running`` either. An unreachable
  fleet is unknown, and unknown must never be reported as conclusively
  healthy - nor as conclusively recovered.

The collector and the reporter are both outside the task's own path:
a detector that cannot read the database or reach the broker logs and
returns, so a detection outage never delays or fails an execution, and never
writes per task. Its writes are bounded by ``TASK_PERFORMANCE_MAX_VERDICTS_-
PER_FIRE``, and its incidents age out with the incident retention of #1319.

Runbook
=======

1. An incident says ``slow``: read the evidence block. ``measured`` names
   the window, ``samples`` the size, ``budget_seconds`` the policy that
   judged it, and ``observed_max_active_seconds`` what actually ran. The
   queue-wait numbers travel along, labelled: a verdict whose
   ``max_wait_seconds`` dwarfs its active seconds is a capacity finding for
   #1324, not a code problem. ``suspected_external_latency`` says so
   explicitly when the class' own queue wait moved past the baseline too,
   and names ``#1324`` as its owner; it is a hint read from the same
   samples, never a separate measurement and never a slow-task verdict.
2. A class you expected to be heavy reports: give it a policy (above), do
   not raise the global default - that silences the classes nobody has
   looked at yet.
3. ``regression`` reports: compare ``baseline_window`` and ``window`` in the
   evidence. The baseline is the class' own previous window, so a deploy
   between the two is the first hypothesis; a p50 that did not move while
   the p95 did is a tail, not a shift.
4. ``long_running`` reports with ``confidence: low`` (``measured: unknown``,
   ``reason: worker_unreachable``): the attempt is running longer than its
   budget but no worker confirmed it. Check the workers before the task;
   #1320's consumer verdict says whether any worker answers at all. Such a
   suspicion never becomes an incident, and a fire which reached no worker
   also keeps a standing ``long_running`` incident standing - the next fire
   which reaches its worker decides, with evidence.
5. ``coverage`` reports: telemetry is the problem, not the tasks. Check
   ``MRMAP_CAPACITY_TELEMETRY``, then the worker logs for the collector's
   own drop/error counters (#1330).
6. Nothing reports and everything is slow: detection is not a profiler. Use
   :ref:`celery-task-profiling` (#1389) on the named task to find out why.

See also: :ref:`celery-capacity-telemetry`, :ref:`celery-task-profiling`,
:ref:`capacity-snapshot`, :ref:`background-operations`, and the published
series and Grafana dashboard of the same epic at
:ref:`celery-task-performance-export`.
