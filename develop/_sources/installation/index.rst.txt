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
     - 20
   * - `docker compose <https://docs.docker.com/compose/install>`_
     - 1.28

.. warning::
    Make sure that the user you running docker-compose from, has managing rights for docker. For linux developers see `Post-installation steps for Linux <https://docs.docker.com/engine/install/linux-postinstall/>`_

1. Download MrMap
*****************

Download the project from `github <https://github.com/mrmap-community/mrmap/archive/refs/heads/develop.zip>`_ and unzip it to any installation folder you like.


2. Start MrMap
**************

Open a terminal and change working directory to the path you unzipped the project to. You can start all configured services with the command ``docker-compose -f docker-compose.yml up --build``. After that, all services should be started properly.

Environment Variables
*********************

