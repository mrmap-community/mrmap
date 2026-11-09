.. _celery-result-backend:

=====================
Celery result backend
=====================

MrMap runs its long work in Celery chords: the metadata collection of a registration and the import backlog of a harvest are chord headers whose callback ends the background process when the last member returned. A chord needs somewhere to keep its members' results and its bookkeeping while it is collecting; what a human sees of the progress belongs to the domain models and to ``BackgroundProcess``, not to that store. Since #1178 that store is **Celery's native Redis result backend** (``celery.backends.redis:RedisBackend``); before that it was a wrapper over the cache backend of the ``django-celery-results`` package, which read and wrote results through the Django cache. The wrapper is gone and nothing of the result path imports that package any more; the package itself is still installed while its remaining models are (the ``TaskResult`` row of the legacy registration resource), and its removal is a later step of #1175.

What lives where
################

The deployment has one Redis. Its tables (Celery says *db*) are assigned exactly like the comment block of ``backend/MrMap/settings.py`` has always documented them:

.. list-table::
   :header-rows: 1
   :widths: 25 75

   * - Redis table
     - Carries
   * - ``0``
     - The Celery broker's queues and the native result backend: task results under ``celery-task-meta-*``, group and chord bookkeeping under ``celery-taskset-meta-*``. They share the table with the broker's own keys; the prefixes do not collide.
   * - ``1``
     - The Django application cache (``django-redis``, zlib-compressed). Celery results have no part in it any more.

The URL is assembled from ``REDIS_HOST``/``REDIS_PORT`` like the broker URL it derives from; no separate credentials exist for it and none are introduced.

Retry budget
############

A member of a chord stores its result *after* its body - a harvest file which took minutes to import - has committed. Losing that write must not run the body again and must not end the harvest as failed (#816). The native backend answers this on its own, which is why the wrapper was removable:

* Redis connection and time-out errors are the backend's own retriable set; anything else - a programming error such as an unserialisable value - is raised at once instead of being retried repeatedly.
* A write first runs through the backend's bounded connection-retry loop; the outer loop then applies ``CELERY_RESULT_BACKEND_ALWAYS_RETRY`` with ``CELERY_RESULT_BACKEND_MAX_RETRIES`` retries and exponential backoff. The budget is finite; when it runs out the worker logs a ``BackendStoreError`` and the task's *body* is still reported as it really ran.
* Reads of results share the same budget.

``tests/django/test_celery_backend.py`` keeps exactly this contract against the Redis of the stack, plus the chord bookkeeping: a redelivered member counts once, the callback is dispatched exactly once, and a failing member fails the chord instead of publishing the callback.

Expiry
######

``CELERY_RESULT_EXPIRES`` is one day (Celery's default, spelled out in the settings). That covers a chord which keeps working, because every member returning refreshes the expiry of the group's bookkeeping keys; what expires are the entries of chords that died - a chord whose queue no worker consumes (#1038) leaves keys which disappear on their own instead of filling Redis. A chord whose members stay uncollected for longer than one day cannot be completed by any backend of this project; the harvest's import backlog is watched instead (:ref:`celery-queues`, #1038), and it resumes through ``manage.py resume_harvesting_job``.

Cutover from the cache-backed result backend
############################################

The old entries are not readable by the new backend and the new entries are not readable by the old one: results moved from zlib-compressed values under the Django cache's key prefix in table 1 to plain ``celery-task-meta-*`` keys in table 0, and the chord bookkeeping of a run in progress sits in one or the other. A chord which was published under the old backend therefore does not complete on the new one - the switch has to treat in-flight work explicitly:

1. **Stop the producers of new chord publications.** Stop ``celery-beat`` and then ``celery-worker`` with the container runtime's normal signal (``docker compose stop celery-beat celery-worker``); a worker answers the tasks it is inside and finishes running task bodies.
2. **Let the queues drain.** The broker is unchanged by this switch: messages which are already queued are still consumed after the worker restarts. What must not span the switch are *running chords* - a header whose members have not all returned yet.
3. **Account for the open work.** List the harvesting jobs and background processes which still run. A harvest whose import chord did not finish before the stop resumes on the new release through ``manage.py resume_harvesting_job <pk>`` (its backlog rebuild is built for worker-loss anyway, #970); a registration whose collection chord did not finish is aborted on its ``BackgroundProcess`` and the service registered again.
4. **Recreate the Celery containers on the new release** (``backend``, ``celery-worker``, ``celery-beat``) and restart ``celery-beat`` and ``celery-worker``. From here on chords run entirely in table 0.
5. **Leave the old entries alone.** The leftover results in table 1 carry the one-day expiry they were written with and disappear by themselves. Do not flush table 1 - the application cache lives there too.

**Rollback boundary.** The same drain is the way back: once a chord was published under the new backend, the old release cannot complete it either. The old entries of table 1 need no restoration at any point - they were only ever read by the old backend's still-running runs.
