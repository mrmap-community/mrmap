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
