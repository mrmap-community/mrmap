.. _runtime-memory-baselines:

============================================
Runtime memory baselines of the dev stack
============================================

.. sidebar:: Issue #1613

   Part of epic #1612 (runtime memory), phase V1 · measurement. The
   admission gate that consumes these
   numbers stays ``scripts/agent_capacity`` (#1053/#1054/#1055) - this page
   never overrides it, it only tells what the stack actually costs so the
   budgets have a measured floor.

This page is the measured before-picture of #1613: what one MrMap dev stack
of ``develop`` costs in memory, per container and per workload phase, and
what a **lightweight** and a **full** profile may therefore budget. The
numbers come from one read-only sampler

.. code:: console

    scripts/stack_memory_profile sample --project <compose-project> --phase <name> \
        [--duration N | --during 'command'] [--interval S] --out runs.jsonl
    scripts/stack_memory_profile report --in runs.jsonl

which reads only cgroup files (``memory.current``/``memory.peak``,
``memory.stat``, ``memory.events``, ``cpu.stat``, ``cgroup.procs``) and the
``/proc/<pid>/status`` of the stack's processes, plus `docker ps`/`inspect` -
it mutates nothing, and its offline suite runs without docker
(``scripts/test_stack_memory_profile.py``, picked up by
``scripts/check_repo_tooling.sh``).

How to read the numbers
=======================

Per container the report answers three things, and conflating them is the
#1054 mistake to avoid:

* ``cur p50 / peak`` - the cgroup charge ``memory.current``: anonymous
  memory, tmpfs **and page cache**. Cache is charged but reclaimable; a
  container whose 2 GB are mostly file cache is not a 2 GB reservation.
* ``file-peak`` - the kernel's own high watermark (``memory.peak``, kernel
  ≥ 5.19), which survives phases the sampler did not cover.
* ``committed peak`` - ``anon + sock + kernel_stack + slab_unreclaimable``
  from ``memory.stat``: the part an OOM situation cannot take back. This is
  the number a budget must cover.

``oom``/``oom_kill`` deltas are per phase; a phase that OOMed says so. The
cpu column is the ``usage_usec`` delta of ``cpu.stat`` divided by the phase's
wall time, so it reads as "cores this container held during the phase", with
the throttled time next to it where a limit was hit. On a coarser cadence the
sampler adds the per-process view of ``/proc`` (RSS with its anon/file/shmem
split, aggregated by command name) - see the process section below for what
that may and may not be used to claim. The sampler's own cgroup rides along
in every run, because a profile taken from inside the agent container is a
measurement inside that cgroup, not of the bare machine.

Measured profile
================

Environment (one run, one tree, no invented values):

.. list-table::
   :header-rows: 1
   :widths: auto

   * - what
     - value
   * - tree
     - ``origin/develop`` at ``0aeec58d3`` (worktree of #1613 branched from it)
   * - compose files
     - ``docker-compose.yml`` + ``docker-compose.dev.yml`` + ``docker-compose.prebuilt.yml``
       (backend image ``ghcr.io/mrmap-community/mrmap-backend-dev:fcbd17dfa3b5``)
   * - stack services up
     - backend, celery-worker, celery-beat, postgis, redis, mapserver,
       docker-api, frontend(nginx), victoria-logs, grafana, pgadmin, flower
       (the ordinary services of ``docker-compose.yml``; ``behave``,
       ``django-tests``, ``frontend-tests`` and ``pre-commit-check`` are
       one-off run containers, counted while they run)
   * - measurement host
     - kernel 6.12.107+deb13-amd64, docker 29.8.2, cgroup v2 (cgroupfs);
       the agent container's own limit is not visible through its cgroup
       mount here (``limit -``) - host ceiling numbers stay owned by
       ``scripts/agent_capacity``, which reads them through the parent
       chain (#1054)
   * - NOT measured here
     - a 32-GiB local developer host, and the production gunicorn/daphne
       backend shape (``docker-compose.dev.yml`` runs ``runserver`` +
       StatReloader and celery ``--autoreload`` - the dev backend is a
       different shape from the deployed one); both are projections only
       the next V1 issue may make, and it must label them as such

Per-container steady state (warm idle, no traffic):

.. list-table::
   :header-rows: 1
   :widths: auto

   * - container
     - charge p50
     - charge peak
     - committed p50
     - note
   * - grafana
     - 1958 M
     - 1959 M
     - 345 M
     - the single biggest service and the biggest lie of the charge column: ~82 % of it is reclaimable page cache (``anon`` 340 M), watermark ``file-peak`` 2014 M. Optional UI.
   * - celery-worker
     - 672 M
     - 725 M
     - 661 M
     - the largest committed number of the fleet; real prefork worker, dev mode adds watchmedo autoreload
   * - backend (runserver + StatReloader)
     - 441 M
     - 442 M
     - 430 M
     - dev shape; the deployed gunicorn/4-worker/4-thread shape is **not** what this row measures
   * - pgadmin
     - 311 M
     - 311 M
     - 231 M
     - optional UI
   * - postgis
     - 191 M
     - 195 M
     - 16 M
     - charge is shared-buffer and relation cache, committed is 16 M; the row that shows the two columns mean different things
   * - celery-beat
     - 180 M
     - 180 M
     - 173 M
     -
   * - flower
     - 67 M
     - 67 M
     - 50 M
     - optional UI
   * - victoria-logs
     - 55 M
     - 57 M
     - 39 M
     -
   * - docker-api socket proxy
     - 33 M
     - 33 M
     - 26 M
     -
   * - frontend (nginx serving the built SPA)
     - 17 M
     - 17 M
     - 14 M
     -
   * - mapserver
     - 13 M
     - 13 M
     - 11 M
     -
   * - redis
     - 12 M
     - 13 M
     - 10 M
     -
   * - **stack sum**
     - **3949 M**
     - **4002 M**
     - **2005 M**
     - committed is 51 % of the charge: half of the idle footprint can be taken back under pressure, the other half cannot

Phase workloads (same stack, same day, nothing restarted between phases):

.. list-table::
   :header-rows: 1
   :widths: auto

   * - phase
     - what ran
     - stack charge peak
     - committed peak
     - oom
     - throughput / latency
   * - cold-start
     - ``docker compose up -d`` of the 12 services, sampled through
     - 725 M (rising; the table values land during boot-settle)
     - 376 M
     - 0
     - boot to all-containers-up: 124 s
   * - boot-settle
     - two minutes after the up, init fixtures loading, first healthchecks
     - 4025 M
     - 2089 M
     - 0
     - -
   * - warm-idle
     - 10 min, no traffic
     - 4002 M
     - 2063 M
     - 0
     - -
   * - api-load
     - 400 GETs over keywords/wms/csw/harvesting-jobs lists, unauthenticated
     - 4039 M
     - 2100 M
     - 0
     - 7.7 req/s, p50 88 ms, p95 120 ms, 400/400 answered
   * - work-behave
     - live behave harvesting+alerts (119 scenarios) against the running
       stack: real celery tasks over the shared broker
     - 4374 M
     - 2394 M
     - 0
     - 119/119 scenarios passed
   * - suite-targeted
     - 420 tests (notify, harvest history, service alerts, alert-refresh
       SQL guard, harvesting run measurements), one test database
     - 4477 M
     - 2418 M
     - 0
     - 420 OK in 168 s
   * - suite-full
     - ``manage.py test tests.django --parallel=4`` (the dev.yml shape: one
       test database plus four forkserver workers)
     - 7350 M
     - 4973 M
     - 0
     - 2965 tests OK in 1453 s

Two phases are recorded in ``runs.jsonl`` but not in the table, because they
did not measure what they were meant to: the first ``api-load`` run's loop
broke off after 200 requests on a bug in the load script, and the first
``suite-targeted`` run exited on a mistyped test label before running
anything. Both are kept in the raw file for honesty; neither is quoted.

The data state behind the load numbers
======================================

The API load and the behave run are only comparable to anything else if the
database they met is named. The dev stack's application database is the shape
the Compose entrypoint produces - migrations plus one superuser, no content
import:

.. list-table::
   :header-rows: 1
   :widths: auto

   * - what
     - value
   * - content rows
     - 0 web map services, 0 keywords; 2 users (the entrypoint's
       ``MRMAP_USER`` and the anonymous placeholder)
   * - PostgreSQL shape
     - ``shared_buffers`` 128 MB, ``max_connections`` 100,
       ``effective_cache_size`` 4 GB (image defaults, not tuned)
   * - what that means
     - the 88 ms p50 of the api-load phase is an empty-database floor of the
       dev server, not a latency a deployment would answer with; the behave
       phase is the one that actually writes and reads content (119
       harvesting and alert scenarios create services, runs and alerts)

Who inside the container: the process view
==========================================

Memory.current of a container says how much a container costs; it does not
say which process costs it, nor how much of it is shared. ``--proc-interval``
adds the ``/proc/<pid>/status`` view of every process of every container on a
coarse cadence (default 15 s; the run below used 10 s). The phase below is
**idle after the suite**, not the fresh warm idle of the first table, so its
charges are lower where cache had been dropped and higher where the suite
left cache behind - read it for the split inside the container, not as a
second idle baseline.

.. list-table::
   :header-rows: 1
   :widths: auto

   * - container
     - biggest process group
     - peak RSS of one process
     - anon (sum)
     - file (sum)
     - shmem (sum)
     - cpu during the phase
   * - celery-worker
     - ``celery`` x8 as recorded (the container's own ``ps`` counts 7 steady
       state: broker client + prefork pool, one more appeared during the
       phase), plus ``watchmedo`` autoreload
     - 231 M
     - 1166 M
     - 132 M
     - 0 M
     - 0.18 cores
   * - backend
     - ``python manage.py runserver`` x2 (server + StatReloader parent) and
       ``gunicorn`` x2 with one Uvicorn worker on :8002 - the dev container
       runs two HTTP servers, the deployed shape runs one
     - 243 M
     - 333 M
     - 215 M
     - 0 M
     - 0.08 cores
   * - postgis
     - ``postgres`` x14 (postmaster, background workers, client backends)
     - 164 M
     - 74 M
     - 76 M
     - 362 M
     - 0.01 cores
   * - grafana
     - the ``gpx_grafana-*`` plugin processes (three of them are shown by the
       report's top-three; the row is the biggest of the group)
     - 40 M
     - 12 M
     - 28 M
     - 0 M
     - 0.02 cores
   * - celery-beat
     - ``celery`` x1 (``watchmedo`` adds 7 M anon / 7 M file)
     - 232 M
     - 159 M
     - 72 M
     - 0 M
     - 0.02 cores
   * - pgadmin
     - ``python3-cap`` x2 (the Flask app), ``master``/``pickup`` (its mail
       spool, not ours)
     - 145 M
     - 171 M
     - 19 M
     - 0 M
     - 0.00 cores
   * - mapserver
     - ``apache2`` x4 + ``mapserv``
     - 44 M
     - 6 M
     - 56 M
     - 1 M
     - 0.00 cores
   * - frontend (nginx)
     - ``nginx`` x21 (master + workers)
     - 7 M
     - 47 M
     - 25 M
     - 0 M
     - 0.00 cores

Three things this answers, and one it does not:

* **the worker pool is the reservation**: seven celery processes with 1166 M
  of anonymous memory at idle confirm what the container row only hinted -
  the prefork slots, not the cache, are what a lightweight profile has to
  talk about (epic #1612's V2), and dev mode adds a ``watchmedo`` file
  watcher to worker and beat that a deployed image does not run.
* **PostgreSQL's memory is shared, not private**: the backends' private anon
  is 74 M while their shared segment accounts for 362 M of their RssShmem -
  which is why the postgis container's charge (602 M here) collapses to 59 M
  of committed once the cache is reclaimed. Caveat that belongs on the
  reading guide: RssShmem is per process, so the column **sums the same
  physical segment once per backend**; the segment's own size is
  ``shared_buffers`` plus the other shared pools (128 MB here), and the
  cgroup's ``file``/``anon`` split, not this sum.
* **the CPU cost of the idle fleet is negligible**: the whole stack uses
  ~0.3 cores at rest (worker 0.18, backend 0.08, the rest rounding to
  zero), all of it the file watchers polling. A memory-tuned profile that
  trades CPU for memory is therefore not buying itself a stall.
* **Proportional Set Size is not measured**: PSS needs
  ``/proc/<pid>/smaps_rollup``, which an unprivileged agent container may not
  read (``Operation not permitted`` on the host this ran on). RSS with the
  anon/file/shmem split is what is available without ptrace rights, and the
  page this leaves the gap open instead of estimating a number.

The agent cgroup while this ran
===============================

Every run also carries the sampler's own cgroup, and during these phases it
sat at ``current`` ~11.2 GiB with a ``committed`` peak of ~2.3 GiB - the
stack of this page is a part of that number, not all of it (the rest is the
agent session, dockerd and whatever else shares the container). During the
full-suite phase it read p50 8.2 GiB / peak 10.7 GiB, because the suite's own
memory is inside the same cgroup. That is the concrete shape of the #1054
argument: a stack which costs 3.9 GiB of charge can still be the reason a
16 GiB agent cgroup has no room for a second one, and it is why admission is
decided by ``scripts/agent_capacity`` reading the whole tree, never by the
stack sums above.

Measured and projected, kept apart
==================================

* **measured** (this page): one 16-GiB-limited agent cgroup on one host
  generation, kernel 6.12, docker 29.8.2, the develop dev-Compose shape with
  ``docker-compose.prebuilt.yml``, the phases as named in the table. Every
  number in the tables is a read of a cgroup or proc file of that run.
* **projected, and labelled as projection**: the 32-GiB local developer host
  of the epic's goal statement. Nothing here measured one. What the profile
  supports saying is only this: the shape that has to fit there is the same
  1613 M charge / 1379 M committed lightweight stack, or the 3.9 GiB / 2.0
  GiB full one, plus whatever the developer's own editor and browser cost -
  and the transient to survive is the +3.3 GiB charge / +2.9 GiB committed of
  a full suite. Anything beyond that sentence is a second measurement, not a
  extrapolation of this one.
* **not measured at all**: the deployed backend shape (this dev container
  runs ``manage.py runserver`` with its StatReloader child **and** a
  gunicorn/Uvicorn ASGI server on :8002; the deployed image runs gunicorn
  with 4 workers and 4 threads, and daphne for WebSockets), a tuned
  ``shared_buffers``, a database with content, and authenticated requests
  with their session and permission work.

Budget conclusions
==================

What the measured picture allows to say, and what it does not:

* the dev stack's **idle reservation** (committed) is about 2.0 GiB; its
  charged footprint 3.9 GiB is half reclaimable cache. A host under
  pressure can take back the cache but not the 2 GiB - that is the floor
  #1613's "lightweight deployment profile" must not push below without
  dropping services.
* the optional UI/logging tier is a real share of the idle footprint, but
  a lopsided one: grafana (charge 1958 M, committed 345 M), pgadmin
  (311 M / 231 M) and flower (67 M / 50 M) together are 59 % of the idle
  charge and only 31 % of the committed idle. Dropping all three leaves a
  stack at **1613 M charge / 1379 M committed**; that is what a
  **lightweight profile** costs at idle, and the **full profile** is the
  table above. The committed floor barely moves (2.0 GiB → 1.35 GiB)
  because grafana's 2 GiB is mostly cache - so the honest saving of
  dropping the tier is charge, not reservation, and a memory-starved host
  already reclaims much of it on its own.
* the committed idle is dominated by the two services doing the work:
  celery-worker (661 M) and the dev backend (430 M) are 54 % of it, beat
  adds 173 M. Any real reduction of the reservation has to talk about
  worker slots and the server shape (epic #1612's V2), not about dashboards.
* one-off test containers run ON TOP of the idle stack, and the delta is
  smaller than the containers' own charge suggests, because PostgreSQL's
  cache is where the work actually lands: the behave run added 372 M of
  charge and 331 M of committed (its own container peaked at 323 M,
  postgis grew from 191 M to 318 M charge but only 16 M to 75 M
  committed); the targeted 420-test suite added 475 M / 355 M (container
  peak 298 M, postgis 475 M charge / 101 M committed).
* the **full suite is a different class of work**, and the measurement says
  how much: ``--parallel=4`` took the stack from 4002 M charge / 2063 M
  committed at idle to **7350 M / 4973 M** - one test container peaking at
  2885 M of almost purely anonymous memory (2854 M committed: four forkserver
  workers holding their own copy of the imports and the test databases), and
  postgis doubling to 1595 M charge / 432 M committed. Against the idle
  numbers the suite costs **+3.3 GiB charge / +2.9 GiB committed**, and this
  happened with zero OOM events.
* that delta is why ``scripts/agent_capacity`` asks for a separate
  ``--need suite`` class at 8 GiB effective memory instead of reusing the
  6 GiB of ``--need stack``: the stack's own committed peak under the suite
  is 4.9 GiB and the agent container's committed charge around it was 2.1-2.4
  GiB during these phases, so ~7 GiB of the 16 GiB cgroup was unreclaimable
  while the suite ran. The gate's constants are not generous for this shape,
  they are about right (#1055's recorded 12.1 GiB whole-cgroup peak is the
  same event seen from the outside, with cache included).
* every conclusion above is one profile of one dev-composition on one host
  generation; a second host or the production gunicorn shape must be
  re-measured with the same tool before being budgeted (``sample`` takes
  the phase names, so a re-run extends this table instead of contradicting
  it).

What #1614 did with this
========================

``docker-compose.lightweight.yml`` (:ref:`compose-profiles`) is the supported
form of the tiering this page's numbers argue for: the log store, its UI and the
two operator UIs became Compose profiles, the check containers became a tier of
their own so ``up`` cannot boot them as services, and the core is documented to
start without any of it. The mode's own budget rows are the arithmetic of the
paragraph above, labelled as derived - a stack of that mode was not sampled
while #1614 was implemented, and the page says so where it quotes them.

Admission authority
===================

``scripts/agent_capacity`` remains the admission gate and the owner of the
host-cgroup reading rules (#1053/#1054/#1055): the classes
(``--need stack`` / ``--need suite``) and the effective-memory formula stay
there, and nothing on this page licenses starting a stack the gate refuses.
The budget rows above are the measured floor the gate's constants may be
REVIEWED against - changing them is a change to ``agent_capacity`` and its
suite, not to this page.
