.. _compose-profiles:

=======================================
Compose profiles: full and lightweight
=======================================

.. sidebar:: Issue #1614

   Part of epic #1612 (runtime memory), phase V1. The measured before-picture
   this split is designed against is
   :ref:`runtime-memory-baselines`; the admission gate which decides whether a
   host fits another stack stays ``scripts/agent_capacity``
   (#1053/#1054/#1055) - nothing on this page overrides it.

.. sidebar:: This is not the new default

   ``docker-compose.yml`` alone is still the full deployment, with its logging,
   its dashboards and its start-up ordering, exactly as before #1614. The
   lightweight mode is a file you add.

MrMap ships one deployment of eleven services. Half of its idle footprint does
not serve a request: #1613 measured that the two operator UIs and the log store
are 61 % of the charged idle memory of a development stack, while the part an
OOM cannot take back barely moves when they are dropped. #1614 turned that
measurement into a supported choice: the services which only observe or
administer MrMap, and the containers which run its test suites, are now a tier
each, and the core runs without them.

The service matrix
==================

Every service of the two committed Compose files belongs to one tier. The
classification is machine-checked by ``scripts/compose_profiles_smoke.py``: a
new service in no tier fails it.

.. list-table::
   :header-rows: 1
   :widths: 22 16 62

   * - service
     - tier
     - why there
   * - ``postgis``, ``redis``
     - core
     - the data and the broker; nothing in the matrix is measured to work
       without them
   * - ``backend``, ``celery-worker``, ``celery-beat``, ``frontend``
     - core
     - the application: HTTP, websocket, tasks, scheduling, the edge
   * - ``docker-api``
     - core
     - not a dashboard. The status UI of the ``system`` app reads container
       health through this socket proxy, so dropping it would trade memory for a
       broken status page
   * - ``mapserver``
     - core (dev)
     - a runtime dependency of the development stack and the exact dependency of
       the suites which assert OGC responses; started by name where it is needed
   * - ``victoria-logs``, ``grafana``
     - ``observability``
     - the log store and its UI. Optional for the application, required for
       central log search
   * - ``pgadmin``, ``flower``
     - ``admin``
     - two operator UIs over data the application's own API and status pages
       already expose
   * - ``pre-commit-check``, ``behave``, ``django-tests``, ``frontend-tests``
     - ``testing``
     - the one-off check containers of ``docker-compose.dev.yml``. They carry
       their work in their ``command``, so ``up`` used to boot whole test suites
       as background services

Running the modes
=================

The tiers are Compose profiles, which are **opt-in**: declaring one only removes
the service for the invocation which layered the file that declares it.

.. code:: console

    # the full deployment - the documented contract, unchanged: do not layer anything
    docker compose -f docker-compose.yml up -d

    # the full development stack of develop before #1614 - also unchanged
    docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d

    # the lightweight core, layered LAST
    docker compose -f docker-compose.yml -f docker-compose.lightweight.yml up -d

    # one tier back on, for the run which needs it
    docker compose -f docker-compose.yml -f docker-compose.lightweight.yml \
        --profile observability up -d

    # an agent or development stack: the prebuilt images of epic #959, then the tier
    export COMPOSE_FILE="docker-compose.yml:docker-compose.dev.yml:docker-compose.prebuilt.yml:docker-compose.lightweight.yml"
    docker compose up -d postgis redis mapserver
    docker compose run --rm --no-deps django-tests python manage.py test tests.django.notify --noinput

``COMPOSE_PROFILES`` in ``.env`` is the persistent switch for a host that always
wants (or never wants) a tier:

.. code:: env

    # a monitoring host which always wants the log store and its UI
    COMPOSE_PROFILES=observability

Three things to know about the mechanism
----------------------------------------

* **Profiles gate what ``up`` creates; they never remove anything.** A stack
  which already runs the tier keeps running it after the file is layered. Take
  it down deliberately, in your own project only:

  .. code:: console

      docker compose stop grafana pgadmin flower victoria-logs
      docker compose rm -f grafana pgadmin flower victoria-logs

* **A tier which is not active is not part of the project's containers**, so no
  restart policy brings it back after a host reboot - see
  `Health, readiness and restart policy`_ below.
* **A missing tier is a hard error for a dependent service**, unless the edge
  says otherwise: see `The log store the backend waits for`_.

Docker Compose version
----------------------

``docker-compose.lightweight.yml`` needs ``depends_on.required`` (Compose
v2.20.2) and the ``!override`` merge tag (v2.24.4) - the same CLI floor
``docker-compose.prebuilt.yml`` already carries with its ``!reset`` tags. The
base file stays within the minimum of the :ref:`installation` document, so this
is a requirement of the opt-in mode only. The numbers on this page were measured
and verified against Compose v5.6.0 with Docker 29.8.2.

What the lightweight mode has to answer
=======================================

Dropping a service is easy; dropping a service something else talks to is the
work. Each of these is asserted by the smoke check, so a mode which stops
answering one of them goes red before it reaches a stack.

The log store the backend waits for
-----------------------------------

``docker-compose.yml`` gives ``backend`` a ``depends_on`` on
``victoria-logs`` with ``condition: service_started``, and that wait is
 load-bearing: ``settings.py`` decides once, at import, whether the syslog
handler of the application attaches, by looking the log store up
(``MRMAP_SYSLOG_HOST``, default ``victoria-logs``). Start the backend before the
store and the process runs the whole time without its log handler.

With the tier profiled, that edge would be a configuration error while the tier
is off ("service ``backend`` depends on undefined service ``victoria-logs``"),
and simply deleting it would break the cold start whenever the tier is on. The
lightweight mode therefore merges ``required: false`` onto the edge:

.. code:: yaml

    backend:
      depends_on:
        victoria-logs:
          required: false

With the observability profile active, ``condition: service_started`` is honoured
exactly as in the full mode. With it off, the wait is skipped and
``settings.py`` prints "syslog server is not reachable. skipping syslog handler
setup." and logs to the console - the fallback #1614 relies on, which the
application already had.

Container logs of ``postgis`` and ``frontend``
----------------------------------------------

Those two services ship their stdout/stderr into the log store through Docker's
syslog log driver, aimed at the host loopback port ``victoria-logs`` publishes.
A syslog driver writing into a sink which is not there does not fail: the
container starts, reports healthy and its output is gone without a word. So the
lightweight mode overrides the block instead of inheriting it, and says where its
container logs go:

.. code:: yaml

    postgis:
      logging: !override
        driver: json-file
        options:
          max-size: "10m"
          max-file: "2"

The output is then ``docker compose logs postgis``, capped at 2 x 10 MB per
container so the memory-cheap mode cannot be the reason a host runs out of disk
(the retention question itself belongs to #1497). The structured application
logs are not affected by this block: they reach the store over the project
network when the observability tier is on, without needing a published port.

The two operator UIs
--------------------

The edge proxies ``/grafana/``, ``/pgadmin/`` and ``/flower/`` to those service
names. Without the tier those three paths answer 502, and nothing else changes:
no page, API or configuration inside MrMap links to them (checked over the
frontend sources and the backend apps). The task history of the application's
own job drawer, and the Celery state it is built from, do not need Flower.

The check containers
--------------------

Gating the testing tier removes the largest accidental memory line of a
development stack: ``up -d`` used to start ``django-tests`` and ``behave`` as
services, which means it started the suites. #1613 measured what that is worth -
a container peaking at 2885 M of almost purely anonymous memory for the full
unit suite, +3.3 GiB of charge over the idle stack.

They stay runnable, because ``docker compose run`` names the service explicitly
and Compose starts a named service regardless of its profile (verified against
Compose v5.6.0). This is what keeps ``.github/workflows/quality-assurance.yml``
untouched: its ``run --rm <service>`` lines need no profile and no flag. A
``docker compose up`` of a specific check service is now the one command which
refuses, and it is the command the repository's own instructions never use.

Health, readiness and restart policy
------------------------------------

* Healthchecks are unchanged for every service which runs. The core tier does
  not gain, lose or weaken one; ``pg_isready``, the Redis ``PING``, the Celery
  ``inspect ping`` and the beat heartbeat file all still gate what gated on them
  before.
* ``backend`` no longer waits for a log store which is not there, and still
  waits for it when it is (`The log store the backend waits for`_).
* Restart policy (#901) is kept for every always-on core service in every
  combination, which the smoke check asserts by name. What it cannot do is
  revive a tier: a profiled service which was never created has no container and
  therefore no restart policy, so after a host reboot a lightweight deployment
  comes back **as configured** - the core without the tier. An operator who
  wants the tier permanently on a host should set ``COMPOSE_PROFILES`` in
  ``.env`` and bring the stack up once with it, which creates the containers and
  gives them their ``unless-stopped`` policy.
* The status UI is not affected: ``backend/system/status.py`` reports the
  ``database`` / ``redis`` / ``workers`` / ``beat`` components, all core, and
  simply lists the containers the project has.

What still has to be configured
-------------------------------

Compose interpolates every service in the files it reads, including one a
profile switched off - so a lightweight ``.env`` still needs
``GRAFANA_ADMIN_USER``/``GRAFANA_ADMIN_PASSWORD`` and ``PGADMIN_PASSWORD``. The
tier does not run them, but the file still names them. Nothing about ``.env`` got
easier with #1614, and an agent's copied ``.env`` is already complete.

The budget
==========

The rows below are **derived from the measured per-container numbers of #1613**
by removing the tier's own measured rows - the same arithmetic that page uses
when it says that dropping the three UIs leaves 1613 M of charge. They are a
budget, not a second measurement: no stack of this branch was sampled, and the
row labelled "measured" says exactly what was.

.. list-table:: Warm idle, one development stack (M = MiB of the cgroup charge)
   :header-rows: 1
   :widths: 34 14 16 36

   * - combination
     - charge p50
     - committed p50
     - basis
   * - full (the 12-service stack of ``develop``)
     - 3949 M
     - 2005 M
     - **measured** in :ref:`#1613 <runtime-memory-baselines>`, warm idle, no
       traffic
   * - **lightweight default (core only)**
     - 1558 M
     - 1340 M
     - derived: 3949 M − 2391 M of charge, 2005 M − 665 M committed
   * - lightweight + ``observability``
     - 1613 M
     - 1379 M
     - derived; equals #1613's own "dropping all three UIs" row, which is the
       cross-check of the arithmetic
   * - lightweight + ``admin``
     - 1936 M
     - 1621 M
     - derived
   * - lightweight + both tiers
     - 3949 M
     - 2005 M
     - derived; equals the measured row by construction, which is the other
       half of the same cross-check

The tier costs 2391 M of charge and 665 M of committed: **61 % of the charge,
33 % of the reservation**. That lopsided split is the honest headline of this
page and it is #1613's, not a new claim - grafana's 1958 M were 82 % reclaimable
page cache. The lightweight mode is therefore worth most on a host which is
short of *addressable* memory and least on one which is merely short of free
cache, and it does not touch the reservation which dominates: the Celery prefork
pool and the server shape, which epic #1612 takes up in #1615 and #1617.

Startup was **not** measured for the core-only set. What supports saying
something about it without a measurement: #1613's boot to all-containers-up was
124 s for the 12-service stack, no service ``depends_on`` the admin tier, and
only ``victoria-logs`` is waited for at all (with ``service_started``) - so the
lightweight set cannot take longer than that, and the saving is the tail of
``grafana``'s own start, not a share of the 124 s.

To replace the derived rows with measured ones, the read-only sampler of #1613
takes the phase names, so a re-run extends the table instead of contradicting
it:

.. code:: console

    scripts/stack_memory_profile sample --project <compose-project> --phase lite-warm-idle \
        --duration 600 --out runs.jsonl
    scripts/stack_memory_profile sample --project <compose-project> --phase lite-boot \
        --during 'docker compose up -d' --out runs.jsonl
    scripts/stack_memory_profile report --in runs.jsonl

Re-measuring means starting a stack: check ``scripts/agent_capacity`` first, run
it in a job-owned project and tear that project down again
(:ref:`development-agent-capacity`). The repeatable regression reporting which owns doing
this on a schedule is #1623.

Upgrade behaviour
=================

Nothing to migrate, and that is the point of the shape:

* **The full deployment contract is unchanged.** ``docker-compose.yml`` carries
  no profile, no ``required: false`` and no ``logging`` change. An existing
  deployment which pulls a new version and runs the command of the installation
  document gets what it got before, including the cold-start wait for the log
  store and the syslog shipping. The versioned migration path #1614 was asked to
  provide if it could not keep the contract, it does not need.
* **The new file is additive.** It changes the service set of an invocation that
  names it and of no other. A deployment that wants the low-memory mode adopts
  it by adding it to its ``COMPOSE_FILE`` / ``-f`` list, last, and takes the
  tiering decisions - which of the three tiers it wants - at that moment.
* **Rolling a mix of the two over the same volumes is safe.** The tiers share no
  state with the core except the log store's own volume (``vlogs-data``,
  ``grafana-data``), and both keep theirs when the tier is off; nothing prunes
  them. Dropping the observability tier does not delete a single log line which
  was already stored - and does not store new ones.
* **Rollout to the operator documentation is #1624's**, together with the
  runbook of the full memory work of epic #1612.

Validating the matrix
=====================

.. code:: console

    $ python3 scripts/compose_profiles_smoke.py
    OK    full deployment (the documented contract): runs backend celery-beat ...
    ...
    9 supported combination(s) agree with the matrix of #1614

It resolves each supported combination with
``docker compose config --no-interpolate --format json`` - ``.env`` stays out of
it, so it runs on a bare runner - and checks the active service set, the
classification of every service, that no running service depends on one no
profile activates, that no running service ships its container log to a log store
which is not running, that the always-on core keeps ``restart: unless-stopped``,
and that both halves of the ``depends_on`` seam are where they belong. It starts
nothing. Its rules are tested offline against synthetic configurations by
``scripts/test_compose_profiles_smoke.py``, which CI runs through
``scripts/check_repo_tooling.sh``; that suite also runs the real files where a
docker CLI is available.

Two sibling checks sweep every ``docker-compose*.yml`` in the checkout by glob,
so the new file is judged with them and needs no wiring:
``scripts/static_mounts_smoke.py`` (#922/#1027, nothing may mount the image's
static roots) and ``scripts/test_validator_retirement.py`` (#1529, no retired
validator may come back, and the shared networks must survive the resolution).

When to touch this
==================

A new service has to be classified: into ``TIERS`` of the smoke check plus the
matrix above, or into the core. Leaving it out is the drift this page's check
exists to catch, because an unclassified service is a service whose tier nobody
decided - and "which mode runs this" is the question #1614 exists to answer.
Raising a tier's memory budget, or moving a service between tiers, is a change
to this page and to the check's table together, not to one of them.
