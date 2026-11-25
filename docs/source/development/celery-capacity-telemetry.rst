.. _celery-capacity-telemetry:

================================
Celery task occupancy telemetry
================================

Epic #1324 ("why is a scheduled task not running?") could only answer *which*
schedules exist. Issue #1330 adds the missing measurement layer: how long the
workers are actually busy with an execution, and how long a message waited in
the broker before a worker picked it up. Issue #1326 builds the capacity
snapshot endpoint on top of what is described here; this document describes the
measurement source and nothing else.

The promise of #1330 is deliberately narrow. Every number answered by this
layer is one a real worker process measured for itself, it is labelled as
such, and states that were *not* measured stay unknown instead of being filled
in with a guess. A capacity reader can present these numbers as
``measured_worker`` evidence and must not present them as a global prior; the
source and sample size travel with every answer.

Three durations, never added together
=====================================

One execution has up to three different "times", and collapsing them is what
made #1324 unanswerable:

``wait_seconds``
    Broker wait: wall time between the publish of the message and the start of
    the attempt. Measured from the ``mrmap-published-at`` message header (see
    below), so it is the wait of exactly this attempt; ``Task.retry``
    re-publishes through ``before_task_publish`` and the re-published message
    is stamped anew, which keeps a retry chain's waits separate. Unstamped
    messages (protocol v1, foreign publishers, eager ``apply()``) answer
    ``None`` — an unknown wait, not a zero one.

``active_seconds``
    Worker slot occupancy: monotonic time between ``task_prerun`` and the
    terminal signal of the attempt. It includes any HTTP or database waiting
    the task body itself does — that time *is* worker occupancy — but it never
    includes broker time. A 4 h backlog in front of a 2 s task contributes 2
    occupied slot-seconds and one queue wait sample of ~4 h: two separate
    answers, the acceptance example of #1330.

no third duration is measured
    Time between "beat decided to fire" and the publish, or time a message sat
    after a ``revoke``, is not measured here. Anything #1326 wants to know
    beyond these two numbers has to be measured by that issue, not inferred
    from these.

The attempt table
=================

One row per observed attempt, written by the worker process that observed it:
``system.models.CeleryTaskAttempt`` (migration ``system.0002_celery_attempt_samples``).

================================  ===========================================================================
column                            meaning
================================  ===========================================================================
``task_id`` / ``attempt_no``      the attempt's identity: celery's task uuid and ``request.retries``
``task_name``                     the celery task name, truncated to 255
``queue``                         routing key the message was consumed from
``worker``                        ``hostname`` of the executing process
``root_id`` / ``parent_id``       celery's own correlation ids (chain / fan-out parent)
``periodic_name``                 beat's ``periodic_task_name`` header, when the fire came from beat
``published_at``                  parseable publish stamp, else ``None``
``started_at`` / ``finished_at``  wall times of prerun and of the terminal signal
``active_seconds``                measured slot occupancy, ``None`` while open
``wait_seconds``                  measured broker wait, ``None`` when unstamped
``outcome``                       ``""`` while open; else ``success`` / ``failure`` / ``retry`` / ``revoked``
``quality``                       list of quality flags, see below
``recorded_at``                   when this row was written
================================  ===========================================================================

``(task_id, attempt_no)`` is the identity because celery's ``Task.retry`` keeps
the same task uuid across retries — verified against the celery 5.7 source —
so only the attempt counter separates attempt 0 from attempt 1 of the same
logical task id.

The table is insert-only. Two *partial* unique indexes give the deduplication
semantics:

``unique_open_celery_attempt``
    at most one row per identity with ``outcome = ''`` — a duplicate start
    delivery never accumulates a second open row.
``unique_terminal_celery_attempt``
    at most one row per identity with ``outcome != ''`` — whichever process
    writes the finish first wins; a second terminal write is dropped with
    ``ON CONFLICT DO NOTHING``, never counted twice.

This is also why an *open* row and a *terminal* row for one identity can
coexist: the open row was written by an earlier flush while the attempt was
still running; the terminal row records how it ended. Readers therefore
aggregate durations from terminal rows only, and count open rows without a
terminal counterpart as *uncertain* observations, never as durations.

Quality flags
=============

``redelivered``
    The same identity started a second execution — before its first end
    (concurrent duplicate delivery, merged into one sample) or after it
    (a broker redelivery of a finished task; the measured terminal sample
    stays valid). A worker crash that loses a message is *not* visible here;
    the broker decides redelivery, so the flag means "this identity ran more
    than once in the eyes of at least one worker".
``abandoned``
    Set by the nightly sweep on an open row that never got its end within the
    abandon grace (default 48 h): crash residue the worker can no longer
    close. Open rows within the grace are simply still running.

Unstamped and open states are not flags — both are derivable from the columns
(``published_at IS NULL``, ``outcome = ''``), and a flag that duplicates a
column is a flag that drifts.

Who collects, and what a worker pays
====================================

Collection is gated on ``worker_process_init`` — the signal celery fires once
per prefork child (and once for solo/gevent). Web processes, the test runner,
`manage.py` shells and beat's scheduler process never buffer or write task
signals; the old-style argv sniff was rejected because any command line that
merely mentions ``celery`` and ``worker`` passes it (``manage.py test
tests.django.test_celery_worker_queues`` included — caught by the unit tests
of this very feature).

A worker's per-attempt cost is bounded by construction:

* signals only touch an in-process dict keyed by ``(task_id, attempt_no)``;
  nothing is written per task,
* a flush is one ``INSERT ... ON CONFLICT DO NOTHING`` for the whole batch,
  triggered at ``CAPACITY_TELEMETRY_FLUSH_THRESHOLD`` buffered attempts or
  ``CAPACITY_TELEMETRY_FLUSH_SECONDS`` after the last flush, and at worker
  process shutdown,
* the buffer holds at most ``CAPACITY_TELEMETRY_BUFFER_LIMIT`` attempts; over
  the limit the oldest *open* observations are dropped, counted in
  ``collector_stats()["dropped"]`` and logged with a rate limit — a wave that
  outruns the writer shows up as dropped samples, not as a blown worker,
* a failed flush silences the collector for
  ``CAPACITY_TELEMETRY_RETRY_COOLDOWN_SECONDS`` instead of retrying per task:
  when the database is the thing that is down, the collector must not become
  a write storm on top of it,
* no signal handler ever raises: any failure degrades to a debug log line.

The ``HighVolumeWaveTests`` unit test pushes 43 000 attempts through the
collector and prints the measured cost for this documentation to cite; on the
development machine of the implementation run it measured **0.24 ms per
attempt** (10.24 s for the wave, buffer never over its limit). Treat that as
an order-of-magnitude calibration of one machine, re-measure on real
deployments.

Keeping the table bounded
=========================

``system.tasks.bound_task_attempt_samples`` runs every hour (beat row "bound
celery task attempt samples", five minutes after the hour) and, in order:

1. flags open attempts older than ``CAPACITY_TELEMETRY_ABANDON_GRACE_HOURS``
   with ``abandoned`` — the grace must stay above the longest task the
   deployment runs on purpose, or a long harvest run would be declared dead
   while it runs,
2. deletes terminal rows older than ``CAPACITY_TELEMETRY_RETENTION_DAYS``,
3. while the table is over ``CAPACITY_TELEMETRY_MAX_ATTEMPTS`` rows, deletes
   the oldest terminal rows in batches.

Open rows are never deleted by age or cap — abandoning them (step 1) is the
only judgment the sweep is allowed to make about them.

Reading: the sample API
=======================

``system.capacity_measures`` is the module #1326 reads; nothing in this layer
answers an HTTP endpoint. Every function is one bounded query on the
(queue, started_at) index for a window, and the labelling rules are the API:

* durations are ``None`` when nothing was measured in the window — "nothing
  measured" and "measured zero" are different statements;
* every answer carries ``source="measured_worker"``, the window and the
  sample counts, so a snapshot can carry its evidence class;
* ``uncertain`` reports ``open_without_end`` and ``abandoned`` counts —
  partial evidence is reported as such, never summed into occupancy;
* queue wait percentiles (p50/p95/max/mean) read only stamped terminal
  attempts; ``queue_wait["samples"]`` says how many attempts that is, and the
  share of stamped attempts is part of the coverage answer.

``system.capacity_topology`` observes the broker (``inspect active_queues`` and
``ping``) with a 1 s bound and caches the shared answer for
``CAPACITY_TOPOLOGY_CACHE_SECONDS`` so a snapshot request never pays for a
broadcast; a deployment without a reachable broker gets an answer saying
"topology unknown" (fail closed) instead of an empty one pretending to be a
statement.

The read-only Django admin (system → "Celery attempt samples") lists rows for
operator questions; nothing is editable there because nothing may rewrite a
measured sample.

Settings
========

==========================================  ==========================================================================
``MRMAP_CAPACITY_TELEMETRY``                environment kill-switch; any of ``off``/``0``/``false`` disables stamping
                                            and collecting everywhere
``CAPACITY_TELEMETRY_COLLECT_ANY_PROCESS``  test seam only — deployments leave it False
                                            ``CAPACITY_TELEMETRY_BUFFER_LIMIT`` / ``..._FLUSH_THRESHOLD`` /
                                            ``..._FLUSH_SECONDS`` / ``..._RETRY_COOLDOWN_SECONDS`` the per-worker
                                            bounds above ``CAPACITY_TELEMETRY_RETENTION_DAYS`` / ``..._MAX_ATTEMPTS``
                                            / ``..._ABANDON_GRACE_HOURS`` the sweep's bounds
                                            ``CAPACITY_TOPOLOGY_CACHE_SECONDS`` / ``..._TIMEOUT_SECONDS`` the broker
                                            observation bounds
==========================================  ==========================================================================

What belongs to #1326 and not here
==================================

* the snapshot endpoint and its authentication,
* demand-side counts (43k schedules, per-schedule next-fire bookkeeping),
* any aggregation across the ``measured_worker`` source class (historic
  priors, vendor defaults) — this layer is one source class, and it is the
  only one #1330 measures.

See also: :ref:`celery-queues`, :ref:`background-jobs`,
:ref:`development-agent-capacity`.
