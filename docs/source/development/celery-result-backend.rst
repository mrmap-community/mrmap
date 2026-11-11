.. _celery-result-backend:

=====================
Celery result backend
=====================

MrMap runs its long work in Celery chords: the metadata collection of a registration and the import backlog of a harvest are chord headers whose callback ends the background process when the last member returned. A chord needs somewhere to keep its members' results and its bookkeeping while it is collecting; what a human sees of the progress belongs to the domain models and to ``BackgroundProcess``, not to that store. Since #1178 that store is **Celery's native Redis result backend** (``celery.backends.redis:RedisBackend``); before that it was a wrapper over the cache backend of the ``django-celery-results`` package, which read and wrote results through the Django cache. The wrapper is gone and nothing of the result path imports that package any more. #1180 removed the package itself; :ref:`the last section <celery-results-removal>` is what an operator has to do about it.

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

.. _celery-results-removal:

Removal of django-celery-results (#1180)
########################################

The package outlived its purpose, not its rows. Nothing read or wrote ``TaskResult`` any more once #1177 answered a registration with its ``BackgroundProcess`` and #1179 retired the ``threads`` relation; #1180 removed the package, its installed-app entry and the last endpoint over its rows.

Required intermediate release
    This release is only reachable from one which already carries **#1178 and #1179** - a deployment whose ``django_migrations`` records ``notify.0006_remove_backgroundprocess_threads``. From an older release, upgrade and migrate there first; that release is the oldest supported baseline (#1180 answer 3). Check before upgrading:

    .. code-block:: console

        $ docker compose run --rm --no-deps backend python manage.py showmigrations notify

    ``notify [X] 0006_remove_backgroundprocess_threads`` is the marker. Without it, stop at the intermediate release first - and do not expect ``migrate`` to warn you: the nodes which once added ``status`` and the ``date_created`` index are empty here, because the databases they were written for recorded those names already, so a database which skipped them migrates "successfully" and the application then fails on a missing column.

Before migrating: back up and export
    Back the database up. This is the last moment at which the legacy tables are readable *application* data - with a model, a migration history and a supported meaning: ``django_celery_results_taskresult`` and, on a deployment which ever used chords or group results, ``django_celery_results_chordcounter`` and ``django_celery_results_groupresult``. Whatever an operator wants to keep of them is exported here, out of the backup or with a query of their own; the application offers no export command and invents no retention rule of its own. What the migration itself carries into supported data is only the task ids and the terminal outcome of each task (see below); the arguments, results, tracebacks, worker names and the two counter tables of the package exist afterwards only where an operator exported them.

What the migration does
    * The ``notify`` history is **regenerated**: ``notify.0001_initial`` creates ``BackgroundProcess`` and ``BackgroundProcessLog`` as they are today - without ``threads``, and with no dependency on the removed app - while ``0002`` up to ``0006`` stay on disk as nodes which add nothing. They stay because the chain still parents on those names and ``registry/0014``, ``registry/0020`` and ``registry/0037`` name ``0005_alter_backgroundprocess_process_type`` at their end: a node whose parent is gone fails the whole graph, so the names are kept and their contents are not.
    * ``notify.0006`` is kept as a node whose schema work is empty. Its name is load-bearing twice over: the databases which applied the real ``RemoveField`` recorded it, and ``0007_backgroundprocess_action_required_and_more`` of #1229 parents on it.
    * ``notify.0006`` carries one data step (**D03** of #1175, accepted on #1180): where a database still has the retired through table ``notify_backgroundprocess_threads``, two things are read out of it and of the legacy rows it points at, before that table goes. The task ids are unioned into ``BackgroundProcess.celery_task_ids`` - the column cancellation reads since #1179 - so association ownership outlives the relation. And every task whose legacy row records a state which *is* a result - ``SUCCESS``, ``FAILURE``, ``REVOKED`` - is appended to the logs of its process as a ``BackgroundProcessLog``, dated by the moment the backend recorded. The step is **guarded and self-skipping**: on a database which already applied the ``RemoveField`` - every database migrated by the intermediate release - the table is gone and there is nothing to read, which is the expected case and not a failure. For those databases the evidence went with #1179 itself, whose audit found no production path populating the relation, so the affected set is expected to be empty.
    * Each of those log rows begins with ``[#1180 carried over from django_celery_results_taskresult]``, so a carried outcome can be told apart from one the application logged and can be deleted on its own. It is the only place a statement about a single past task can live after this release: the results themselves went with #1178 into the Celery result backend, which is Redis and disposable.
    * No state of the *process* is ever written from a legacy row, and no log is written for a task whose row records no result: a row which never left ``PENDING`` (or ``RECEIVED``/``STARTED``/``RETRY``/``REJECTED``) stays unknown, and is written as completed, failed or aborted nowhere. A carried row therefore names one task of a process, never the state of that process.

The irreversible boundary
    After this release the legacy tables are **orphans**: no model, no migration and no endpoint of MrMap refers to them, and a fresh installation never creates them. They are deliberately **not dropped** - that removal is irreversible raw SQL and needs an explicit maintainer order which the accepted D03 policy does not contain. No cleanup release is scheduled or named here; an operator who exported what they need may drop the tables by hand at their own discretion, which is not an application-supported step.

    Two parts of the migration are irreversible on their own: the ids added to ``celery_task_ids``, and - on a database which arrived without having applied #1179 - the dropped ``notify_backgroundprocess_threads`` table.

Legacy HTTP surface retired at the same cutover
    ``GET /api/notify/task-results`` is gone with no replacement resource (#1175 decision D01, option B: an announced breaking cutover rather than a dual contract). A client follows ``/api/notify/background-processes/<pk>``, which answers the workflow status, the progress, the moment a terminal state was reached and the ``related_resource`` the work belongs to; the logs of what failed are at its nested ``background-processes/<pk>/logs``. The ``threads`` route under the same path went earlier, with the relation itself (#1179).

Rollback
    The release before this one - the #1178/#1179 release, which already has no ``threads`` relation - rolls back onto the same database: its own image still carries the package and the legacy tables it reads are untouched. Anything older needs the backup taken above, because it expects ``notify_backgroundprocess_threads`` to exist. Chords are unaffected by this particular switch; the result path stopped going through the package with #1178, and :ref:`the drain procedure above <celery-result-backend>` is about that one.
