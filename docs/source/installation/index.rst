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
* To enable Postgres slow statement logging, run (hot, no restart):
  ``ALTER SYSTEM SET log_min_duration_statement = '400ms'; SELECT pg_reload_conf();``

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

Recreate the ``frontend`` container to apply the injected script, the location
and the log driver. Reporting lives in nginx, so it is there where the image
serves the app and not in the vite dev server of ``frontend``.
