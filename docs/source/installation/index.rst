.. _installation:


============
Installation
============

The MrMap project is full dockerized. All dependend services MrMap needs are also provided as docker containers. The only thing you have to install on your system is a docker enginge and docker compose. See the table below to get the right version of docker engine and docker compose.

**Requirements**

.. list-table::
   :widths: 50 50
   :header-rows: 1

   * - Dependency
     - Minimum Version
   * - `docker engine <https://docs.docker.com/engine/install>`_
     - >= 20.10.23
   * - `docker compose cli plugin <https://docs.docker.com/compose/install>`_
     - >= 2.17.2

.. warning::
    Make sure that the user you running docker-compose from, has managing rights for docker. For linux developers see `Post-installation steps for Linux <https://docs.docker.com/engine/install/linux-postinstall/>`_

Proxy pre setup
===============
If you need to communicate via proxy you'll need to configure your docker environment as well. 
You need two configuration files to tell the docker engine and the docker compose plugin which proxy shall be used.

Docker-Engine config
--------------------

.. code-block:: console

    $ cat /etc/systemd/system/docker.service.d/http-proxy.conf
    [Service]
    Environment="HTTP_PROXY=http://proxy:8080/"
    Environment="HTTPS_PROXY=http://proxy:8080/"
    Environment="FTP_PROXY=http://proxy:8080/"
    Environment="NO_PROXY=localhost,127.0.0.1/"


Docker client config file
-------------------------

.. code-block:: console

    $ cat ~/.docker/config.json
    {
      "proxies": {
          "default": {
              "httpProxy": "http://proxy:8080",
              "httpsProxy": "http://proxy:8080",
              "noProxy": "localhost"
          }
      }
    }


1. Download MrMap
=================

Download the project from `github <https://github.com/mrmap-community/mrmap/archive/refs/heads/master.zip>`_ and unzip it to any installation folder you like.

2. Create .env file
===================

create .env file under your mrmap path with the following variables. Please setup your own strong passwords! 

.. code-block:: env

    EXTERNAL_BASE_URL=mrmap.example.com
    EXTERNAL_PORT=443
    EXTERNAL_SCHEME=https
    DB_USER=someuser
    DB_PASSWORD=supersecurepassword
    DJANGO_ADMIN_USER=mrmap
    DJANGO_ADMIN_PASSWORD=supersecurepassword
    DJANGO_SECRET_KEY=mrmap-dev-secret-key-change-me-in-production
    GRAFANA_ADMIN_USER=admin
    GRAFANA_ADMIN_PASSWORD=supersecurepassword
    PGADMIN_USER=admin@example.com
    PGADMIN_PASSWORD=supersecurepassword

``PGADMIN_USER`` configures the pgadmin administrator login and falls back to ``admin@example.com`` if it is not set; pgadmin rejects an address without a fully qualified domain (for example ``admin@localhost``) at startup and then crash-loops, so keep this value a valid email address.

Beside these required variables ``.env`` accepts the optional ``DJANGO_ALLOWED_HOSTS``: a ``;`` or ``,`` separated list of additional names and addresses the deployment is reached by, for example ``DJANGO_ALLOWED_HOSTS=10.0.0.12,mrmap.internal``. The host of ``EXTERNAL_BASE_URL`` and the internal presets of the image (``localhost``, loopback addresses, the compose service names) are always allowed; every other name or address answers HTTP 400 until it is listed here. See :ref:`development-environment` for both variables.

..warning::
    If some of the environment variables are not configured, the docker compose command will fail with erro message like this: error while interpolating services.backend.environment.EXTERNAL_BASE_URL: required variable EXTERNAL_BASE_URL is missing a value: Please configure EXTERNAL_BASE_URL in the .env file.

2. Start MrMap
==============

Open a terminal and change working directory to the path you unzipped the project to. You can start all configured services with the command ``docker compose -f docker-compose.yml up --build frontend``. After that, MrMap should be reachable under http://localhost


Docker health reporting
=======================

The status API reads container lifecycle and healthcheck results from Docker.
It does not run probes, maintain a background thread, or retrieve periodic tasks.
Periodic tasks remain available through their existing JSON:API resource.

The private ``docker-api`` proxy permits only GET requests to container list and
inspect endpoints. Only the proxy mounts the Docker socket; no proxy port is
published on the host. The backend connects over the internal ``docker-status``
network. Container inspection includes configuration metadata, so keep access to
this network restricted to the backend. The read-only socket mount itself is
not the authorization boundary: the proxy's method/path allowlist is.

Compose passes its project name to the backend as ``SYSTEM_STATUS_DOCKER_PROJECT``.
Containers are selected by Compose project/service labels, including stopped
containers and worker replicas, excluding one-off commands. Each worker uses
its unique container hostname and checks only its own Celery node. PostgreSQL
uses ``pg_isready`` and Redis uses ``PING``. Beat writes a local heartbeat after
successful scheduler iterations; its Docker healthcheck checks the file's age.

Recreate the backend, database, Redis, worker, and Beat containers to apply the
healthchecks and networking. Start ``docker-api`` before the backend. Recreating
workers or the database should be scheduled around active work; no schema
migration is required. Containers not yet recreated may show unknown health.

Missing containers or healthchecks report unknown; exited containers report
down; unhealthy or partially failed replicas report degraded. Docker API failure
reports unknown. Detection latency follows healthcheck intervals and retries;
a reported healthy container does not prove task execution succeeded.


Surviving a host reboot
=======================

Every service of ``docker-compose.yml`` declares ``restart: unless-stopped``, so
after a host reboot the docker engine starts the whole stack again by itself;
``docker compose up -d`` only has to converge it. Convergence is real, not a
race: after an unclean shutdown Postgres replays its write-ahead log before it
serves queries, which on a busy instance can take minutes, and during that
window the postmaster already listens on its port but refuses every connection.
The backend, worker and Beat containers therefore probe the database with
``pg_isready`` in their entrypoint (``backend/.bash_scripts/wait_db.sh``) - "up"
means "accepting connections", not "port open" - and the backend additionally
retries ``manage.py migrate``, the true readiness test, a bounded number of
times before exiting. The ``backend`` and Celery services gate on the
``postgis`` (``pg_isready``) and ``redis`` healthchecks via ``depends_on``, so a
plain ``docker compose up -d`` orders the stack as well.

``unless-stopped`` deliberately and not ``always``: a stack an operator stopped
with ``docker compose stop`` or ``down`` stays stopped across reboots, while
``always`` would bring it back against that decision. One-off containers started
with ``docker compose run`` never inherit a service's restart policy and never
come back on boot.

The wait and retry budgets are configurable (``WAIT_DB_ATTEMPTS``,
``WAIT_DB_DELAY``, ``MIGRATE_ATTEMPTS``, ``MIGRATE_RETRY_DELAY``); a container
that exhausts them exits non-zero and the restart policy tries the whole
sequence again.


Central log aggregation
=======================

MrMap emits RFC 5424 syslog records (slow requests include a structured-data
pointer to the per-request JSON dump under the media root). VictoriaLogs is
the central log store: it receives that stream through its native syslog
receiver, parses the structured-data parameters (``metaSDID@Details.json``
etc.) into queryable fields and keeps 14 days of logs (``-retentionPeriod``).
VictoriaLogs publishes no HTTP port; only its loopback UDP port
(``127.0.0.1:5514/udp``) is exposed so that Docker's own ``syslog`` log-driver
can ship container stdout/stderr into it — add the same ``logging:`` block as
``postgis`` to any service, e.g. to get Postgres ``LOG: duration:`` statements
into the same store.

Grafana is the single authenticated web entry point, published under
``/grafana/``. It ships with the VictoriaLogs datasource and a "MrMap slow
requests" dashboard pre-provisioned from ``docker/grafana/``; login with
``GRAFANA_ADMIN_USER`` / ``GRAFANA_ADMIN_PASSWORD``.

* ``MRMAP_SYSLOG_HOST`` / ``MRMAP_SYSLOG_PORT`` point the backend syslog
  handler at any RFC 5424 receiver; the default is ``victoria-logs:5514``,
  the compose service.
* ``MRMAP_SLOW_REQUEST_THRESHOLD_MS`` is the duration of a request in milliseconds
  which is worth a "Slow Request Detected" record; the default is 400.
* To enable Postgres slow statement logging, run (hot, no restart):
  ``ALTER SYSTEM SET log_min_duration_statement = '400ms'; SELECT pg_reload_conf();``

Every record the syslog handler answers leaves the verbose details of that record as
a JSON file in ``<MEDIA_ROOT>/logs``. Nothing deleted them, so a deployment which ran
for a few weeks held a few hundred thousand of them (#888). The periodic task
``system.tasks.delete_old_slow_request_dumps`` takes them back: it is created on
migrate, beat hands it over hourly, and it deletes the dumps which are older than
``MRMAP_SLOW_REQUEST_DUMP_RETENTION_DAYS`` days (default 14, the retention of
VictoriaLogs above) as well as everything beyond
``MRMAP_SLOW_REQUEST_DUMP_MAX_FILES`` dumps (default 0, which answers no limit and
leaves the age bound alone). A dump which is gone costs the per-request SQL detail of
that one request; the syslog line which pointed at it stays in the log store for its
whole retention. ``MRMAP_SLOW_REQUEST_DUMP_RETENTION_DAYS=0`` keeps the dumps until
the cap is reached or until somebody reads them.

Those dumps carry complete SQL statements, the internal host names which answered the
request and its metadata, and only the syslog line points at them — no screen of
MrMap does. They are therefore not served over the media route: ``/media/logs/`` is
answered with 404 by the nginx of the stack (``docker/nginx/mrmap.conf``) and by the
backend itself for every origin it is reached from, so a deployment which serves the
backend without that nginx is not more open than one which serves it with it. Recreate
the ``frontend`` service, which runs that nginx, to apply the location. Read the dumps
on the filesystem of the backend, for as long as the task above keeps them:

.. code-block:: console

    docker compose exec backend ls /var/mrmap/backend/media/logs

Errors of the user's browser take the same route through the ``frontend``
service, which carries that ``logging:`` block as well: its access log and
error log are in the store too. The image injects ``error-beacon.js`` into the
built ``index.html`` before the app bundle, and that script reports uncaught
exceptions, unhandled promise rejections and failed resource loads to
``/api/system/error``. Nginx answers that url itself: the fields of a report
travel in the query string, so nginx has them at log time without ever reading
a request body, and one accepted report is one line of
``/var/log/nginx/frontend-error.log``, which is symlinked to stdout like the
``access.log`` of the image. The backend has no such endpoint, so a request
which reaches it without nginx is answered 404.

Such a line names the ``source`` (``error``, ``rejection`` or ``resource``),
the ``msg``, the ``url`` of the script which failed, the ``page`` the user was
on, the ``stack``, the ``ua``, the ``ip`` of the client and the ``answered``
status; every value is percent encoded as it arrived. To count them per
deployment:

.. code-block:: console

    "Frontend Error" | extract "source=\"<source>\"" | stats by (source) count() as n

Failing api calls are not reported from the browser: the access log of this
very nginx already knows the status code of every call, and a browser report
would have the beacon post at exactly the api that is down.

What one address may write is bounded. ``limit_req`` takes five reports a
second with a burst of 50 and answers 429 beyond that, and only an accepted
report with a message of its own writes a line — a probe, a GET and anything
over the limit stay silent. The refused attempts are still readable in the
nginx error log ("limiting requests"), which travels with the same block. One
report is one request line, so nginx refuses one above its 8k with a 414; the
beacon keeps itself below that, deduplicates identical reports for 30 seconds
and caps a page load at 20 reports.

Script, location and log driver come with the image of the ``frontend`` service,
so that container has to be recreated to apply them. An existing deployment
holds the built frontend in the ``frontend-static`` volume, and Docker fills
such a volume from the image only while it is still empty, so the volume goes
with the container (``docker volume ls`` names it after the project):

.. code-block:: console

    docker compose rm -fs frontend
    docker volume rm mrmap_frontend-static
    docker compose up -d --build frontend

Reporting lives in nginx, so it exists where the built app is served behind it:
the development server of the frontend (``npm run dev``) answers without nginx
and reports nothing.

Database tuning
===============

The reference deployment ships Postgres with Just-in-Time compilation switched
off (``command: ["postgres", "-c", "jit=off"]`` on the ``postgis`` service), so a
fresh ``docker compose up`` is fast without any manual step.

The service-list endpoints (for example ``GET /api/registry/csw``) are answered by
one annotated query carrying dozens of correlated sub-selects (alert flags,
monitoring/update/harvest state, ``elementCount``). Its planner cost is far above
Postgres' default ``jit_above_cost = 100000``, so the stock image JIT-compiles that
plan on *every* request. These are one-shot OLTP queries whose plan is never reused,
so the compile time is pure overhead and has no chance to amortize: measured on the
reference stack the query dropped from ``721 ms`` to ``363 ms`` once JIT was off
(``EXPLAIN ANALYZE`` loses its ``JIT:`` section entirely, issue ``#871``).

Nothing in mrmap loses a JIT speed-up by this: the genuinely heavy reads -- the
harvest day statistics and the ``tsvector`` search -- plan at a few thousand cost,
well under ``jit_above_cost``, so they were never JIT-compiled in the first place.
A raised ``jit_above_cost`` was rejected as brittle: the list query's cost grows
with the number of harvested records, so it would cross any fixed threshold again.

The setting is passed to the server process, not with ``ALTER SYSTEM`` (which would
write into the shared data directory and leak into the test databases). It therefore
applies to every database on that server. A deployment that wants JIT back removes
the ``command:`` line or raises ``jit_above_cost`` instead.

