.. _development-environment:


=====================
Environment Variables
=====================

We provide default environment files with the repository. All files starts with ``.env.{purpose}``


MrMap applications
##################

``MRMAP_USER``
**************

Used by setup command to create initial superuser.


``MRMAP_PASSWORD``
******************

Used by setup command while creating superuser to provide initial password.


``DJANGO_DEBUG``
*********************

Used to activate debugging features. See `django docs <https://docs.djangoproject.com/en/3.2/ref/settings/#debug>`__ for details.

.. warning::
    never use DJANGO_DEBUG=1 in pruction environment!


``DJANGO_SECRET_KEY``
*********************

Used to configure the secrete key which is used by django. See `django docs <https://docs.djangoproject.com/en/3.2/ref/settings/#secret-key>`__ for details.

.. warning::
    use a strong secret and never the default from the repository!

``DJANGO_ALLOWED_HOSTS``
************************

Used to configure the allowed hosts from the origin header. The entries are separated by ``;`` and/or ``,``. docker-compose.yml passes this variable to ``backend``, ``celery-worker`` and ``celery-beat``; it may also be set in the ``.env`` file of a deployment. It is added to the hosts of ``DJANGO_ALLOWED_HOST_DEFAULTS`` and to the host of ``EXTERNAL_BASE_URL``, which are allowed in any case. See `django docs <https://docs.djangoproject.com/en/3.2/ref/settings/#allowed-hosts>`__ for details.

.. note::
    Requests with a Host which is not allowed are answered with HTTP 400 by django, which is most visible when a deployment is reached by an IP address or by a second name next to ``EXTERNAL_BASE_URL`` -- list those names here.

``DJANGO_ALLOWED_HOST_DEFAULTS``
********************************

The internal preset of the host allow-list which the image ships with: ``localhost;127.0.0.1;[::1];mrmap-appserver;172.17.0.1;testserver``. These are the hosts of the callers which reach the backend without a browser header: the ETF validator answering to ``MRMAP_BASE_URL_FOR_ETF``, the development stack on localhost, the docker bridge address and the django test client. Setting this variable **replaces** that preset; deployments normally never set it -- extend the allow-list with ``DJANGO_ALLOWED_HOSTS`` instead.

``DJANGO_TIME_ZONE``
********************

Used to configure the timezone which shall be used in MrMap. See `django docs <https://docs.djangoproject.com/en/3.2/ref/settings/#time-zone>`__ for details.

``SQL_ENGINE``
**************

Used to configure the sql engine which is used. See `django docs <https://docs.djangoproject.com/en/3.2/ref/settings/#engine>`__ for details.


``SQL_DATABASE``
****************

Used to configure the name of the schema. See `django docs <https://docs.djangoproject.com/en/3.2/ref/settings/#name>`__ for details.


``SQL_USER``
************

Used to configure the name of the user which shall be used to connect to the database. See `django docs <https://docs.djangoproject.com/en/3.2/ref/settings/#user>`__ for details.


``SQL_PASSWORD``
****************

Used to configure the password of the user which shall be used to connect to the database. See `django docs <https://docs.djangoproject.com/en/3.2/ref/settings/#password>`__ for details.


``SQL_HOST``
************

Used to configure the ip/dns name of the database host. See `django docs <https://docs.djangoproject.com/en/3.2/ref/settings/#host>`__ for details.


``SQL_PORT``
************

Used to configure the port of the database host. See `django docs <https://docs.djangoproject.com/en/3.2/ref/settings/#port>`__ for details.


``REDIS_HOST``
**************

Used to configure the ip/dns name of the redis host.


``REDIS_PORT``
**************

Used to configure the port of the redis host.


``MAPSERVER_URL``
*****************

Used to configure the url of the mapservice instance.

``MAPSERVER_SECURITY_MASK_FILE_PATH``
*************************************

Used to configure the map file for security proxy. This file needed to be installed on the used mapserver which is configured by ``MAPSERVER_URL``.


``MRMAP_SLOW_REQUEST_THRESHOLD_MS``
***********************************

Used to configure the duration of a request in milliseconds which is worth a ``Slow Request Detected`` record and the JSON dump of its details. The default is 400.


``MRMAP_SLOW_REQUEST_DUMP_RETENTION_DAYS``
******************************************

Used to configure how many days the per request JSON dumps below the media root are kept before the periodic sweep of ``system.tasks`` deletes them. The default is 14, which is how long the central log store keeps the syslog line that points at them; 0 keeps them until the cap below is reached.


``MRMAP_SLOW_REQUEST_DUMP_MAX_FILES``
*************************************

Used to configure how many of those dumps may lie around at most; the oldest beyond that number are taken back by the same sweep. 0 answers no limit, which leaves the age bound alone.


``MRMAP_HARVEST_IMPORT_BATCH_SIZE``
***********************************

Used to configure how many stored metadata files a single import task writes to the database. The fan-out which imports harvested records publishes one task per chunk of that many records instead of one task per record, so the number of task round-trips a harvest costs is bounded by the chunk count and the import is limited by the database again. The default is 250, which takes a harvest of 70,000 records to ~280 tasks. This is not ``max_step_size`` of a harvesting job: that one is the page size the catalogue is asked with and is chosen per catalogue.


``MRMAP_HARVEST_IMPORT_PROGRESS_STEPS`` and ``MRMAP_HARVEST_IMPORT_PROGRESS_SECONDS``
**************************************************************************************

Used to configure how the draining import backlog reports its progress to the background process of the harvest (#958). A worker coalesces the files it has committed and answers them as one bulk increment of the progress once it has piled up this many steps or this many seconds have passed since its last report - whichever comes first. The defaults are 200 steps and 30 seconds, which keep a catalogue of 400k+ records to a few thousand single-row updates instead of one contended row-lock per imported file. ``MRMAP_HARVEST_IMPORT_PROGRESS_SECONDS=0`` disables the time trigger alone; the step threshold then coalesces alone too.

``CELERY_WORKER_CONCURRENCY``
*****************************

Used to configure how many slots a celery worker process runs with. docker-compose.yml passes it to ``celery-worker``; empty keeps celery's own default of one slot per CPU core and ``auto`` sizes the prefork pool by the cgroup quota of the container. It is the knob for a bigger worker, so that changing worker concurrency never makes a deployment override the worker command and thereby restate - and freeze - the queue list of the release the override was written for; see :ref:`celery-queues` (#1040).


The web tier
############

The HTTP of the ``backend`` container is served by ``gunicorn`` with ``gthread``
workers and the WSGI application; its websockets by a second, small ``gunicorn``
with ASGI workers on port 8002, which the edge of the frontend forwards ``/ws``
to. The split is #1032. Every view of MrMap is sync, so under an ASGI worker the
view work runs on threads off the event loop while that loop keeps the sockets of
the same worker - one GIL for the two of them - and the bill arrives twice: the
view is slower and its neighbours wait. Which worker of a burst did how much also
differs: for one and the same burst of 8 builds the four workers of the ASGI
configuration burned 18.4, 10.5, 7.7 and 4.5 CPU seconds, those of the
``gthread`` configuration 10.2, 8.8, 8.5 and 8.2. Measured on one deployment of
this application behind a 4-core quota, with 4 workers, that burst of 8
``/api/schema`` builds (the CPU bound endpoint of the report, ~2.4 s of building
each), against an otherwise idle server:

====================================  ==========  ==============  ============
Server of ``/api``                    Cores used  Build, alone    Cheap peer
====================================  ==========  ==============  ============
ASGI workers, 4 (was: the default)    1.8 - 2.2   2.9 s           181 - 233 ms
``gthread``, 4 workers x 4 threads    2.7         2.5 s           41 - 67 ms
``gthread``, 4 workers x 1 thread     3.8         2.4 s           4.1 s
``gthread``, 4 workers x 8 threads    2.1 - 3.4   2.4 s           45 - 95 ms
====================================  ==========  ==============  ============

The cheap peer is a request to an unrouted url of the same server - it walks the
whole middleware chain and answers 404 in 5 ms while the server is idle - asked
ten times while the burst is in flight. It is the number the issue is about: an
endpoint which does no work of its own must not pay for what its neighbours do.
The ``gthread`` row with four threads is the shipped command line of
``backend/.bash_scripts/startup.sh``, measured twice: once as the bare gunicorn
invocation and once by starting that script itself.

``GUNICORN_WORKERS``
********************

How many HTTP worker *processes* the backend runs; docker-compose.yml passes it
to ``backend`` with a default of 4. CPU bound views parallelize per process and
not per thread, because the interpreter runs one of them at a time - so a
deployment whose API traffic is CPU bound gets its lanes from this number, and
the honest way to size it is the number of cores it gives to the web tier. The
database pays for it: each worker holds its own connection pool (see
``DATABASES`` of the settings), so this is also the multiplier of the connections
a backend may hold at once.

``GUNICORN_THREADS``
********************

How many requests one HTTP worker answers at a time; docker-compose.yml passes it
to ``backend`` with a default of 4. This is the depth of the queue in front of one
worker, and it is what keeps a cheap request from waiting behind a slow one: a
request which arrives at a worker whose threads are all taken waits in that
worker's own queue, behind whatever it is already doing, while a worker with a
free thread answers it on the spot. The three ``gthread`` rows above are the same
four workers with one, four and eight threads, and they pull apart in the same
measured direction: the fewer the threads, the more of the burst's CPU arrives and
the longer the cheap peer waits. 4 is what is shipped, because the issue is about
that peer. It is not a promise of more cores - a CPU bound view cannot use two of
them in one process - so a deployment which measures CPU and not queueing raises
``GUNICORN_WORKERS`` instead.

``GUNICORN_WS_WORKERS``
***********************

How many ASGI worker processes serve the websockets on port 8002; docker-compose.yml
passes it to ``backend`` with a default of 1. Open websockets are idle and I/O
bound, so one event loop carries the connections of a whole deployment; the
variable is there for a deployment with an unusual number of simultaneous
connections.
