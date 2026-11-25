.. _db-pool-memory:

=================================================
Database pool bounds and PostgreSQL memory
=================================================

Issue #1621, part of :ref:`runtime-memory-baselines` / epic #1612.

Every process of the deployment which is not Celery opens one psycopg
connection pool against PostgreSQL - the HTTP workers, the websocket server,
a management command. The pool was configured from three places that
disagreed: a module constant ``MAX_BACKEND_RESERVED_CONNECTIONS = 10`` no
code read, an environment variable of that name read with a default of 20,
and a ``min_size`` of 4 no knob could reach. #1615 has the rule for that
shape: a number an operator sets and the process reads differently is worse
than no knob, because it is the number an operator trusts.

What the bounds are now
=======================

One resolver in ``MrMap/settings.py`` owns both bounds. ``MRMAP_LOW_MEMORY``
- the same mode variable ``backend/.bash_scripts/process_defaults.sh`` uses
for the process shape - selects the pair together with it, because every
HTTP worker process carries its own pool and the shape and the reservation
are one decision: the shipped shape runs **4 workers x 4 threads** with
**4 reserved and 20 open** per process, the low-memory shape runs **1 worker
x 2 threads** with **1 and 4**. Explicit
``MIN/MAX_BACKEND_RESERVED_CONNECTIONS`` win over the mode; nonsense (not a
number, below 1, minimum above maximum) fails while the settings load. The
shipped production numbers are preserved unchanged. In a Compose deployment
the pair is set in ``docker/backend/.mrmap.env`` and is deliberately *not* a
``docker-compose.yml`` pass-through: an ``environment`` entry with the empty
fallback would shadow the value written into that file. Celery's processes
keep no pool at all - the old comment's unfinished transaction is the reason
and the tests keep it that way in a fresh interpreter.

What a bound actually costs
===========================

Three readings decide how to set the bounds; all three are measured below.

* **The pool is lazy.** Nothing in the boot path touches the database, so a
  process holds no pooled connection until its first request imports it -
  ``min_size`` is what a process holds *at rest once it has been used*, not
  what a freshly recreated container costs.
* **In the shipped shape the thread count, not ``max_size``, is what a pool
  grows to.** A gthread worker cannot put more than its ``GUNICORN_THREADS``
  requests into the database at once, so with 4 threads a pool of ``min 4``
  never needs a fifth connection no matter how many clients wait in the
  queue - the queue costs latency, not connections. The bound that then
  carries the deployment is the process count.
* **PostgreSQL pays per connection, and keeps connections.** Each pooled
  connection is a postmaster backend with its own memory; and psycopg keeps
  an over-minimum connection after its holder releases it (no ``max_idle``
  expiry is configured), so a spike leaves its footprint behind until the
  process restarts.

How the numbers below were produced
===================================

One disposable stack, the *deployed* shape - ``docker-compose.yml`` **without**
``docker-compose.dev.yml``, so gunicorn boots through ``startup.sh`` with no
``runserver`` and no watcher; a job-local override exposed 8001/8002 on
loopback and reset the victoria-logs host port; services were ``backend``
with its dependencies (postgis, redis, docker-api, victoria-logs) and no
celery container; the image was the local build of
``docker/backend/alpine.Dockerfile`` with ``MRMAP_PRODUCTION=True`` (the
prebuilt tag is published for the dev flavour only, so this measurement
built its own):

.. code:: console

    # confirm external host/container admission before starting Docker
    export COMPOSE_PROJECT_NAME=mrmap-agent-<issue>-<run-id>
    export COMPOSE_FILE="docker-compose.yml:<job-local override>"
    # one arm = recreate the backend for one shape, then per phase:
    env <arm vars> docker compose up -d --force-recreate backend
    python3 scripts/http_process_bench.py wait-ready --arm <arm> --out bench.jsonl
    scripts/stack_memory_profile sample --project <project> \
        --phase <arm>.idle --duration 60 --proc-interval 15 --out mem.jsonl
    scripts/stack_memory_profile sample --project <project> \
        --phase <arm>.api-load --proc-interval 15 --out mem.jsonl --during \
      "python3 scripts/http_process_bench.py load --arm <arm> --phase api-load \
        --endpoint /api/registry/keywords*3 --endpoint /api/registry/wms*2 \
        --endpoint /api/registry/harvesting/harvesting-jobs*1 \
        --requests 3000 --concurrency 16 --peer-endpoint /__cheap_peer__ \
        --peer-interval 0.25 --out bench.jsonl"
    scripts/stack_memory_profile sample --project <project> \
        --phase <arm>.post-load --duration 60 --proc-interval 15 --out mem.jsonl
    # between phases, from the postgis container:
    psql -At -c "SELECT application_name, state, count(*) \
                 FROM pg_stat_activity WHERE datname = current_database() \
                 GROUP BY 1,2"

Arms: ``default`` (shipped pair 4/20, 4 x 4), ``lowmem``
(``MRMAP_LOW_MEMORY=1``: pair 1/4, 1 x 2), ``pinned`` (shipped shape with an
explicit ``2``/``3`` - the knob proven live, and a ceiling below the thread
count seen), ``ws-hold`` (shipped shape plus 25 held authenticated
websockets over the API load - the one process whose database work runs on
a thread pool wider than its request depth). ``default`` ran twice, once
before and once after the other arms, as the drift control. Three honesty
notes the tables assume:

* the database is the **empty migrate-only floor** of the Compose entrypoint
  (the #1613 convention): every latency is a floor, not a capacity promise
  for filled data;
* the host is the usual agent cgroup on kernel 6.12 / docker 29.8.2 - the
  numbers are one host generation, and a second host re-runs the same
  commands rather than extrapolating;
* websockets share one reused knox token across the phase (#1450 caps live
  tokens per user at five).

Measured profile
================

The campaign ran on 2026-11-20 in the job-owned project
``mrmap-agent-1621-1620b`` on kernel 6.12.107+deb13-amd64 / docker 29.8.2,
from this branch's working tree (the pool code under review, bind-mounted).
Connection counts read ``pg_stat_activity`` for the application database
with the reading ``psql`` session removed; pool sessions report no
``application_name``, so the counts are deployment totals, not per-process
attributions. The stack ran no Celery container - the worker's own
connections are not in these numbers and are what the #1613 baselines
cover.

.. list-table:: Application connections visible to PostgreSQL
   :header-rows: 1

   * - arm
     - after boot + ready
     - 60 s idle, untouched
     - api-load (C 16)
     - right after
     - 60 s later
   * - default (4 x 4, pool 4/20)
     - 0
     - 0
     - 20
     - 20
     - 20
   * - lowmem (1 x 2, pool 1/4)
     - 0
     - 0
     - 3
     - 3
     - 3
   * - pinned (4 x 4, explicit 2/3)
     - -
     - -
     - 12
     - 12
     - -
   * - ws-hold (default shape, + 25 websockets)
     - 20 carried over
     - -
     - 25
     - -
     - 25 right after

``default`` ran twice, once before and once after the other arms; the two
agreed (20 connections in every phase, rps 179.1 and 181.4, p95 213 and
188 ms - the first arm's higher p99, 722 vs 388 ms, is the cold page cache
after a fresh recreate, and the second run is the warm control). The
``ws-hold`` phase continued on the still-running ``default`` container
rather than booting fresh, and is read as a delta: 20 to 25.

PostgreSQL's own cost per pooled connection, from the sampler's
per-container view and its per-process section inside the postgis
container:

.. list-table::
   :header-rows: 1

   * - phase
     - container p50
     - ``postgres`` processes
     - process anon p50
   * - default idle (no pool yet)
     - 155 M
     - 9
     - 6 M
   * - default api-load
     - 199 M
     - 29
     - 45 M
   * - default 60 s after load
     - 197 M
     - 29
     - 45 M
   * - lowmem idle (no pool yet)
     - 151 M
     - 9
     - 6 M
   * - lowmem api-load
     - 157 M
     - 12
     - 12 M

The 20 extra backends of the ``default`` phase are the 20 visible pooled
connections; ``(45 - 6) / 20`` and ``(12 - 6) / 3`` agree across two
independent arms at **about 2 M of anonymous RSS per pooled connection**,
and the footprint is held: the row after the load is the row of the load.

The web tier's own container (the process-shape half belongs to
:ref:`http-process-profiles` and matches it): idle 644 M with seven
gunicorn/uvicorn processes for the shipped shape against 299 M with four
for the low-memory one; under the load 723 M at 3.90 cores against 310 M
at 0.99 cores.

The HTTP reading on the empty-database floor:

.. list-table::
   :header-rows: 1

   * - arm
     - boot to first answer
     - rps
     - p50
     - p95
     - p99
     - cheap-peer p95
   * - default
     - 16.1 s
     - 179.1
     - 65.4 ms
     - 213.3 ms
     - 721.8 ms
     - 285.3 ms
   * - default2 (control)
     - 16.0 s
     - 181.4
     - 71.3 ms
     - 188.4 ms
     - 388.2 ms
     - 256.7 ms
   * - lowmem
     - 16.7 s
     - 51.7
     - 293.7 ms
     - 482.0 ms
     - 555.6 ms
     - 477.6 ms
   * - pinned (2/3)
     - 16.9 s
     - 178.9
     - 75.3 ms
     - 187.7 ms
     - 394.4 ms
     - 225.8 ms
   * - ws-hold (25 held)
     - -
     - 191.6
     - 71.4 ms
     - 178.2 ms
     - 334.8 ms
     - 18.3 ms

Every row served all requests with zero errors; the ``ws-hold`` row held
its 25 authenticated websockets across the phase.

What this means for the knobs
=============================

* **A pool connection is paid from a process's first request, and never
  given back.** Every arm booted and passed its readiness check with zero
  application connections, and every arm still held its full pool a minute
  after the load - psycopg expires an over-minimum idle connection only if
  a ``max_idle`` is configured, which this deployment does not do. The
  ``min_size`` of the shipped mode is therefore the deployment's **rest
  reservation: 20 connections** at about 2 M each server-side - five
  pool-capable processes (four HTTP workers, one websocket server) against
  a minimum of 4 each, which is the arithmetic the total matches, though
  the totals alone cannot attribute it per process. The low-memory mode's
  is 3.
* **In the shipped shape ``max_size`` is out of reach for the HTTP workers
  and reachable by the websocket server.** Sixteen queued clients against
  four threads per worker cost latency, not connections - the pool stayed
  at its minimum under 16-way load - while the ASGI server, whose database
  work runs on a thread pool wider than any request queue, grew the
  deployment's total from 20 to 25 with 25 websockets. Against the 100
  connections the stock PostGIS answers, a full stack with this ceiling
  leaves the headroom the #1613 baselines documented for Celery's unpooled
  sessions and the admin; the ceiling earns its keep only where threads are
  raised above 4.
* **An explicit ceiling binds exactly and does not bite before it has to.**
  The ``pinned`` arm capped the workers at 3 each: 12 visible connections -
  consistent with four workers bound at 3, an attribution the totals alone
  cannot offer the shipped arm - while serving the same rps as the
  control with a p50 of 75 against 65-71 ms and zero timeouts, because
  waiting threads queue on the pool and the empty floor's queries hold a
  connection for milliseconds. On filled data a ceiling below
  ``GUNICORN_THREADS`` is the region where a 30-second ``PoolTimeout``
  becomes possible; the knob is safe, but it is the deployment's job to
  keep the pair above its real concurrency, which is what these readings
  are for.
* **The shipped numbers are preserved and the preset follows the shape it
  belongs to**: 4 workers reserve 4 each (20 rest), one worker with two
  threads reserves 1 (3 rest with the websocket server), about 34 M of
  PostGIS anon plus the per-process overhead saved at rest, against the
  documented price of 3.5x throughput and 54% of the web tier's own
  memory, both measured in :ref:`http-process-profiles`.

Validation status
=================

What was measured here is the connection and PostGIS half on the empty
migrate-only floor of the Compose entrypoint, on one host generation; a
second host re-runs the commands above rather than extrapolating. Three
reading limits are named by their shape: pool sessions carry no
``application_name``, so the counts above are totals, not per-process; the
``ws-hold`` phase continued on a running container and is read as a delta;
and the stack ran no Celery container, so Celery's connection behaviour is
covered by unit tests and the epic's baselines, not by this table.

The tests keep the rest: the resolver's arithmetic, its mode spellings and
loud failures; that the running settings carry the resolver's answer rather
than a copy; and in a fresh interpreter that a Celery worker still imports
no pool - also under ``MRMAP_LOW_MEMORY`` - and Beat still imports only its
application name. The settings change adds no migration, and both test
stacks created and reused their isolated test databases through the pooled
connection settings (``--keepdb`` included) without conflict. Reconnect and
long-transaction behaviour are untouched by the change: ``CONN_HEALTH_CHECKS``
and the pool ``timeout`` of 30 s are the values the pool ran with before.
