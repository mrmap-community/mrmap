.. _celery-healthcheck-overhead:

=========================================
Celery healthcheck overhead investigation
=========================================

Issue #1616, part of :ref:`runtime-memory-baselines` / epic #1612.
The worker healthcheck is now ``python -m system.worker_healthcheck``: the
comparison below ran on 2026-11-20 on an admitted host and the change followed
from it. The development supervisors are unchanged. The unavailable-broker
experiment at the end of this page is the draft's partial evidence - on its own
it could not establish equivalent safety or a saving during normal operation,
which the comparison below does.

The replaced check and the candidate
====================================

The check this page replaced ran every 15 seconds, with a 10-second Docker
deadline, three retries and a 40-second startup grace period:

.. code:: sh

   celery -A MrMap inspect ping --destination "celery@$HOSTNAME" --timeout 2

The CLI loads the MrMap app and Django settings before contacting the
worker. The two-second argument bounds the reply wait, not the entire
startup or broker connection. Development adds a ``watchmedo auto-restart``
parent to both worker and Beat; production runs Celery directly.

What runs now is ``python -m system.worker_healthcheck``. It uses a fresh,
unconfigured Celery client, disables Django fixups, derives the Redis
address from the same ``REDIS_HOST`` / ``REDIS_PORT`` values as
``MrMap.settings.BROKER_URL``, and uses Celery's existing directed
``inspect(...).ping()``. It accepts only the local worker's ``{"ok": "pong"}``
reply. Missing replies, another worker's reply and broker errors fail.
Connection attempts have no connection retry loop and Redis socket timeouts
are two seconds; the outer 10-second deadline is unchanged.
Celery still imports a few small ``django.utils`` modules; Django's database,
settings and MrMap task registry are not initialized by it.

This uses the public
`Celery inspect API <https://docs.celeryq.dev/en/stable/_modules/celery/app/control.html>`_
and adds no resident process. Both probes test the consumer's control loop
through the broker. Neither proves that every prefork task slot can execute
work. A PID check, Redis ``PING`` alone or a timer-written local heartbeat
would drop the consumer round trip and are insufficient replacements.

The probe matches the stock Redis broker, default control
exchange/serializer and ``celery@<hostname>`` node naming. A deployment that
customizes those must explicitly match them in the probe. Multiple
workers need unique hostnames/node names; preserve that uniqueness if
adding a Compose ``hostname`` override. The CLI check it replaced had the
same node-name constraint.

Profiler
========

``scripts/stack_memory_profile command`` extends the baseline tool with
short-lived command measurements. It executes the argument vector directly,
without a shell, and records each invocation's:

* exit code and whether the deadline killed it;
* elapsed and user + system CPU seconds;
* kernel peak RSS from Linux ``wait4`` (separate for each invocation);
* sampled peak PSS from ``/proc/<pid>/smaps_rollup``, or ``null`` if unreadable.

PSS sampling defaults to 10 ms and can miss shorter peaks. The child CPU
excludes the sampler's own CPU, but sampling perturbs elapsed time; use the
same cadence for both arms. Only the immediate child is sampled: pass the
actual executable, never a shell or a supervisor with descendants. The
existing ``sample`` command measures the complete stack and its supervisors
separately. Command stdout/stderr are discarded; inspect failures separately
before attributing them to the broker. Arguments are recorded, so pass
credentials through the environment rather than the command line.

Copy the tool into a **job-owned** worker container (it is not a production
runtime dependency), then run both arms there against that worker:

.. code:: sh

   docker compose -p "$COMPOSE_PROJECT_NAME" cp scripts/stack_memory_profile celery-worker:/tmp/stack_memory_profile
   MRMAP_MEASUREMENT_REVISION=$(git rev-parse HEAD)
   MRMAP_WORKER_HOSTNAME=$(docker compose -p "$COMPOSE_PROJECT_NAME" exec -T celery-worker hostname)
   docker compose -p "$COMPOSE_PROJECT_NAME" exec -T celery-worker \
     python /tmp/stack_memory_profile command --phase cli-idle --runs 20 \
       --revision "$MRMAP_MEASUREMENT_REVISION" --out /tmp/probes.jsonl -- \
       celery -A MrMap inspect ping --destination "celery@$MRMAP_WORKER_HOSTNAME" --timeout 2
   docker compose -p "$COMPOSE_PROJECT_NAME" exec -T celery-worker \
     python /tmp/stack_memory_profile command --phase candidate-idle --runs 20 \
       --revision "$MRMAP_MEASUREMENT_REVISION" --out /tmp/probes.jsonl -- \
       python -m system.worker_healthcheck
   docker compose -p "$COMPOSE_PROJECT_NAME" cp celery-worker:/tmp/probes.jsonl ./probes.jsonl
   scripts/stack_memory_profile report --in probes.jsonl

The CLI destination above is read from the selected container;
select each container separately when testing distinct nodes. Repeat batches in alternating order
to reduce cache/order effects, retain first-run results as startup samples,
and keep all individual runs. A nonzero command exits the profiler with
status 1 **after** writing its results. This is expected in failure phases;
inspect recorded exits and timeouts rather than treating the profiler's
status as a test verdict.

Reproducing the comparison
==========================

Start only a disposable, isolated stack admitted by the operator or external
execution environment. Use the prebuilt image and port/container-name
resets in :ref:`development-prebuilt-images`, unique project state, and the
cleanup/ownership rules in ``AGENTS.md``. Register cleanup before creating
resources, retain the same Compose files and exact project name, and remove
only that project's verified containers, networks and disposable volumes.
The developer's stack is not a benchmark fixture.

The command profiler must run inside the worker container so that Docker
client startup is excluded. Keep a parallel whole-stack phase with the
baseline ``sample`` tool to capture transient cgroup memory and total CPU.
Use a separate JSONL file for each environment; record the source commit,
image digest, Compose files, pool, concurrency, workload, sample interval
and OOM counters. Do not infer PSS from RSS or sum shared RSS as physical RAM.

.. list-table:: Evidence this page retains for each phase
   :header-rows: 1
   :widths: auto

   * - phase
     - evidence to retain for both probes
   * - cold start and warm idle
     - first-run imports, per-probe CPU/wall/RSS/PSS, cgroup peak and health transition
   * - loaded prefork worker
     - same checks while the same fixture task batch runs; task throughput and latency, timeouts and false unhealthy results
   * - one worker, then two distinct worker nodes
     - both local destinations pass; remove/freeze one main consumer and verify the healthy peer cannot mask it
   * - Redis stop/pause and recovery
     - nonzero or timeout within 10 seconds while unavailable; directed replies recover after Redis resumes
   * - stopped or unresponsive consumer
     - nonzero after stopping or SIGSTOP of the Celery main process; resume in cleanup; a live supervisor/PID alone must not pass
   * - development supervisors
     - per-process RSS/PSS and cgroup CPU for watchmedo + worker/Beat at idle, file-change restart and loaded phases; compare production without autoreload

For Redis command overhead, retain ``redis-cli INFO commandstats`` before
and after each arm against the job-owned broker. Do not reset global stats.
Subtract a matched no-probe workload window: under load, the delta also
contains task traffic. Retain per-command deltas and the completed probe
count; ``MONITOR`` is unnecessary and can expose task payloads. Redis command
counts and a successful consumer reply cannot be measured with no broker.

Run failure injection exclusively against verified job-owned resources.
SIGSTOP the main consumer, not a task slot or the watchmedo parent; execute
probes using ``exec`` while that process is stopped. For two workers, stop
only one. Keep ``SIGCONT`` / broker resume in cleanup even on failed checks.
For supervisor PSS, read the selected process's ``smaps_rollup`` inside the
container; record an unavailable reading explicitly if permissions deny it.

The rule for changing the file: replace only the worker healthcheck command,
retaining the current interval/deadline/retries/startup grace, and do not
introduce a resident watchdog to save imports or remove development
autoreload without measuring and preserving its development behavior. The
comparison below met that rule and the section "Adopted" records the change.

Live comparison
===============

The matrix ran on 2026-11-20 in the job-owned project
``mrmap-agent-1616-1620``, admitted by the historical external capacity check
for a stack, started from ``docker-compose.yml``,
``docker-compose.dev.yml`` and ``docker-compose.prebuilt.yml``:

* source revision ``ebf5a0ab2121461235b3cd1a88ae3de4182dd40c`` - this branch
  with ``origin/develop`` merged in;
* image ``ghcr.io/mrmap-community/mrmap-backend-dev:fcbd17dfa3b5``, digest
  ``sha256:5964ac35194c5f9c75a7aa30efe65cc37bb17a1370d5d2468dd07e42bb0861dd``;
* Python 3.15.2 on kernel 6.12.107+deb13-amd64;
* prefork pool, ``CELERY_WORKER_CONCURRENCY=6``, and the worker's cgroup
  reported ``oom_kill 0`` over the whole campaign;
* the development flavour, so the worker ran under ``watchmedo auto-restart``
  - the supervisor's own cost is measured below;
* the deployment's syslog target is unreachable in a disposable stack and its
  handler is skipped identically by both arms, which removes the confounder
  the draft's first diagnostic had to discard.

Every probe ran inside the worker container with the profiler's 10-second
deadline and 10 ms PSS cadence, identical for both arms. During the cost
phases the container's own healthcheck was disabled so that only the measured
probe ran; the phases which measure the check as deployed used it as
configured. The load drivers ran in their own one-off containers, so the
measured container held the worker and the probe and nothing else. The two arms
are named as in the evidence files: ``cli`` is the command this page replaced,
``candidate`` the probe which runs now.

Two load shapes were measured, and which one matters follows from what the
probe touches: a task which blocks a prefork child cannot starve the control
loop, because that loop runs in the master process. The load which can delay a
reply is therefore queue and broker pressure, not a busy slot. The first shape
is exactly that pressure - 1500 retention-sweep messages queued at once and
draining, the load the whole-stack phase below measures at 2.09 cores. The
second is the project's work as it normally arrives: 35 rounds of filling the
job history and dispatching the retention sweep over it, one after another.
That keeps a message in flight across the whole window but holds the worker's
own work at 2 % of the wall clock; it is listed because it is the realistic
shape, not because it stresses anything.

.. list-table:: p50 per phase; every individual run is in the linked JSONL
   :header-rows: 1
   :widths: auto

   * - phase
     - probe
     - CPU seconds
     - elapsed seconds
     - peak RSS (MiB)
     - sampled peak PSS (MiB)
     - exits / deadline hits
   * - warm idle, 40 runs in two batches run in opposite order
     - current CLI
     - 2.565
     - 2.668
     - 68
     - 59
     - 0 for all forty / zero
   * - warm idle, same batches
     - candidate
     - 1.914
     - 1.992
     - 51
     - 43
     - 0 for all forty / zero
   * - 1500 queued messages draining, 10 runs
     - current CLI
     - 2.815
     - 2.966
     - 68
     - 59
     - 0 for all ten / zero
   * - 1500 queued messages draining, 10 runs
     - candidate
     - 2.012
     - 2.105
     - 51
     - 43
     - 0 for all ten / zero
   * - sustained sweeps over re-filled history, 8 runs
     - current CLI
     - 2.637
     - 2.759
     - 68
     - 56
     - 0 for all eight / zero
   * - sustained sweeps over re-filled history, 8 runs
     - candidate
     - 1.965
     - 2.040
     - 51
     - 42
     - 0 for all eight / zero
   * - Redis paused
     - current CLI
     - 2.407
     - 10.012
     - 68
     - 59
     - killed by the deadline for all five
   * - Redis paused
     - candidate
     - 1.821
     - 3.880
     - 51
     - 43
     - 1 for all five / zero
   * - consumer held with ``SIGSTOP``
     - current CLI
     - 2.532
     - 4.657
     - 68
     - 59
     - 69 for all five / zero
   * - consumer held with ``SIGSTOP``
     - candidate
     - 1.872
     - 4.008
     - 51
     - 43
     - 1 for all five / zero
   * - Redis resumed / ``SIGCONT``
     - current CLI
     - 2.593
     - 2.722
     - 68
     - 59
     - 0 for all three / zero
   * - Redis resumed / ``SIGCONT``
     - candidate
     - 1.857
     - 1.924
     - 51
     - 43
     - 0 for all three / zero

Raw invocations:
:download:`celery-healthcheck-live-idle.jsonl <evidence/celery-healthcheck-live-idle.jsonl>`,
:download:`celery-healthcheck-live-load.jsonl <evidence/celery-healthcheck-live-load.jsonl>`,
:download:`celery-healthcheck-live-failure.jsonl <evidence/celery-healthcheck-live-failure.jsonl>`,
:download:`celery-healthcheck-live-multi-node.jsonl <evidence/celery-healthcheck-live-multi-node.jsonl>`.

The two idle batches were run in opposite order - CLI first, then candidate
first - and agree within 0.08 seconds of the median, so neither cache warmth
nor order moved the result. The first probe of each batch, which is the first
one Docker runs after the 40-second start period, is in the same range as its
batch: 2.47 CPU s for the CLI and 1.83 for the candidate in one order, 2.42 and
1.98 in the other, with the same peaks. No separate fresh-container cold-start
phase was run; the interpreter warm-up such a phase would add on top is what
the no-broker experiment at the end of this page measures, where the CLI arm
spent 1.390 CPU seconds of imports against the probe's 1.071.

What the difference is worth
============================

The interval is 15 seconds, so a worker answers 5760 probes a day. At the idle
medians the CLI arm costs 0.65 CPU-seconds more per probe than the candidate:
**about one CPU-hour per worker per day**. The peak a single probe touches
falls from 68 to 51 MiB resident and from 59 to 43 MiB proportional shared
size - PSS is the quantity :ref:`runtime-memory-baselines` measures, because
the shared pages of a container are paid once. The saving holds under both
load shapes: the CLI arm's median rose from 2.565 to 2.815 CPU seconds while
1500 messages drained and the candidate's from 1.914 to 2.012, and both sat
slightly above idle again during the sustained sweeps (2.637 and 1.965). The
difference is not an idle-cache artefact, and it is not a peculiarity of the
heavy shape either.

Neither peak stays around: both arms are short-lived commands and neither
leaves a process behind. That is the acceptance condition of #1616 - a cheaper
check may not be paid for with an always-resident watchdog. The candidate
imports Celery's control client and nothing of the Django application; the
development stack's ``watchmedo`` supervisor, which *is* always resident, is
measured below and belongs to neither arm.

Failure detection
=================

Both arms reported unhealthy in both failure modes and answered again after
the fault was removed, so the candidate is not safer by failing less. The
direction that differs is the margin. On this host the CLI arm spent its whole
10-second budget and was killed by it in every run while Redis was paused (exit
code 9 at 10.012 s). The deployed ``timeout: 10s`` *is* that budget, so with
the CLI arm there is no room between "the check answered" and "Docker killed
the check"; the draft's host measured 7.4 s for the same path, the same event a
little further from the edge. The candidate reported the same loss in 3.88 s,
and the failure path is where a healthcheck's cost actually matters - a check
that only ever runs against a healthy worker is not being tested.

At container level, with the healthcheck deployed as configured (interval 15
s, three retries, 40 s start period), a consumer held with ``SIGSTOP`` turned
the worker container **unhealthy after 61 s** with the current CLI check and
**after 58 s** with the candidate, and the container was healthy again **18 s**
and **16 s** respectively after ``SIGCONT``. The transition is a property of
the interval and the retry count, not of the arm: the candidate is at least as
fast in both directions and, unlike the CLI arm, never needs the deadline to
decide.

Two worker nodes
================

Two ``celery-worker`` containers in one stack, each with its own healthcheck
and its own ``celery@$HOSTNAME`` destination:

* both containers answered for their own destination (CLI 3.81 s and 3.46 s,
  candidate 2.52 s and 2.60 s, exit 0);
* stopping one container left the survivor **healthy** for both arms (CLI 3.21
  s, candidate 2.14 s) while the stopped container's own health went
  unhealthy - a missing peer does not make a working node look broken;
* with the **peer alive**, holding the local node's consumer with ``SIGSTOP``
  made both arms exit nonzero (CLI 69 at 4.82 s, candidate 1 at 4.27 s), and
  both answered again after ``SIGCONT``.

The last point is the one that could have made a cheaper check unsafe, and it
holds for a reason visible in the source: the CLI asks ``--destination
celery@$HOSTNAME`` by name, and the candidate passes its own node name as the
destination *and* accepts a reply only under that key
(``system/worker_healthcheck.py``). A neighbour's pong cannot vouch for a stuck
node in either arm.

The always-resident supervisor
==============================

``watchmedo auto-restart`` is PID 1 of the development worker container. Over
60 seconds at idle it used **0.5 % of one core** and held **13.3 MiB** of PSS;
the supervised Celery master held 88-90 MiB. A watched file change brought the
worker back within **2.46 s**, and a worker terminated with ``SIGTERM`` was
back within **16.21 s**.

Two facts follow. The supervisor's entire resident cost is about a quarter of
one CLI probe's peak - if the fleet's health cost is the concern, the probe is
the larger number. And nothing restarts a worker which *hangs* instead of
exiting: the supervisor restarts exits and file changes, Docker only reports an
unhealthy container. A consumer-directed healthcheck is the only link in the
chain that sees that case, which is why neither arm is replaced by a PID or a
``PING`` check.

Redis commands per probe
========================

``redis-cli INFO commandstats`` around 20-run windows per arm with a matched
no-probe window of the same length subtracted (the idle stack itself asks
**5.64 commands per second** of its broker): the current CLI probe costs
**60.7 commands**, the candidate **47.2**. The per-command shape is the same -
``llen``, ``ping``, ``MULTI``/``EXEC``, ``DEL``, ``HELLO``, ``PUBLISH`` - the
candidate simply opens fewer connections. Command counts cannot be measured
against a paused broker, which is why the failure phases carry none.

The whole stack
===============

The baseline ``sample`` command in parallel: the stack's cgroup sum moved from
**p50 3766 M / peak 3807 M at idle** to **p50 3896 M / peak 3992 M** while 1500
messages drained, with the worker container going from 661 M to 700 M and its
CPU from 0.17 to 2.09 cores. The load driver appears as its own container
(``…-celery-worker-run-…``, 137-192 M), which is the point of running it
outside: the worker's numbers contain the worker.

Adopted
=======

The matrix shows lower cost on every measured path, equivalent failure
detection in both failure modes and at container level, and no new resident
process. ``docker-compose.yml`` therefore runs the candidate for
``celery-worker``, with ``interval: 15s``, ``timeout: 10s``, ``retries: 3`` and
``start_period: 40s`` unchanged. Beat's healthcheck is untouched - it was not
measured here. The development autoreload is untouched, and no resident
watchdog was introduced.

The assumptions the probe makes about the broker, the control exchange and
the node name are the ones the CLI check it replaced already made, so a
deployment which customizes any of them has to match them in the probe - the
same requirement it already had, as the section above spells out.

Validation status
=================

The live comparison above is what the adoption rests on: warm idle in both
orders, two load shapes, the unavailable broker, a held consumer, two worker
nodes, the supervisor and the whole-stack samples, with every individual run in
the evidence files. Three rows of the table were not run and are not claimed:
Redis's container was made unavailable with a cgroup pause rather than stopped
(which keeps its address resolvable, the confounder the draft's discarded
diagnostic had), the supervisor's cost was measured at idle and across its own
restarts but not during the loaded phases, and no production stack without
autoreload was started. The last two would move the supervisor's numbers, not
the probe's.

The isolated probe unit tests use the real Celery client with its broker
boundary mocked; a fresh interpreter verifies that the probe does not
initialize MrMap/Django's database. These tests also cover wrong-node,
missing and error replies, local hostname selection and credential-free
failure output. Profiler tests cover independent RSS peaks, CPU accounting,
missing PSS, timeout cleanup and failure-result persistence.

Unavailable-broker experiment (partial evidence)
================================================

On 2026-11-19, five fresh invocations of each probe ran in one disposable
container, using the admitted **process** budget, not a new service stack.
The container had no network, no broker/worker/PostgreSQL, a 512-MiB memory
ceiling and 64-PID limit. It used backend image
``ghcr.io/mrmap-community/mrmap-backend-dev:fcbd17dfa3b5`` with Python 3.15.2,
on kernel 7.0.0-43-generic / Docker 27.2.1. Source was the draft working tree
based on ``43fb1f04f``; the evidence records the candidate source digest.
The root/source mounts were read-only, with private writable tmpfs runtime
directories. Redis and syslog addresses were explicitly ``127.0.0.1`` so
unavailable service DNS could not dominate initialization. The 10-second
deadline and 10-ms PSS sampling were identical for both arms.

.. list-table:: No-broker path only, p50 of five invocations
   :header-rows: 1
   :widths: auto

   * - command
     - CPU seconds
     - elapsed seconds
     - peak RSS (MiB)
     - sampled peak PSS (MiB)
     - exits / timeouts
   * - current CLI
     - 1.390
     - 7.447
     - 68
     - 64
     - 69 for all five / zero
   * - candidate
     - 1.071
     - 1.111
     - 50
     - 46
     - 1 for all five / zero

Raw invocation results:
:download:`celery-healthcheck-unavailable.jsonl <evidence/celery-healthcheck-unavailable.jsonl>`.
Both checks reported unhealthy. This establishes lower cost for this
controlled unavailable-broker path only. It does **not** measure an
established worker losing its broker, successful replies at idle/load,
Redis command counts or supervisor overhead. An earlier diagnostic with an
unresolvable syslog hostname spent its 10-second budget in startup; those
confounded runs were discarded rather than attributed to Redis.

What this experiment left open - the live matrix, the Redis command deltas,
the loaded worker and the watchmedo comparison - is what the sections above
measured. On 2026-11-19 the host admission gate had refused a new stack on
memory (about 4 GiB available, below its 16-GiB unrestricted-host requirement
plus reserve), which is why the draft published only this path; the matrix ran
on 2026-11-20 on an admitted host.
