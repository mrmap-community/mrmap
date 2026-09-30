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
    OPENOBSERVE_USER=admin@example.com
    OPENOBSERVE_PASSWORD=supersecurepassword
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
