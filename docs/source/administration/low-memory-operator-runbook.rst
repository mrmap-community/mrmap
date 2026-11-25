.. _low-memory-operator-runbook:

============================
Low-Memory Operator Runbook
============================

.. sidebar:: Issue #1624 · epic #1612

    The operator-facing rollout of the runtime-memory work of epic #1612.
    Every number quoted here is a **measurement** carried by a linked page
    (#1613, #1614, #1615, #1616, #1617, #1618, #1621) or is explicitly
    labelled **derived** or **not measured**; this page adds no new
    measurement of its own. The admission gate which decides whether a host
    fits a stack stays ``scripts/agent_capacity`` (#1053/#1054/#1055) -
    nothing here overrides it.

A runbook for the human who runs MrMap on a host that is short of memory:
which modes exist, what each one is worth, what it costs, how to bring a
stack up and down, what has to be true before a low-memory configuration is
trusted, and how to get back. Every step is taken from committed tooling -
the Compose files, the resolvers and the scripts named as sources - not from
aspiration.

The machine-readable form of these modes, consumed by the documentation
automation (#1604) and held against the real Compose files and resolvers by
``scripts/test_low_memory_deployment.py``, is
``scripts/low_memory_deployment.json`` - the same convention as
``scripts/release_lifecycle.json``. What is written here is what the tooling
actually does; a drift between the two fails that suite.

Sources
=======

- :ref:`compose-profiles` - the service matrix of the tiers and the two
  seams which make the lightweight mode safe to layer.
- :ref:`runtime-memory-baselines` - the measured before-picture, the reading
  rules (charge vs committed), the 16-GiB agent-cgroup environment.
- :ref:`http-process-profiles` - the deployed web-tier shapes, the
  low-memory mode and the preload verdict, all measured.
- :ref:`db-pool-memory` - the pool bounds and PostgreSQL's cost per pooled
  connection.
- :ref:`celery-queues` - the worker slots, recycling and the revocation
  window.
- :ref:`celery-healthcheck-overhead` - what the worker healthcheck probe
  costs and what #1616 changed about it.
- :ref:`test-memory` - the test-only one-worker preset (#1619).
- :ref:`development-environment` - the per-variable reference of every knob
  below.
- :ref:`release-operator-runbook` - the release side of an upgrade; this
  page is the deployment-shape side.

Modes
=====

Four supported shapes, three of them deployment modes and one a test
preset. None of them is a new default: the full deployment of the
installation document is unchanged by epic #1612, and every mode below is a
file you add or a variable you set.

.. list-table::
   :header-rows: 1
   :widths: 22 34 44

   * - mode
     - selected with
     - what it changes
   * - **full** (the contract)
     - ``docker-compose.yml`` alone
     - nothing - eleven services, log store, dashboards, cold-start wait on
       the log store, exactly as before the epic
   * - **lightweight**
     - layer ``docker-compose.lightweight.yml`` LAST
     - the observability (``victoria-logs``, ``grafana``), admin
       (``pgadmin``, ``flower``) and testing (the four one-off check
       containers of ``docker-compose.dev.yml``) services become opt-in
       Compose profiles; the core runs without them
   * - **low-memory web tier**
     - ``MRMAP_LOW_MEMORY=1`` in the deployment environment
     - one variable moves the web shape to **1 HTTP worker x 2 threads**
       and the database pool bounds to **1 reserved / 4 open per pooled
       process** (#1617 + #1621 read the same mode); everything else -
       websocket server, queue depths you pin explicitly, ``DJANGO_DEBUG`` -
       is untouched
   * - **test concurrency** (#1619)
     - layer ``docker-compose.test-low-memory.yml``
     - the ``django-tests`` and ``frontend-tests`` containers run their
       runners with one worker (``MRMAP_TEST_WORKERS=1``); no pool, heap,
       database or production setting changes with it

The modes compose: a lightweight core with the low-memory web tier is the
shape the epic describes for a host running MrMap *beside* an agent or an
editor. An explicit ``GUNICORN_WORKERS``/``GUNICORN_THREADS``/
``GUNICORN_WS_WORKERS``/``MIN/MAX_BACKEND_RESERVED_CONNECTIONS`` always wins
over the mode - the mode only supplies defaults
(``backend/.bash_scripts/process_defaults.sh``, ``_db_pool_bounds_from_env``
in ``backend/MrMap/settings.py``).

Startup and shutdown
====================

Always in a project you own (``COMPOSE_PROJECT_NAME`` or ``-p``), never
against the stack of somebody else; an agent follows the worktree isolation
rules of ``AGENTS.md``.

.. code:: console

    # 0. admission first, always - it decides, this page does not
    scripts/agent_capacity                      # --need stack / --need suite
    export COMPOSE_PROJECT_NAME=mrmap-operator-<name>

    # full deployment - the documented contract, unchanged
    docker compose -f docker-compose.yml up -d

    # lightweight core (tiers off), layered LAST
    docker compose -f docker-compose.yml -f docker-compose.lightweight.yml up -d

    # one tier back on for the run which needs it
    docker compose -f docker-compose.yml -f docker-compose.lightweight.yml \
        --profile observability up -d

    # lightweight + low-memory web tier (set it in .env or export it -
    # docker-compose.yml passes the variable through untouched)
    MRMAP_LOW_MEMORY=1 docker compose -f docker-compose.yml \
        -f docker-compose.lightweight.yml up -d --force-recreate backend

    # shut down THIS project and nothing else: down re-reads .env on every
    # invocation, so the project is named explicitly rather than inherited
    # (AGENTS.md requires the same before any removal - a copied .env still
    # carries somebody else's COMPOSE_PROJECT_NAME). Look before you delete:
    docker ps -a --filter \
      "label=com.docker.compose.project=$COMPOSE_PROJECT_NAME"
    docker compose -p "$COMPOSE_PROJECT_NAME" -f docker-compose.yml \
      -f docker-compose.lightweight.yml down

Three shutdown facts an operator has to know:

* **Profiles gate what ``up`` creates; they never remove anything.** A stack
  which already runs a tier keeps running it after the file is layered -
  take it down by name in your own project
  (``docker compose stop grafana pgadmin flower victoria-logs && docker
  compose rm -f ...``).
* **A tier which is not active has no container and therefore no restart
  policy.** After a host reboot a lightweight deployment comes back *as
  configured* - the core without the tier. To make a tier permanent on a
  host, set ``COMPOSE_PROFILES`` in ``.env`` and bring the stack up once
  with it, which creates the containers and gives them their
  ``unless-stopped`` policy (#901).
* **A lightweight ``.env`` still needs the tier's variables**
  (``GRAFANA_ADMIN_USER``/``GRAFANA_ADMIN_PASSWORD``,
  ``PGADMIN_USER``/``PGADMIN_PASSWORD``): Compose interpolates every service
  in the files it reads, profiled or not.

Dependencies and required services
==================================

The core is not negotiable; the tiers are. The classification is
machine-checked by ``scripts/compose_profiles_smoke.py`` (run it from the
repository root before trusting a matrix that changed).

* **core** - ``postgis``, ``redis`` (data and broker), ``backend``,
  ``celery-worker``, ``celery-beat``, ``frontend`` (the application) and
  ``docker-api``. The socket proxy is *not* a dashboard: the status UI of
  the ``system`` app reads container health through it, so dropping it
  trades memory for a broken status page. ``mapserver`` is a runtime
  dependency of the development stack and the exact dependency of the
  suites which assert OGC responses - start it by name where it is needed.
* **observability** (``victoria-logs``, ``grafana``) - optional for the
  application, required for central log search. The one load-bearing edge
  into this tier is ``backend``'s ``depends_on`` on the log store: the
  syslog handler of ``settings.py`` decides once, at import, whether the
  store resolves. The lightweight file merges ``required: false`` onto that
  edge - with the tier on the wait is honoured exactly as in the full mode;
  with it off the backend starts, prints "syslog server is not reachable.
  skipping syslog handler setup." and logs to its console. That fallback is
  the documented log path of the mode: application logs reach the console
  (``docker compose logs backend``), and the container logs of
  ``postgis``/``frontend`` are redirected to bounded local json-file logs
  (2 x 10 MB) instead of shipping into a sink which is not there.
* **admin** (``pgadmin``, ``flower``) - two UIs over data the application's
  own API and status pages already expose. The edge's ``/grafana/``,
  ``/pgadmin/`` and ``/flower/`` locations answer 502 without them; nothing
  inside MrMap links to them.
* **testing** - the one-off check containers; ``docker compose run`` names
  them explicitly and works with the profile off, so no CI command needs a
  flag.

The knobs and their defaults
============================

The full per-variable reference is :ref:`development-environment`; this is
the memory-relevant table with the defaults the shipped files actually pass
(values as committed in ``docker-compose.yml``, the redis command line,
``backend/.bash_scripts/process_defaults.sh`` and
``backend/MrMap/settings.py``).

.. list-table::
   :header-rows: 1
   :widths: 34 18 48

   * - knob
     - default
     - what it is
   * - ``CELERY_WORKER_CONCURRENCY``
     - 4
     - prefork slots of the worker. The memory of the fleet is this number
       times whatever a child holds (~170-211 MB resident once warm,
       :ref:`celery-queues`); ``auto`` sizes by the container's cgroup
       quota. Celery's own default (one slot per host core) was the OOM
       path #1454 closed.
   * - ``CELERY_WORKER_MAX_TASKS_PER_CHILD``
     - 1000
     - tasks a slot runs before the pool replaces it - what keeps a child
       that parsed a few thousand documents from carrying that residue
       (#1615 fixed the name celery actually reads). Empty means 1000;
       there is no "never".
   * - ``CELERY_WORKER_MAX_MEMORY_PER_CHILD``
     - off (empty)
     - replaces a child whose ``ru_maxrss`` peak passes the kB. Ships off:
       a fresh child already peaks near 170 MB of that quantity and the
       import path plateaus at 211 MB, so a bound below that replaces after
       every task; it is also checked only after a *completed* task, so it
       is no OOM guard.
   * - ``CELERY_WORKER_REVOKES_MAX``
     - 2000000
     - revoked task ids kept per worker. Below the ~600k ids a big
       catalogue abort revokes and a forgotten revocation runs again.
   * - ``REDIS_MAXMEMORY``
     - 768mb
     - the ceiling of the one shared instance (broker + results + cache);
       the policy is ``volatile-lru`` (``docker/redis/redis.conf``): only
       keys with a TTL can be evicted, so broker queues cannot be a victim.
       The measured idle footprint is 12 M charged (#1613) - the default is
       headroom against a runaway consumer, not a measured need.
       ``0`` removes the ceiling and is the failure mode this knob exists
       to avoid.
   * - ``GUNICORN_WORKERS`` / ``GUNICORN_THREADS``
     - 4 / 4 (1 / 2 with the mode)
     - the HTTP lanes: the worker *count* is the reservation (measured ~117
       M of committed per idle worker) and the throughput; the thread count
       is the queue depth in front of one worker (:ref:`http-process-profiles`).
   * - ``GUNICORN_WS_WORKERS``
     - 1
     - ASGI workers on :8002; idle websockets are I/O bound and one event
       loop carried 25 held sockets at no measurable cost on every arm.
   * - ``GUNICORN_PRELOAD``
     - off
     - forks the HTTP workers from one pre-imported master: measured to
       halve the web tier's idle reservation (641 -> 324 M charged) for
       ~2 % throughput, with one posture change - a failed import kills the
       whole boot. The websocket server is never preloaded.
   * - ``MRMAP_LOW_MEMORY``
     - off
     - the one switch for both rows below and the two web rows above; the
       spellings are ``1/true/yes/on``.
   * - ``MIN_BACKEND_RESERVED_CONNECTIONS`` and
       ``MAX_BACKEND_RESERVED_CONNECTIONS``
     - 4 / 20 (1 / 4 with the mode)
     - the psycopg pool of every *non-celery* process (Celery keeps no pool
       by decision). Set these in ``docker/backend/.mrmap.env``, not as a
       Compose pass-through - an ``environment`` entry with an empty
       fallback would shadow the file (#1615's failure class). Each pooled
       connection costs PostgreSQL ~2 M of anonymous RSS, and an
       over-minimum connection is held after release (:ref:`db-pool-memory`).
   * - ``MRMAP_TEST_WORKERS``
     - unset (preset sets 1)
     - test-runner concurrency of the #1619 preset only; never a deployment
       knob.

Tradeoffs
=========

What each lever buys, with the source page. "charge" and "committed" are
read the way #1613 defines them (the cgroup ``memory.current`` vs the
non-reclaimable part an OOM cannot take back); budgets must cover
**committed**, not charge.

* **Dropping the admin + observability tier** (lightweight mode): 61 % of
  the stack's idle charge but only 33 % of its idle reservation - grafana's
  1958 M were 82 % reclaimable page cache. Full stack warm idle: 3949 M
  charge / 2005 M committed (**measured**, #1613); core-only: 1558 M /
  1340 M (**derived** from those rows by subtracting the tier's own
  measured rows - no stack of the mode was itself sampled). What you lose:
  central log search (console fallback instead), the Grafana dashboard,
  the pgAdmin and Flower UIs (502 at the edge). Nothing inside MrMap links
  to the tier; the status UI is core and unaffected.
* **``MRMAP_LOW_MEMORY=1``** (1 x 2 web shape): the backend container
  drops from 641 M charge / 632 M committed idle to 290 M / 283 M, and its
  loaded committed peak from 713 M to 295 M (**measured**, #1617) - and
  answers the same empty-database list workload at **55 rps instead of
  201** (-73 %), p95 440 ms instead of 172 ms. 2 x 2 is the measured
  midpoint (-230 M idle, -47 %). This mode is aimed at a host where the
  web tier is background service - beside an agent, an editor, another
  stack - not at serving users.
* **``GUNICORN_PRELOAD=1`` without the mode**: halves the web tier's idle
  reservation for ~2 % of throughput (**measured**); pointless inside
  ``MRMAP_LOW_MEMORY`` (one worker shares with nobody) and it changes the
  boot's failure posture (import failure kills the whole container).
* **Pool bounds 1/4 with the mode**: idle loaded pool went from 20 visible
  connections to 3 in the measured arms (**measured**, #1621); each
  connection is ~2 M of PostgreSQL anonymous RSS which is *held* after the
  spike. The bound limits one process - a capacity-aware deployment sets
  the pair for the total it can serve against PostgreSQL's
  ``max_connections`` (100 by image default).
* **Redis ceiling**: the trade is a rising charge for a plateau. The
  reading that says the bound is wrong: ``redis-cli INFO stats`` ->
  ``evicted_keys`` non-zero under a workload you consider normal means
  raise ``REDIS_MAXMEMORY``; do **not** relax ``volatile-lru`` - it is the
  only policy that cannot drop broker queues. A lost result under pressure
  is loud by design (``NotFound`` at the consumer), a lost queue is
  silent.
* **Fewer Celery slots** (``CELERY_WORKER_CONCURRENCY``): the slots are
  the reservation of the fleet (7 celery processes held 1166 M of anonymous
  memory at idle in the measured dev stack, **measured** #1613) - taking
  slots is the biggest single lever and the one that costs task
  throughput, so change it against a sampled workload, not against a hunch.

Health checks
=============

The tiers do not gain, lose or weaken one healthcheck; the same four gate
what gated before (``docker-compose.yml``):

.. list-table::
   :header-rows: 1
   :widths: 24 52 12 12

   * - service
     - test
     - interval
     - start_period
   * - ``postgis``
     - ``pg_isready -U $POSTGRES_USER -d $POSTGRES_DB``
     - 10s
     - 20s
   * - ``redis``
     - ``redis-cli ping``
     - 5s
     - 2s
   * - ``celery-worker``
     - ``python -m system.worker_healthcheck`` - the module probe of #1616:
       the same directed ``inspect ping`` without a Django startup, ~a
       quarter less CPU per probe, and it reports a paused broker in under
       4 s instead of hanging to the timeout
     - 15s
     - 40s
   * - ``celery-beat``
     - the age of ``/var/mrmap/run/beat-heartbeat`` (< 30 s)
     - 10s
     - 30s

``backend`` has no healthcheck of its own and no mode gives it one; it no
longer waits for a log store which is not there, and still waits for it when
it is (the ``required: false`` seam). The application's own status UI is
core and reports ``database``/``redis``/``workers``/``beat`` through the
docker-api proxy - ``GET /api/system/status/<id>`` (admin only), which
answers in every mode, with or without any tier.

Before calling a low-memory configuration up, wait for the four to report
``healthy`` and for the backend to answer at all (``/api/system/info`` is
admin-only, so an unauthenticated probe expects 403 - a refused answer
proves the server is up, a connection error does not):

.. code:: console

    docker compose ps
    code=$(curl -s -o /dev/null -w '%{http_code}' http://localhost/api/system/info)
    case "$code" in 200|403) echo "backend answering ($code)";;
                    *) echo "backend not up ($code)"; false;; esac

Telemetry
=========

The read-only sampler and the bench are the committed instruments - they
mutate nothing and their offline suites run in
``scripts/check_repo_tooling.sh``:

.. code:: console

    # RAM per container and phase: cgroup charge/peak/committed + OOM events
    scripts/stack_memory_profile sample --project "$COMPOSE_PROJECT_NAME" \
        --phase lite-warm-idle --duration 600 --out runs.jsonl
    scripts/stack_memory_profile sample --project "$COMPOSE_PROJECT_NAME" \
        --phase lite-boot --during 'docker compose up -d' --out runs.jsonl
    scripts/stack_memory_profile report --in runs.jsonl

    # web-tier throughput / latency of one arm - the weighted endpoint plan
    # the #1617/#1621 arms ran, with its cheap peer (see db-pool-memory for
    # the full campaign; --base-url defaults to the bench's own backend port)
    python3 scripts/http_process_bench.py load --arm lowmem --phase api-load \
        --endpoint /api/registry/keywords*3 --endpoint /api/registry/wms*2 \
        --endpoint /api/registry/harvesting/harvesting-jobs*1 \
        --requests 3000 --concurrency 16 --peer-endpoint /__cheap_peer__ \
        --peer-interval 0.25 --out bench.jsonl
    python3 scripts/http_process_bench.py report --in bench.jsonl

Routine operator readings, one per knob that bounds something:

.. code:: console

    # what is charged right now, per container
    docker stats --no-stream

    # Redis: a non-zero delta under normal load = raise REDIS_MAXMEMORY
    docker compose exec redis redis-cli INFO stats | grep -E 'evicted_keys|evicted'
    docker compose exec redis redis-cli CONFIG GET maxmemory

    # PostgreSQL: who holds connections (pool totals, not per process). The
    # names are read INSIDE the container - single quotes keep the host shell
    # from expanding them - which is exactly what the postgis healthcheck's
    # pg_isready does; see the note under this block.
    docker compose exec -T postgis sh -c \
      'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -At -c \
       "SELECT application_name, state, count(*) FROM pg_stat_activity \
        WHERE datname = current_database() GROUP BY 1,2"'

    # OOM accounting of the stack's cgroups (0 expected in every phase)
    docker compose exec redis sh -c 'cat /sys/fs/cgroup/memory.events 2>/dev/null || true'

The ``psql`` line names its user and database **inside** the container on
purpose. ``docker compose exec`` enters the postgis image as root, and the
image has no ``root`` role - ``POSTGRES_USER`` is whatever ``DB_USER`` said -
so a bare ``docker compose exec postgis psql -At -c ...`` answers
``FATAL: role "root" does not exist``; the reading
:ref:`db-pool-memory <db-pool-memory>` ran from a shell already inside the
container as the right user. The single quotes are what stop the **host**
shell, which never holds these variables (``.env`` is read by Compose and not
exported), from substituting empty ones - the same escape
``docker-compose.yml`` uses in the ``pg_isready`` test.

Re-measuring means starting a stack: ``scripts/agent_capacity`` first, in a
project you own, torn down afterwards. The repeatable regression reporting
that owns doing this on a schedule is #1623 (open) - until it lands, a
re-run is a deliberate act, and the pages above take the new phase names so
a re-run extends their tables instead of contradicting them.

Scenarios
=========

Two scenarios the epic names, kept apart the way #1613 keeps measured from
projected. Neither is a safety promise; both describe a configuration to
validate, not a result to assume.

**A. The 16-GiB agent cgroup - measured.** This is the environment of
#1613's baseline and of the #1617/#1621/#1619 campaigns (kernel 6.12,
docker 29.8.2): an agent container limited to 16 GiB running the stack
beside its own session. The admission gate decides for it, per class:
``--need stack`` requires 6 GiB effective, ``--need suite`` 8 GiB (the
full-suite arm took the stack to 7350 M charge / 4973 M committed, and
~7 GiB of the 16 GiB were unreclaimable while it ran). The lightweight
stack's own floor is the core-only budget row - 1558 M charge / 1340 M
committed, derived (:ref:`compose-profiles <compose-profiles>`); with the
``observability`` tier on that row reads 1613 M / 1379 M instead, still
under a tenth of the cgroup. The web tier in low-memory shape adds 283 M
committed to the picture instead of 632 M. What to run: the lightweight
mode, ``MRMAP_LOW_MEMORY=1`` if the agent's traffic is background, and
never a second stack the gate refuses.
A full-suite run in the same cgroup is a ``--need suite`` job by admission,
not by taste.

**B. The 32-GiB Ubuntu host with a local coding model - NOT measured.**
No number in this repository measured such a host; #1623 carries that
measurement as an open task. What the measured evidence supports is a
configuration to validate there, labelled as a projection: the
lightweight core (derived 1558 M charge / 1340 M committed idle) with the
low-memory web tier, plus the coding model's own footprint and the
transient to survive, carried over as the **worst case measured so far**
rather than as a fit: the ``suite-full`` phase took a **development** stack
- twelve services including the observability tier, with the check
containers booting - from 4002 M / 2063 M idle to 7350 M / 4973 M
:ref:`charged and committed <runtime-memory-baselines>`, a **+3.3 GiB /
+2.9 GiB** delta measured in the 16-GiB environment. Adding it to a
core-only base is arithmetic across two different configurations, so it is
an upper bound and never an expectation: no core-only stack with a suite was
ever sampled, which is exactly what #1623 owes before anyone calls this
host safe. It also does not transfer automatically to a 32-GiB host with a
different kernel, allocator pressure and model runtime. Treat every fit
claim for that host as an open measurement until someone runs
``scripts/stack_memory_profile`` there and appends the phases to
:ref:`runtime-memory-baselines`. Do not conclude the host is safe because
the projections fit; conclude it is safe because the host's own numbers
fit, with margin.

Rollout
=======

The order below is the validation an operator runs once per host, in a
job-owned project. Each step's gate is observable, and "stopped" means
observed failure at that gate, not a feeling.

1. **Admit.** ``scripts/agent_capacity`` (``--need stack`` for a stack,
   ``--need suite`` for suite runs). A refused admission is the end of the
   rollout, not a speed bump.
2. **Bring up the mode you intend to run** (Startup and shutdown above);
   wait for the four healthchecks and ``/api/system/info``.
3. **Sample the idle floor** for 10 minutes (``lite-warm-idle`` above) and
   compare with the **budget row of the mode you started**, from the table
   in :ref:`compose-profiles <compose-profiles>` - core only: 1340 M
   committed (1558 M charge); with ``observability`` on: 1379 M (1613 M);
   with ``admin`` on: 1621 M (1936 M). The committed number must sit at or
   under the figure of that row; a stack which idles far above its
   row is not the configuration the page describes.
4. **Drive the representative workload** you actually care about through
   the mode - the API reads (``http_process_bench.py load``), a
   registration/harvest run, a monitoring update - sampled with
   ``--during``. Gate: zero ``oom_kill`` deltas in ``memory.events`` per
   phase, worker healthchecks stay green, websockets stay open
   (``http_process_bench`` counts early closes), task results are readable
   (no ``NotFound`` on results you did not expect to evict).
5. **Read the bounded knobs after the load**: ``evicted_keys`` (Redis),
   ``pg_stat_activity`` counts (pool), worker child RSS behaviour
   (recycling). A bound that bites under *normal* load is raised per the
   Tradeoffs table - not disabled.
6. **Only then** put the mode behind ``.env`` (``COMPOSE_PROFILES``,
   ``MRMAP_LOW_MEMORY``) on the host, bring it up once so its containers
   exist with their restart policy, and re-run step 3's idle sample after
   the next host reboot to confirm it came back as configured.

Rollback and upgrade
====================

Nothing in the epic's shape work migrates state, and that is the point of
the shape; the release-side migration mechanics live in the
:ref:`release-operator-runbook`.

* **The full deployment contract is unchanged.** An instance which pulls a
  new version and runs the installation command gets what it got before,
  log store and dashboards included. Rolling an upgrade onto a
  lightweight-mode host is equally safe: the lightweight file changes the
  service set of the invocation that names it and of no other.
* **Rolling a mix of modes over the same volumes is safe.** The tiers share
  no state with the core except their own volumes (``vlogs-data``,
  ``grafana-data``), which survive their tier being off - dropping the
  observability tier stores no new lines and deletes none that exist.
* **Rolling back a mode is deleting your own addition**: drop the
  ``-f docker-compose.lightweight.yml`` from the invocation (and bring the
  tier services up once if you want them back as always-on), unset
  ``MRMAP_LOW_MEMORY`` and recreate the backend
  (``docker compose up -d --force-recreate backend``) to return to 4 x 4
  and the 4/20 pool. No restart of the other services is needed and no
  data changes shape.
* **Rolling back an *upgrade*** is a different operation - pinned image
  references and the migration reversibility rules are the
  :ref:`release-operator-runbook`'s Rollback section; memory shape never
  rescues an unreversible migration, and a low-memory configuration never
  changes what migrations a version applies.
* **Capacity is never a rollback argument**: if the full mode does not fit
  after an upgrade, that is an admission finding - take it to
  ``scripts/agent_capacity`` and the budget pages, not to a knob nobody
  measured.

Evidence and open risks
=======================

Evidence links for epic review, with each page's own commit/environment
metadata:

- measured baseline and reading rules: :ref:`runtime-memory-baselines`
  (#1613, PR #1655);
- tier matrix and budget rows (derived, labelled): :ref:`compose-profiles`
  (#1614, PR #1674) and its machine check
  ``scripts/compose_profiles_smoke.py``;
- web-tier shapes, preload verdict: :ref:`http-process-profiles` (#1617,
  PR #1678) - tool suite ``scripts/test_http_process_bench.py``;
- pool bounds and per-connection cost: :ref:`db-pool-memory` (#1621, PR
  #1704);
- worker recycling and the inert-name class: :ref:`celery-queues` (#1615,
  PR #1680); healthcheck probe: :ref:`celery-healthcheck-overhead` (#1616,
  PR #1662); Redis bound: ``docker/redis/redis.conf`` and
  ``scripts/test_redis_memory_bounds.py`` (#1618, PR #1703).

Remaining risks, owned by open issues:

- **No scheduled regression evidence yet**: the numbers above are single
  campaigns on one host generation; #1623 (open) owes the repeatable
  reports, including the 32-GiB host and the after-picture of #1618's
  Redis bound.
- **Boot of the core-only set was not measured** (only bounded: it cannot
  exceed the full stack's measured 124 s, since nothing ``depends_on`` the
  admin tier and only the log store is waited for at all).
- **Task-peak work is open**: #1620 (harvesting/monitoring/update task
  peaks) and #1619's cross-host verification of the one-worker preset are
  not settled by anything on this page.
- **PSS is unavailable in unprivileged contexts** - where
  ``/proc/<pid>/smaps_rollup`` cannot be read, RSS with the anon/file/shmem
  split is what exists; summed shared RSS must never be read as physical
  memory (#1613's rule).
- **The <3 GiB idle / <6 GiB normal targets of the epic are hypotheses**
  until workload and margins are validated on named hosts; nothing here
  treats them as proven.
