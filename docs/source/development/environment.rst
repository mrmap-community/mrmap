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

.. note::
    Since #1473 the application **refuses to start** when this variable is
    missing and ``MRMAP_PRODUCTION`` is ``True``. The fallback used to be a new
    random key on every import, which works until the next restart and then
    invalidates every session, knox token and signed payload at once -- so a
    deployment which believed it had set the key but had not could not tell.
    Outside production the random fallback stays, for throwaway checkouts and CI.

``DJANGO_ALLOWED_HOSTS``
************************

Used to configure the allowed hosts from the origin header. The entries are separated by ``;`` and/or ``,``. docker-compose.yml passes this variable to ``backend``, ``celery-worker`` and ``celery-beat``; it may also be set in the ``.env`` file of a deployment. It is added to the hosts of ``DJANGO_ALLOWED_HOST_DEFAULTS`` and to the host of ``EXTERNAL_BASE_URL``, which are allowed in any case. See `django docs <https://docs.djangoproject.com/en/3.2/ref/settings/#allowed-hosts>`__ for details.

.. note::
    Requests with a Host which is not allowed are answered with HTTP 400 by django, which is most visible when a deployment is reached by an IP address or by a second name next to ``EXTERNAL_BASE_URL`` -- list those names here.

``DJANGO_ALLOWED_HOST_DEFAULTS``
********************************

The internal preset of the host allow-list which the image ships with: ``localhost;127.0.0.1;[::1];mrmap-appserver;172.17.0.1;testserver``. These are the hosts of the callers which reach the backend without a browser header: the deployment's own service address, the development stack on localhost, the docker bridge address and the django test client. Setting this variable **replaces** that preset; deployments normally never set it -- extend the allow-list with ``DJANGO_ALLOWED_HOSTS`` instead.

HTTP hardening of a deployment (#1473)
--------------------------------------

The variables below decide the cookie flags, the TLS redirect, HSTS, the framing
answer, the cross-origin allowance and the ``Content-Security-Policy`` of the
backend. All of them are read by ``MrMap/settings.py`` at import time and all of
them are overridable on their own, because a deployment which has to narrow one
part of the block must not have to drop the rest. Boolean values use the spelling
of ``MRMAP_PRODUCTION`` itself -- ``True``/``False`` as a string; anything else
(including an empty value) means "use the default", and ``True`` is the only
string which means true.

.. note::
    One prerequisite decides whether the redirect of ``DJANGO_SECURE_SSL_REDIRECT``
    is correct at all: the edge in front of the backend has to *name the protocol
    it terminated*. Django reads the protocol from ``X-Forwarded-Proto`` and the
    host from ``Host`` -- the pair ``SECURE_PROXY_SSL_HEADER`` /
    ``USE_X_FORWARDED_HOST`` of the settings is what makes those two headers of
    the proxy authoritative while a forged value on a direct connection gets no
    say. The nginx of ``docker/nginx/mrmap.conf`` therefore does not pass the
    client value through: a ``map`` replaces a missing ``X-Forwarded-Proto`` with
    the protocol of the connection at the edge. A deployment with another edge in
    front owes the same normalization, or Django reads its own https traffic as
    plain http and answers every request with a ``301`` to the https origin it
    just arrived on -- the loop a deployment in this situation reports.
    ``EXTERNAL_SCHEME`` is the deployment's own statement of that protocol and
    reaches the frontend bundle as ``VITE_API_SCHEMA``; it does **not** tell the
    backend anything. So: a deployment whose TLS really terminates in front and
    which names itself ``MRMAP_PRODUCTION=True`` gets the block and is fine; a
    deployment which answers plain http -- the ``http://localhost`` quickstart of
    the installation page, or anything behind a terminator which forwards plain
    http and cannot add the header -- sets ``DJANGO_SECURE_SSL_REDIRECT=False``,
    or no request is ever answered.

``DJANGO_SECURE_SSL_REDIRECT``
******************************

Whether a plain-http request is answered with a ``301`` to the https URL of the
same address. Default: ``MRMAP_PRODUCTION`` -- on in production, off in a
development stack, which does not speak https at all. See the note above: this is
the one knob of the block which can stop a deployment answering requests, and the
opt-out for a deployment which really does answer plain http. Narrowing it gives
up nothing but the enforcement: the browser is then free to keep talking http to
the deployment, so the HSTS entry below is what keeps it honest instead.

``DJANGO_SECURE_HSTS_SECONDS``
******************************

The ``max-age`` of the ``Strict-Transport-Security`` header, in seconds. Default:
``31536000`` (a year) under ``MRMAP_PRODUCTION``, ``0`` -- no header -- outside.
``0`` means the browser may talk plain http to this deployment tomorrow, which is
why the settings log a warning when the redirect above is on and this value is
``0``. Set the number the deployment's own certificate life supports; anything
below the renewal window of the certificate is a deployment which can lock itself
out of its own https.

``DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS``
*****************************************

Whether the HSTS entry above also covers every subdomain of the host. Default:
``MRMAP_PRODUCTION``. Set it to ``False`` when a subdomain of the deployment is
served without TLS by somebody else -- with this flag on, the browser refuses
plain http to *those* hosts too, for as long as the ``max-age`` above lasts, and
no page of the deployment can undo that.

``DJANGO_SECURE_HSTS_PRELOAD``
******************************

Adds ``preload`` to the HSTS header. Default ``False``, because it is a promise to
a third party rather than a deployment setting: only set it when the host is
actually submitted to the browser preload list, whose removal is a deliberate and
slow process.

``DJANGO_SECURE_CONTENT_TYPE_NOSNIFF``
**************************************

Answers ``X-Content-Type-Options: nosniff``, so a browser never guesses the type
of a response and executes an uploaded file as script. Default ``True`` in both
deployment modes -- there is no deployment for which sniffing is wanted, which is
why it is not gated on ``MRMAP_PRODUCTION``.

``DJANGO_SECURE_REFERRER_POLICY``
*********************************

The value of ``Referrer-Policy``. Default ``same-origin``: only a same-origin
request is told which page referred it. Any `django value
<https://docs.djangoproject.com/en/5.2/ref/clickjacking/#setting-a-referrer-policy>`__
is accepted verbatim; a deployment which must hand the referring address to a
third-party map or statistics host names e.g. ``strict-origin-when-cross-origin``
here, and gives up the fact that a cross-origin collector cannot see the path of
the page it was called from.

``DJANGO_X_FRAME_OPTIONS``
**************************

The value of ``X-Frame-Options``, which the settings answer together with the
``frame-ancestors`` directive of the policy below. Default ``DENY`` -- no page may
frame this application, not even a page of the same origin. The frontend edge of
``docker/nginx/mrmap.conf`` answers the same value for the documents it serves
itself, so the SPA shell and the backend never disagree about framing. A
deployment which embeds its own viewer in an iframe of the same origin sets
``SAMEORIGIN`` **and** ``DJANGO_CONTENT_SECURITY_POLICY`` with
``frame-ancestors 'self'`` -- the browser enforces the stricter of the two, so
only changing one of them changes nothing.

``DJANGO_COOKIE_SECURE``
************************

Whether the session and the CSRF cookie are stored and sent over TLS only.
Default: ``MRMAP_PRODUCTION`` -- the shipped deployment runs behind TLS. Both
cookies always move together: a session kept over plain http without its CSRF
partner, or the other way round, is not a working arrangement. An http-only
deployment **must** set ``False``, or the browser refuses to store the session and
no login ever sticks; a https deployment which is not flagged production can set
``True`` to get the flag anyway. See
``docs/source/administration/authentication.md`` for the rest of the cookie
contract of the browser session.

``DJANGO_CORS_ALLOWED_ORIGINS``
*******************************

The origins which may call the API from another origin with the browser of a
logged-in user. A ``;``/``,` separated list of full origins including the scheme,
e.g. ``https://viewer.example.org``; the value means exactly what it says and
applies in both deployment modes. There is **no** wildcard default any more: the
shipped topology is same-origin -- the nginx of ``docker/nginx/mrmap.conf`` serves
the SPA and proxies ``/api``, ``/csw`` and ``/ws`` on the very host and port the
SPA was loaded from -- so no cross-origin consumer exists to serve, while the
previous default of every origin let any website read the API as the logged-in
user of any browser which visited it (an ``Authorization`` header needs no
cookies, so the credentialed flag was never the guard). A deployment which leaves
this unset logs ``no CORS origins are allowed`` at boot. Outside production the
vite origins of the development frontend (``http://localhost:5173``,
``http://127.0.0.1:5173``) are added to whatever is named here and may send
credentials, because that frontend authenticates with the session of this backend.

``DJANGO_CSRF_TRUSTED_ORIGINS``
*******************************

The origins whose same-origin ``POST`` may carry this site's CSRF token: a
``;``/``,` separated list of full origins including the scheme, and every scheme
named is honoured, so a deployment which serves plain https spells out exactly
that. This used to be derived from the host allow-list -- every
``DJANGO_ALLOWED_HOSTS`` entry contributed ``http://`` **and** ``https://`` of
itself, which turned an internal host name meant for a machine into an origin a
browser could be lured to. Now the variable is the only source in production, and
an unset value means django's own same-origin check and nothing else, which is
what the same-origin topology needs. Outside production the two vite origins join
automatically. Give up nothing by naming them: an origin which is not listed here
cannot make a state-changing request of a logged-in browser, it is answered
``403 Forbidden`` by the CSRF middleware.

``DJANGO_CONTENT_SECURITY_POLICY``
**********************************

The complete ``Content-Security-Policy`` the backend answers on **every** one of
its responses, the error pages included: the header is added by
``MrMap/middleware.py`` below ``SecurityMiddleware``, so the ``301`` of the SSL
redirect and the ``400`` of the host validation carry it too. Unlike the block
above it is answered in both deployment modes, because it describes the sources of
*this application* rather than a production decision, and a policy first exercised
in production is a policy whose breakage is discovered in production.

The default is the source list of the shipped frontend -- scripts of this origin
plus the two CDNs ``frontend/index.html`` and the built bundle load from
(``unpkg.com``, ``cdn.jsdelivr.net``), styles of those hosts and of the Google
Fonts CDN with ``'unsafe-inline'`` (the mechanism MUI, leaflet and monaco position
map overlays and editor decorations with; inline *style* cannot read a token and
cannot reach the network, scripts stay without the allowance), images of this
origin, of the OSM tile hosts and of ``blob:``/``data:`` for the previews the SPA
builds from bytes it fetched through ``/mrmap-proxy``, ``object-src 'none'``,
``base-uri 'self'``, ``form-action 'self'``, ``frame-ancestors 'none'``, and under
``MRMAP_PRODUCTION`` ``upgrade-insecure-requests``.

The variable **replaces** the whole policy; it does not append to it. That is not
a limitation but the reason to name the complete list: a browser enforces the
*intersection* of every ``Content-Security-Policy`` of a response, so a deployment
which adds a second header at its own edge gets the stricter of the two and no
error message. An empty value turns the header off for the backend's answers -- the
hatch for a deployment which protects its documents at the edge; the frontend
container answers its own copy for the SPA shell either way. An operator who
embeds the viewer in an iframe of another host, loads the SPA from a second origin
or hosts a tile server sets this variable; after the change, one look at the
browser console of a page of the deployment is the whole verification, because a
source the policy does not know is refused by the browser and named there.

``DJANGO_DEBUG_TOOLBAR_INTERNAL_IPS``
*************************************

The client addresses which may see the django debug toolbar when it is installed
at all. A ``;``/``,` separated list; default ``127.0.0.1;::1``. The toolbar answers
SQL, settings, request bodies and the environment of the request, so the callback
which used to answer ``True`` for everyone showed all of that to whoever reached
the deployment first. Two gates apply instead, and both have to pass: the client
address has to be listed here, and ``MRMAP_PRODUCTION`` has to be off --
``DJANGO_DEBUG=1`` alone does not make a deployment a development one. A developer
behind a proxy which rewrites the client address, or a remote development machine,
names its addresses here; nothing to gain in production, where the variable is not
read at all because the toolbar is not installed.

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


``REDIS_PASSWORD``
******************

The password of the shared redis instance (#1473). The ``redis`` service of
``docker-compose.yml`` starts with ``--requirepass`` from this value and
authenticates its own healthcheck with it, so an instance of the shipped stack
never answers an unauthenticated client; the ``:?`` of the compose file makes an
unset value refuse ``docker compose up`` the way ``DB_PASSWORD`` does.

Every client of the project reads the same variable, so there is no second place
to keep it in sync: the celery broker, the celery result backend and the Django
cache assemble their URLs from ``REDIS_HOST``/``REDIS_PORT`` and this password
(``MrMap/settings.py``), the channels layer of the notification bus passes it as
the ``password`` of its host entry, the flower UI hands it to ``celery
--broker``, and ``system/worker_healthcheck.py`` -- which must reach the broker
without importing the settings -- builds the same URL itself. The Python clients
percent-encode the value when they assemble their URL, so a credential with
characters reserved in a URL needs no encoded spelling anywhere; the flower UI of
``docker-compose.yml`` is the one client which hands the value to celery on a
command line, so keep the credential free of ``@``, ``:``, ``/`` and ``#``.

An **empty** value keeps its old meaning of "no authentication", which is what
makes the refusal above a compose-file decision and not an application one: a
development stack, a test container or any deployment which runs the image
outside compose and keeps its broker unreachable from other workloads still runs
without a password. Set a real value for anything else: one instance is the
broker, the result backend and the cache of the whole fleet, so whoever can
reach its port unauthenticated can enqueue work the workers execute as the
application, read task results, or flush the queue (#1618 is the contract that
queued work survives, and an open port is how it stops being true).


``REDIS_MAXMEMORY``
*******************

The memory ceiling of the redis instance, passed to ``redis-server`` as
``--maxmemory`` by the ``redis`` service of ``docker-compose.yml``. Defaults to
``768mb`` when unset.

One instance is the celery broker, the celery result backend and the Django
cache, and redis cannot bound a single one of those - the ceiling covers the
whole instance, and ``maxmemory-policy volatile-lru``
(``docker/redis/redis.conf``) decides what gives way: only keys which already
carry an expiry may be evicted, so cache entries and celery result keys give
way while the broker's queue lists cannot. Raise the value when the deployment
measures evictions of result keys under normal load (``INFO stats``:
``evicted_keys``); ``0`` removes the ceiling and lets redis be OOM-killed
together with the broker, which is the failure this variable exists to avoid.
See ``docs/source/development/runtime-memory-baselines.rst`` for the measured
Redis footprint and what a deployment of a different size should set.


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

``MRMAP_HARVEST_TEMP_FILE_RETENTION_DAYS``
******************************************

Used to configure how many days the metadata records a harvesting run stored below ``<MEDIA_ROOT>/temporary_md_metadata_file/`` stay after the run reached a terminal phase, before the periodic cleanup of ``registry.tasks.harvest`` takes the rows and their files back (#1237). The default is 0, which takes them with the run as soon as it ended. Every day above 0 is the window in which an administrator can still reschedule the import of a stored record of a run which completed from the admin and find the document there; the hourly sweep ``registry.tasks.harvest.sweep_ended_harvest_temp_files`` names the run again once its window passed (#1295). Unlike the other retention knobs of a media directory, 0 does not mean "keep them until an operator removes them" here: an unbounded window over this pile is exactly the 849k files and 24.4 GB of ended runs the issue reports, so 0 is the minimum of the window and not its absence. This is not ``MRMAP_HARVEST_TEMP_FILE_CLEANUP_RETENTION_DAYS``, which only says how long a run must have been over before ``manage.py cleanup_temporary_harvest_files`` names it without being asked to.

``MRMAP_UPDATE_JOB_STALE_HORIZON_HOURS``
****************************************

Used to configure how many hours an unfinished service-update job may stand in a not-yet-decided state - waiting for processing, updating or resumed - before the hourly sweep ``registry.tasks.update.sweep_stale_update_jobs`` fails it and tells the incident channel about the service (#1460). The default is 24. The guards of #1453 redeliver a lost message; this horizon answers the delivery which is gone for good - a broker recreated with the database kept, a purge, a discard - or a run whose retries died without the job ever deciding, because the constraint of one unfinished job per service would otherwise block that service's updates silently, forever. No legitimate update run takes so long, which is what makes the horizon the line that protects a job which still works; a job a worker takes at this very moment is additionally covered by the same row lock the runners hold. A mapping which waits for a human review and a run which decided its outcome while only its metadata step is open are never swept. A value below 1 is raised to 1: a busy queue is the queue watchdog's verdict of #1320, not this sweep's work.

``CELERY_WORKER_CONCURRENCY``
*****************************

Used to configure how many slots a celery worker process runs with. docker-compose.yml passes it to ``celery-worker``; unset or empty, the compose file defaults the worker to 4 slots (#1454 - celery's own default of one slot per CPU core counts the host's cores, not the container's share, and that mismatch was the OOM path behind stuck jobs), and ``auto`` sizes the prefork pool by the cgroup quota of the container. It is the knob for a bigger worker, so that changing worker concurrency never makes a deployment override the worker command and thereby restate - and freeze - the queue list of the release the override was written for; see :ref:`celery-queues` (#1040). What the slots imply for redelivery (one prefetched message per slot) and for long attempts (the global task time limits and the one per-task budget) is documented with the worker configuration in :ref:`celery-queues`.

``CELERY_WORKER_MAX_TASKS_PER_CHILD``
*************************************

Used to configure how many tasks one prefork child of a worker runs before the pool replaces it. docker-compose.yml passes it to ``celery-worker`` and the release defaults it to **1000**; empty means exactly that 1000. There is no value of this variable which means "never": the celery worker command reads the same variable from the environment itself (``--max-tasks-per-child``) and hands it to the prefork pool as it stands, and the pool refuses 0 ("maxtasksperchild must be a positive int or None"), so a deployment which sets 0 gets a worker which does not start rather than one which never recycles. ``MrMap/settings.py`` therefore rejects a value below 1 while the settings load, naming the knob, and 1 is the smallest recycling the variable can ask for. Recycling is what keeps a slot which parsed and imported a few thousand documents from carrying that work's memory into its next thousand. Before #1615 this knob was spelled ``CELERY_MAX_TASKS_PER_CHILD`` in ``MrMap/settings.py``, a name celery 5.7 does not read, so the fleet never replaced a child whatever the deployment asked for. What the number costs in worker start-ups, and how the value was chosen, is measured in :ref:`celery-queues`.

``CELERY_WORKER_MAX_MEMORY_PER_CHILD``
**************************************

Used to configure the peak memory of one prefork child in kB at which the pool replaces it. The release ships it **off** - docker-compose.yml passes an empty value and no bound applies - because of what celery measures: the quantity is ``getrusage().ru_maxrss``, the highest resident set the child ever reached, shared pages included, a fresh child of this project already peaks near 170 MB of that, and the same import path plateaus at 211 MB after 2400 documents (:ref:`celery-queues` has the curve). A bound below the measured peak of the deployment's own biggest import therefore bounds nothing - it replaces the child after every task. The check also runs only after a completed task, which makes it no OOM guard: an attempt which allocates past its container never meets the bound. A deployment which has watched its children names the kB it wants; like the knob above it has to be an integer of at least 1, and anything else stops the deployment while the settings load instead of being quietly ignored.

``CELERY_WORKER_REVOKES_MAX``
*****************************

Used to configure how many revoked task ids a worker keeps in memory. celery reads this variable from the *environment* of the worker (``celery/worker/state.py``), not from the application configuration, so docker-compose.yml hands it to ``celery-worker`` directly; the release defaults it to 2000000 against celery's own 50000, because the abort of a big catalogue revokes far more ids than that - ``registry/models/harvest.py`` names over 600000 queued ids for the BKG catalogue - and a revocation the window forgot is a message which runs again. A spelling of this name in ``MrMap/settings.py`` configures nothing, which is what #1615 found and removed.


The web tier
############

The HTTP of the ``backend`` container is served by ``gunicorn`` with ``gthread``
workers and the WSGI application; its websockets by a second, small ``gunicorn``
with ASGI workers on port 8002, which the edge of the frontend forwards ``/ws``
to. The split is #1032. The numbers that shape the two servers resolve in
``backend/.bash_scripts/process_defaults.sh``, which both startup scripts
source: docker-compose.yml passes every ``GUNICORN_*`` knob through untouched,
so the shape a container boots with is answered by one file, whether the
container came from compose, from ``docker run`` or from a test.
``MRMAP_LOW_MEMORY`` selects the low-memory shape of #1617 and
``GUNICORN_PRELOAD`` opts the HTTP workers into forking one pre-imported
application; the measured tradeoffs of both are in
:ref:`http-process-profiles`. Every view of MrMap is sync, so under an ASGI worker the
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

The burst above is the unwarmed shape of the endpoint. ``/api/schema`` now keeps the
document it built per worker, so concurrent requests for the same language are one
build plus cache hits for the rest (#1336); what the table measures is the cost of the
one build that still has to happen.

The cheap peer is a request to an unrouted url of the same server - it walks the
whole middleware chain and answers 404 in 5 ms while the server is idle - asked
ten times while the burst is in flight. It is the number the issue is about: an
endpoint which does no work of its own must not pay for what its neighbours do.
The ``gthread`` row with four threads is the shipped command line of
``backend/.bash_scripts/startup.sh``, measured twice: once as the bare gunicorn
invocation and once by starting that script itself.

``GUNICORN_WORKERS``
********************

How many HTTP worker *processes* the backend runs; docker-compose.yml passes
it to ``backend`` and the default of 4 resolves in
``backend/.bash_scripts/process_defaults.sh``. CPU bound views parallelize per process and
not per thread, because the interpreter runs one of them at a time - so a
deployment whose API traffic is CPU bound gets its lanes from this number, and
the honest way to size it is the number of cores it gives to the web tier. The
database pays for it: each worker holds its own connection pool (see
``DATABASES`` of the settings), so this is also the multiplier of the connections
a backend may hold at once.

``GUNICORN_THREADS``
********************

How many requests one HTTP worker answers at a time; docker-compose.yml passes
it to ``backend`` and the default of 4 resolves in
``backend/.bash_scripts/process_defaults.sh``. This is the depth of the queue in front of one
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

How many ASGI worker processes serve the websockets on port 8002;
docker-compose.yml passes it to ``backend`` and the default of 1 resolves in
``backend/.bash_scripts/process_defaults.sh``. Open websockets are idle and I/O
bound, so one event loop carries the connections of a whole deployment; the
variable is there for a deployment with an unusual number of simultaneous
connections.

``MRMAP_LOW_MEMORY``
********************

Selects the low-memory shape of the web tier (#1617, epic #1612): with
``1``/``true``/``yes``/``on`` the HTTP server boots with **1 worker and 2
threads** instead of 4 and 4, which is what a container that must share its
host with an editor, an agent or another stack pays for with web-tier
throughput. The mode changes nothing else - not the websocket server, not
``DJANGO_DEBUG``, not any queue depth an explicit ``GUNICORN_WORKERS`` or
``GUNICORN_THREADS`` pins - and an unset value keeps the shipped production
shape, so selecting the mode can never reduce production throughput by
accident. Since #1621 the mode also selects the bounds of the database pool
below, because every HTTP worker carries its own pool; it still changes
nothing else. Measured cost and saving: :ref:`http-process-profiles`.

``GUNICORN_PRELOAD``
********************

Off by default. With ``1``/``true``/``yes``/``on`` the HTTP gunicorn imports
the WSGI application once in its master and the workers fork it, so the pages
of the imports are shared copy-on-write and a failed import kills the boot
instead of surfacing per worker. It applies to the HTTP server only: the
websocket server runs one worker (there is nothing to share) and #1617's
acceptance names stuck websockets as the failure mode a preload must not
introduce. The fork-safety audit behind the flag - and the measured memory it
does and does not buy - is in :ref:`http-process-profiles`.

``MIN_BACKEND_RESERVED_CONNECTIONS`` and ``MAX_BACKEND_RESERVED_CONNECTIONS``
*****************************************************************************

The bounds of the psycopg connection pool which every non-Celery process
opens against PostgreSQL - the ``min_size`` and ``max_size`` of the ``pool``
entry under ``DATABASES`` in the settings (#1621). ``min_size`` is what one
process holds at rest; ``max_size`` is what one process may open, so the
deployment's reservation is the pair multiplied by the number of pooled
processes, of which the HTTP workers are the ``GUNICORN_WORKERS`` multiplier
named above. Celery's processes are deliberately outside the pool: an
unfinished transaction once survived on a pooled connection and poisoned the
next request, and the worker branch of the settings has kept the pool off
ever since.

An unset value lands on the default of the selected mode: **4 reserved and
20 open** per process in the shipped shape, **1 and 4** with
``MRMAP_LOW_MEMORY``, mirroring the smaller shape so the rest reservation
follows the process it belongs to. An explicit value always wins over the
mode, and nonsense - not a number, below 1, or a minimum above the maximum -
fails while the settings load rather than being decoded differently
elsewhere. In a Compose deployment these are set in
``docker/backend/.mrmap.env``, the ``env_file`` of the backend service, and
deliberately are not passed through ``docker-compose.yml``: an
``environment`` entry with the empty fallback of a pass-through would shadow
a value written into that file, which is the #1615 failure this knob must
not have. What the bounds are worth in idle and loaded connections and in
PostgreSQL's own per-connection memory: :ref:`db-pool-memory`.
