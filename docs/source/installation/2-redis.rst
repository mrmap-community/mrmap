.. _installation-2-redis:

========
2. Redis
========

Installation
************

`Redis <https://redis.io/>`_ is an in-memory key-value store which MrMap employs for caching and queuing. This section entails the installation and configuration of a local Redis instance. If you already have a Redis service in place, skip to :ref:`the next section <installation-3-mapserver>`.

.. note::
    MrMap require Redis v4.0 or higher. If your distribution does not offer a recent enough release, you will need to build Redis from source. Please see `the Redis installation documentation <https://github.com/redis/redis>`_ for further details.

Debian
======

.. code-block::

   apt install -y redis-server


You may wish to modify the Redis configuration at ``/etc/redis.conf`` or ``/etc/redis/redis.conf``, however in most cases the default configuration is sufficient.

Verify Service Status
*********************

Use the ``redis-cli`` utility to ensure the Redis service is functional:

.. code-block::

   $ redis-cli ping
   PONG

