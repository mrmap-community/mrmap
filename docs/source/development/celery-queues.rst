.. _celery-queues:

=============
Celery queues
=============

MrMap routes the work of its celery tasks onto named queues. The queue names live in exactly one place, ``backend/MrMap/celery_queues.py``; the ``Queue`` declarations of ``MrMap/settings.py`` (``CELERY_TASK_QUEUES``), the ``queue=`` of the task declarations and the broker introspection of the harvest all read their names from there. This page describes which queue carries what, what a worker consumes and how to change worker size without touching any of it.

The queues
##########

.. list-table::
   :header-rows: 1
   :widths: 20 80

   * - Queue
     - Carries
   * - ``default``
     - Everything which is neither bulk work nor bound to a protocol step; every task without a ``queue=`` of its own is published here.
   * - ``download``
     - The download backlog of a harvest: one message per catalogue round trip. Floodable, which is why it has a queue of its own.
   * - ``db-routines``
     - Database work which has to answer quickly: the control messages which build and rebuild a harvest's import chord, the callbacks which end harvests and background processes, and the beat-scheduled periodic tasks. A catalogue must not be able to fill this queue (#970).
   * - ``harvest-import``
     - The import backlog of a harvest: one message per stored metadata file or per chunk of them. This is the queue a real catalogue fills for hours, which is exactly what the messages of ``db-routines`` must not wait behind (#970).
   * - ``monitoring``
     - Service monitoring round trips.
   * - ``update``
     - The update jobs of registered services.

What a worker consumes
######################

The celery command of the ``celery-worker`` service in ``docker-compose.yml`` passes **no** ``-Q`` option. A worker without ``-Q`` consumes every queue the application declares, so the deployment has exactly one source of truth for the queue list: a release which adds a queue (``harvest-import`` did, in #970) is consumed by a restarted deployment without any override having to restate the list.

This matters because a queue which no worker consumes is not an error anywhere in the chain: the publishing task succeeds, the broker stores the message and nothing ever reads it. A harvest which stalls that way gives no other trace than a celery ``chord_unlock`` timeout more than an hour later (#1038). The drift this page prevents: a deployment that overrode the worker command to change its concurrency carried the queue list of its old release in that override, and silently stopped consuming the queue the new release routed its import tasks to (#1040).

Worker slots
############

The number of slots a worker runs with is ``CELERY_WORKER_CONCURRENCY`` in the ``.env`` of the deployment (see :ref:`development-environment`), which ``docker-compose.yml`` passes to ``celery-worker``. Unset or empty, the compose file of the release defaults the worker to **4 slots** (#1454); ``auto`` sizes the prefork pool by the cgroup quota of the container. The default exists because celery's own default of one slot per CPU core is taken from the *host*: a deployment which gives the worker container 2 GiB and no CPU cap on a many-core machine inherited a prefork pool sized for the machine, not for the container - the OOM path which kills slots mid-task. It is also the knob for a bigger worker, and it exists precisely so that growing a worker never requires overriding the worker command - and thereby freezing the queue list of the release the override was written for.

A deployment which deliberately splits its workers - one worker per group of queues, each started with its own ``-Q`` - remains possible; it just has to know what it is doing, which the start-up check below describes.

Prefetch: one un-acked message per slot
#######################################

``CELERY_WORKER_PREFETCH_MULTIPLIER`` is ``1`` (``MrMap/settings.py``). The long work of this fleet - harvesting, registration and the WMS update jobs - runs with ``acks_late``: the broker keeps the message un-acked *while the task works*, so a crash or a roll can hand the message to another slot instead of losing it. With celery's default prefetch of four per slot, a worker also reserves up to three further, never-started messages per slot; on every roll or restart the broker requeues those reservations and their side-effecting tasks run again from the start, for work no slot had even begun. One message per slot removes that class of redelivery: a slot holds nothing it does not run. The broker round trip it adds per task is the deliberate price. This is what Celery's own configuration documentation prescribes for tasks with side effects.

Task time limits
################

Every task attempt is bounded by ``CELERY_TASK_SOFT_TIME_LIMIT`` (2700 s) and ``CELERY_TASK_TIME_LIMIT`` (3000 s) of ``MrMap/settings.py`` (#1454). The bounds are built from the longest request the deployment runs on purpose: one harvesting ``GetRecords`` is capped at 900 s (``HARVESTING_REQUEST_TIMEOUT_MAX_SECONDS``, ``registry/settings.py``), and the soft limit at three times that ceiling still leaves a healthy page room for its parse and persist. What the bounds are for is the attempt which never ends on its own - the CPU-bound parse, import and mapping recursion of a pathological document, which without a limit pins a worker slot forever. The soft limit raises ``SoftTimeLimitExceeded`` inside the running task, so its cleanup and its base class's failure paths still write decided terminal state; the hard limit SIGKILLs the pool slot five minutes later and the prefork pool replaces it, which is also the only bound on a request whose own socket timeout failed to fire.

The one task which declared a budget of its own - the external ETF conformity check, which waited synchronously on a third-party validator whose run takes hours by nature - was deleted with #1458 (#1454 had given it that budget, deliberately below the abandon grace of the attempt samples of :ref:`celery-capacity-telemetry`); every attempt of the fleet now runs under the global bounds. A hard-killed attempt is visible in the telemetry the way it is: an attempt row which never gets its end and is flagged ``abandoned`` by the nightly sweep - the fallout the queue capacity of #1326 reports as uncertain. Time limits are enforced by the prefork pool, which is what the stock ``celery-worker`` runs; ``backend/tests/django/test_celery_worker_config.py`` pins the numbers and the per-task resolution.

The start-up check
##################

Because a narrowed worker is allowed but a drifted one is a silent failure, every worker checks itself at start-up. The ``celeryd_after_setup`` hook ``MrMap.celery.check_consumed_queues`` compares the queues the application declares with the queues this worker consumes and logs an ``ERROR`` naming each declared queue the worker does not consume, together with the tasks bound to it::

    ERROR worker celery@worker-1 does not consume 1 of the queues the app declares: 'harvest-import' carries: registry.tasks.harvest.call_md_metadata_file_to_db, registry.tasks.harvest.call_md_metadata_files_to_db. Messages published to these queues are never read; this is right only if another worker consumes them (#1040).

For a split fleet this line is the confirmation that the split is as intended; for a single worker - the stock case - it is the misconfiguration which would otherwise cost hours of stranded work. A worker which consumes all declared queues, the default, logs nothing.
