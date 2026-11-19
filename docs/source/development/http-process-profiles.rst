.. _http-process-profiles:

============================================================
HTTP and websocket process shapes: modes, measures, preload
============================================================

.. sidebar:: Issue #1617 · epic #1612

    Part of epic #1612 (runtime memory), phase V1 · measurement and
    selection. The WSGI/ASGI split this page keeps in place is #1032; the
    sampler and the reading rules for every RAM number are
    :ref:`runtime-memory-baselines` (#1613), which listed the deployed
    gunicorn shape as *not measured at all* - this page is that
    measurement, arms labelled the way that page labels its phases.
    Environment knobs: :ref:`development-environment` ("The web tier").
    Offline checks: ``python3 scripts/test_http_process_bench.py``
    (no docker, no network, run by ``scripts/check_repo_tooling.sh``).

MrMap's deployed backend answers two kinds of request that want opposite
things of a server - every view is sync and holds its worker for the
duration of one request, websockets are idle and long lived - so the
container runs two gunicorns (#1032): a ``gthread`` HTTP server on :8001
and one Uvicorn (ASGI) worker on :8002 behind ``/ws``. This page answers
the questions #1617 asks about that shape: what the worker and thread
counts are worth under a named workload, what a **low-memory mode** may
therefore trade, whether ``gunicorn --preload`` is safe here and what it
buys, and what must *not* break while measuring all of it (inherited
database connections, dropped websockets, a debug surface, a slower boot).
None of it changed the shipped default shape: production still boots 4
workers x 4 threads and one websocket worker, exactly as before.

The shape a container boots with resolves in one file
=====================================================

``backend/.bash_scripts/process_defaults.sh`` is the single source of the
web tier's numbers: both startup scripts source it, docker-compose.yml
passes every ``GUNICORN_*`` knob and the mode switch through untouched, and
an explicit value always wins over the profile - so the shape is answered
by one file whether the container came from compose, from ``docker run``
or from a test. Three shapes matter:

.. list-table::
   :header-rows: 1
   :widths: auto

   * - shape
     - selected with
     - HTTP workers x threads
     - WS workers
     - preload
   * - production (shipped default)
     - unset
     - 4 x 4
     - 1
     - off
   * - low-memory mode (#1617)
     - ``MRMAP_LOW_MEMORY=1``
     - 1 x 2
     - 1
     - off
   * - explicit
     - ``GUNICORN_WORKERS`` / ``GUNICORN_THREADS`` / ``GUNICORN_WS_WORKERS``
     - as given
     - as given
     - ``GUNICORN_PRELOAD`` decides

The mode changes *only* the HTTP tier: the websocket server, the startup
ordering probe of #1032, ``DJANGO_DEBUG`` and every explicit override are
untouched. Production defaults are the numbers that were already shipped,
so selecting the mode can never reduce production throughput by accident -
and the offline suite pins the resolver table above, the compose
pass-through and the absence of ``DJANGO_DEBUG`` from the production
backend's environment. The debug-toolbar exposure #1617's acceptance names
is gated by settings on ``DJANGO_DEBUG``, which only the development stack
sets, and autoreload exists in the dev shape only (both servers of the
deployed container start without a file watcher; the dev ``runserver`` +
StatReloader shape is measured by #1613 and is a different, larger
resident).

How the numbers below were produced
===================================

One disposable stack, one Compose project, the *deployed* shape -
``docker-compose.yml`` **without** ``docker-compose.dev.yml``, so gunicorn
boots through ``startup.sh`` with no ``runserver`` and no watcher; a
job-local override exposed 8001/8002 on loopback and reset the
victoria-logs host port; the services were ``backend`` with its
dependencies (postgis, redis, docker-api, victoria-logs) and no celery
container, because the web tier is what is under test; the image was the
local build of ``docker/backend/alpine.Dockerfile`` with
``MRMAP_PRODUCTION=True`` (the prebuilt tag is published for the dev
flavour only, so this measurement built its own):

.. code:: console

    scripts/agent_capacity                       # admission gate first, as always
    export COMPOSE_PROJECT_NAME=mrmap-agent-<issue>-<run-id>
    export COMPOSE_FILE="docker-compose.yml:<job-local override>"
    # one arm = recreate the backend for one shape, then per phase:
    env GUNICORN_PRELOAD=1 docker compose up -d --force-recreate backend
    python3 scripts/http_process_bench.py wait-ready --arm <arm> --out bench.jsonl
    python3 scripts/stack_memory_profile sample --project <project> \
        --phase <arm>.idle --duration 90 --proc-interval 15 --out mem.jsonl
    python3 scripts/stack_memory_profile sample --project <project> \
        --phase <arm>.api-load --proc-interval 15 --out mem.jsonl --during \
      "python3 scripts/http_process_bench.py load --arm <arm> --phase api-load \
        --endpoint /api/registry/keywords*3 --endpoint /api/registry/wms*2 \
        --endpoint /api/registry/harvesting/harvesting-jobs*1 \
        --requests 3000 --concurrency 16 --peer-endpoint /__cheap_peer__ \
        --peer-interval 0.25 --out bench.jsonl"
    python3 scripts/stack_memory_profile sample --project <project> \
        --phase <arm>.api-load-ws --proc-interval 15 --out mem.jsonl --during \
      "python3 scripts/http_process_bench.py load --arm <arm> --phase api-load-ws \
        <same endpoints> --requests 1500 --concurrency 16 --peer-endpoint \
        /__cheap_peer__ --peer-interval 0.25 --ws-base-url http://127.0.0.1:18002 \
        --ws-count 25 --ws-hold 75 --token <one reused knox token> --out bench.jsonl"
    python3 scripts/stack_memory_profile report --in mem.jsonl
    python3 scripts/http_process_bench.py report --in bench.jsonl

The workload in one sentence: weighted unauthenticated list reads
(keywords, WMS, harvesting jobs) from sixteen keep-alive client threads,
plus one cheap unrouted peer asked four times a second through the whole
phase (#1032's neighbour measure: an endpoint that does no work must not
pay for its neighbours), while twenty-five *authenticated* websockets -
knox token in the query, the token branch of ``notify.auth`` - are held
open for at least 75 s across the API load. Three honesty notes the
tables assume:

* the database is the **empty migrate-only floor** of the Compose
  entrypoint (the #1613 convention): every latency is a floor, not a
  capacity promise for filled data;
* knox caps live tokens per user at 5 (#1450), so a multi-arm run must
  **reuse one token** (``http_process_bench token``) instead of logging in
  per arm - the first attempts at the two low-memory websocket phases died
  on exactly that cap (rc=1 in the sampler), were redone with a reused
  token, and are named here instead of quoted;
* the host is the usual 16-GiB agent cgroup on kernel 6.12 / docker
  29.8.2 - the numbers are a shape comparison on one host generation, and
  a second host re-runs the same commands rather than extrapolating.

Measured profile
================

Boot - the startup-regression column (``wait-ready``: recreate until the
first HTTP answer, entrypoint wait-and-migrate included):

.. list-table::
   :header-rows: 1

   * - arm
     - boot to first answer
   * - production 4 x 4
     - 15.3 s
   * - production 4 x 4, preload
     - 15.2 s
   * - low-memory 1 x 2
     - 14.5 s
   * - low-memory 2 x 2
     - 15.0 s

No arm pays a startup regression: the preload arm imports the application
in the master *instead of* per worker and boots as fast as without it, and
the 60-second websocket readiness gate of #1032 passed on every boot.

RAM of the ``backend`` container (cgroup view; committed = anon + sock +
kernel stack + unreclaimable slab - the number a budget must cover, per
#1613; ``cores`` is the ``cpu.stat`` delta of the api-load phase):

.. list-table::
   :header-rows: 1

   * - arm
     - idle charge p50
     - idle committed
     - api-load peak
     - api-load committed peak
     - cores under api-load
   * - production 4 x 4
     - 641 M
     - 632 M
     - 723 M
     - 713 M
     - 3.90
   * - production 4 x 4, preload
     - 324 M
     - 315 M
     - 655 M
     - 645 M
     - 3.99
   * - low-memory 1 x 2
     - 290 M
     - 283 M
     - 302 M
     - 295 M
     - 1.01
   * - low-memory 2 x 2
     - 411 M
     - 403 M
     - 445 M
     - 437 M
     - 1.97

The per-process view (``--proc-interval 15``) says one worker of the
deployed shape costs **about the same everywhere**: peak RSS of a single
gunicorn process measured 197-224 M in every arm, and the idle delta
between 4 workers and 1 (641 M - 290 M over 3 workers) prices one idle
HTTP worker at **~117 M of the reservation** - the worker count is the
multiplier, exactly as the celery reading of #1613 found for prefork
slots. One caveat the preload row needs: the sampler's per-process
``anon`` *sums* the same copy-on-write pages once per process (763 M of
summed anon in the preloaded arm against a 655 M charge), so under preload
only the cgroup columns may be read as cost; that is the same trap #1613
documents for PostgreSQL's shared segment.

Throughput and latency under the same phases (``peer95`` = the cheap
unrouted neighbour while the load is in flight; ``ws`` = held websockets
still open at phase end / started, with ``closed early`` counting any
peer-closed or errored connection):

.. list-table::
   :header-rows: 1

   * - arm
     - api-load rps
     - api-load p50 / p95 / p99
     - api-load peer95
     - ws-phase rps
     - ws-phase peer95
     - ws
   * - production 4 x 4
     - 200.9
     - 63 / 172 / 359 ms
     - 218 ms
     - 201.3
     - 44 ms
     - 25/25, 0 early
   * - production 4 x 4, preload
     - 197.1
     - 67 / 165 / 375 ms
     - 147 ms
     - 194.9
     - 25 ms
     - 25/25, 0 early
   * - low-memory 1 x 2
     - 55.0
     - 279 / 440 / 524 ms
     - 464 ms
     - 57.5
     - 266 ms
     - 25/25, 0 early
   * - low-memory 2 x 2
     - 106.3
     - 84 / 347 / 560 ms
     - 395 ms
     - 104.6
     - 28 ms
     - 25/25, 0 early

All 11 000 answered requests across the four arms came back under 400 -
the workload never produced an error in any shape.

What the tables say
===================

* **The worker count is the reservation and the lanes.** ~117 M per idle
  worker, and throughput that tracks processes, not threads: 201 rps at
  4 workers, 106 at 2, 55 at 1. Threads only queue - the 16-client burst
  saturated the 4 x 4 queue depth (peer at 218 ms) and deepened the
  smaller shapes' queues instead of parallelizing them (the #1032 reading
  reproduced from the other side).
* **Low-memory mode is a real lever with a real price.** 1 x 2 takes
  351 M off the container's idle charge (641 -> 290 M, -55 %) and answers
  the same empty-database reads at -73 % throughput, a cheap neighbour at
  464 ms instead of 218 ms, and the API load itself at p95 440 ms. 2 x 2
  is the measured midpoint: -230 M idle, -47 % throughput. This is why
  the mode is **opt-in** and why nothing about it is enabled by default.
* **Twenty-five idle websockets are noise.** Holding them open across an
  API load moved no arm's throughput measurably (201.3 vs 200.9 rps) and
  cost nothing measurable in the container's committed memory; the one
  ASGI worker carried all 25 on every arm, none closed early, and the
  handshakes answered in tens of milliseconds. The #1032 split stands:
  the event loop of :8002 is idle-work-shaped, the gthread pool of :8001
  is sync-work-shaped, and neither should absorb the other.
* **A preloaded arm is not a slower boot.** 15.2 s against 15.3 s - the
  master's single import *replaces* four worker imports instead of adding
  a fifth.

The preload verdict
===================

**Default stays off; the knob is documented and measured, and safe to
enable.** #1617 allows preload only where the fork is provably safe, so
the safety half is an audit, not a hope, and the benefit half is measured:

* **No inherited database connections.** Every app ``ready()`` hook in the
  project connects signals (``post_migrate`` only) - none queries, so the
  master imports the WSGI application with no pool open. Measured: with
  the arm warm and traffic served, ``pg_stat_activity`` held **20
  connections with preload off and 20 with preload on** - five processes
  (four HTTP workers plus the websocket worker) times the pool
  ``min_size`` of 4, each opened *by its own process*, and the master
  itself held none. A 240-request burst at concurrency 16 answered 0
  errors in both states; psycopg connections shared across a fork die on
  exactly that traffic, so the equality is a functional proof, not just a
  count.
* **GDAL/GEOS are imported, not opened.** ``settings.py`` reads GDAL
  version info at import time and the library's cross-process rule is
  about opened datasets; datasets are opened per request/task after the
  fork, so nothing shared survives it.
* **No event loop and no sockets in the master.** The preloaded import
  builds modules, not loops: the ASGI application of :8002 is *never*
  preloaded (one worker - nothing to share - and #1617's acceptance names
  stuck websockets as the failure mode; the held websockets above prove
  the point in the arm that does preload), and gunicorn's listening
  sockets live in the master with or without the flag, which is what
  workers already share today.
* **Caches and init order are untouched.** The per-worker OpenAPI schema
  cache of #1336 warms on first request after the fork, and the startup
  gate that fails the boot when :8002 never listened is unchanged.

What it buys is in the RAM table: **the idle reservation of the web tier
halves** (641 -> 324 M charged, 632 -> 315 M committed, because four
workers then share one copy-on-write set of imported pages), the loaded
peak drops by ~68 M of committed, and throughput pays ~2 % (197 vs 201
rps, within run noise). What it costs is a posture change, which is why
it is a flag and not a default: with preload, an application that fails
to import kills the whole boot instead of failing per worker - the boot
either comes up or it does not. A deployment that wants this for a
memory-starved host while keeping production lanes enables
``GUNICORN_PRELOAD=1`` and nothing else; in the low-memory mode it is
pointless by construction (one worker shares with nobody).

Low-memory mode: what it trades
===============================

``MRMAP_LOW_MEMORY=1`` is the shape #1617 measured as **1 worker x 2
threads**, and the trade is now a number: it gives up ~351 M of the
backend container's committed reservation (and, with a populated or
busier host, up to ~420 M of the loaded peak: 713 -> 295 M committed
between the arms) and takes back 73 % of the empty-database list
throughput, with the cheap neighbour waiting 464 ms instead of 218 ms
under a 16-client burst. The mode is aimed at the host the epic describes
- a developer's or an agent's machine running *beside* MrMap, where the
web tier is background service - not at a deployment; the
:ref:`compose-profiles` mode (#1614) tiers away the optional UIs, this
mode tiers the HTTP tier, and the two compose together. That the web tier
can go as low as 283 M committed at all is the #1613 story told from the
other side: the reservation is processes, and processes are the dial.

What was not measured
=====================

* a **filled database** and authenticated HTTP reads: every latency here
  is the empty-database floor (the #1613 convention); #1623's regression
  reporting re-runs these arms over named data states, and filled data
  moves the absolute numbers, not the per-worker price;
* websockets carrying real background-process traffic (the held sockets
  were idle, which is their shape), ``wss``/TLS edges, and client counts
  beyond 25 - the knob for those is ``GUNICORN_WS_WORKERS``, untouched by
  anything on this page;
* celery (not started in this stack by design) and PostgreSQL tuning -
  ``shared_buffers`` here are the image defaults; the pool sizes the web
  tier multiplies belong to #1621, which takes the ~117 M-per-worker and
  4-connections-per-pool numbers from this page as inputs;
* daphne as the deployed websocket server: the deployed shape is gunicorn
  with one Uvicorn worker (the daphne in ``INSTALLED_APPS`` serves the dev
  ``runserver``), and no arm changed that.
