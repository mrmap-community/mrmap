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


2. Start MrMap
==============

Open a terminal and change working directory to the path you unzipped the project to. You can start all configured services with the command ``docker compose -f docker-compose.yml up --build frontend``. After that, MrMap should be reachable under https://localhost

.. note::
  The initial credentials of MrMap are: username = ``mrmap``, password = ``mrmap``

