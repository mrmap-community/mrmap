.. _celery-healthcheck-overhead:

=========================================
Celery healthcheck overhead investigation
=========================================

Issue #1616, part of :ref:`runtime-memory-baselines` / epic #1612.
This is a **draft investigation**. The deployed healthcheck and development
supervisors are unchanged. Adoption requires the live comparison below;
the unavailable-broker experiment alone cannot establish equivalent safety
or savings during normal operation.

Current behavior and candidate
==============================

``docker-compose.yml`` runs this command every 15 seconds, with a 10-second
Docker deadline, three retries and a 40-second startup grace period:

.. code:: sh

   celery -A MrMap inspect ping --destination "celery@$HOSTNAME" --timeout 2

The CLI loads the MrMap app and Django settings before contacting the
worker. The two-second argument bounds the reply wait, not the entire
startup or broker connection. Development adds a ``watchmedo auto-restart``
parent to both worker and Beat; production runs Celery directly.

The candidate is ``python -m system.worker_healthcheck``. It uses a fresh,
unconfigured Celery client, disables Django fixups, derives the Redis
address from the same ``REDIS_HOST`` / ``REDIS_PORT`` values as
``MrMap.settings.BROKER_URL``, and uses Celery's existing directed
``inspect(...).ping()``. It accepts only the local worker's ``{"ok": "pong"}``
reply. Missing replies, another worker's reply and broker errors fail.
Connection attempts have no connection retry loop and Redis socket timeouts
are two seconds; the outer 10-second deadline must remain in a trial.
Celery still imports a few small ``django.utils`` modules; Django's database,
settings and MrMap task registry are not initialized by the candidate.

This uses the public
`Celery inspect API <https://docs.celeryq.dev/en/stable/_modules/celery/app/control.html>`_
and adds no resident process. Both probes test the consumer's control loop
through the broker. Neither proves that every prefork task slot can execute
work. A PID check, Redis ``PING`` alone or a timer-written local heartbeat
would drop the consumer round trip and are insufficient replacements.

The candidate currently matches the stock Redis broker, default control
exchange/serializer and ``celery@<hostname>`` node naming. A deployment that
customizes those must explicitly match them before trialling it. Multiple
workers need unique hostnames/node names; preserve that uniqueness if
adding a Compose ``hostname`` override. The default healthcheck has the
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

Pending live comparison
=======================

Start only a disposable, isolated stack admitted by
``scripts/agent_capacity``. Use the prebuilt image and port/container-name
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

.. list-table:: Required evidence before replacing the default
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

Once the complete matrix shows lower cost and equivalent failure detection,
replace only the worker healthcheck command with the candidate, retaining
the current interval/deadline/retries/startup grace. Do not introduce a
resident watchdog to save imports, or remove development autoreload without
measuring and preserving its development behavior.

Validation status
=================

The isolated probe unit tests use the real Celery client with its broker
boundary mocked; a fresh interpreter verifies that the candidate does not
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

The live matrix, Redis command deltas, startup/loaded worker behavior and
watchmedo comparison remain pending. On 2026-11-19 the host admission gate
refused a new stack on memory (about 4 GiB host memory available, below its
16-GiB unrestricted-host requirement plus reserve). Complete the live matrix
on an admitted host before adopting the candidate.
