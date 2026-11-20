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

Child recycling
###############

A prefork slot is a forked process, and the work of this fleet leaves something behind in it: the parse tree of a metadata document, the instances a mapping builds from it, the ORM objects a task keeps referenced. ``worker_max_tasks_per_child`` replaces a child after a number of tasks so that residue is not carried into the next batch of work. Before #1615 the project configured this knob under a name celery does not read, and no child was ever replaced - whatever the deployment believed it asked for. The guard which keeps the whole class of that failure out of the settings is the last section of this page.

The deployer knob is ``CELERY_WORKER_MAX_TASKS_PER_CHILD``, which ``docker-compose.yml`` hands to ``celery-worker`` (see :ref:`development-environment`); the release defaults it to **1000** - the number ``MrMap/settings.py`` had named for years, now on a name the worker actually reads. Empty is that 1000, not "never": the celery worker command reads the same variable from the environment itself (``--max-tasks-per-child``) and gives it to the prefork pool unchanged, and the pool refuses 0 with "maxtasksperchild must be a positive int or None" (measured with the celery 5.7.0 of the image, on a bare celery app as well as on this project's). A deployment which names 0 therefore gets a worker which does not start at all; ``MrMap/settings.py`` refuses a value below 1 while the settings load, naming the knob, so the refusal is explained rather than a crash loop with a library message. 1 is the smallest recycling the variable can ask for, and no value of it means "never".

What the number costs was measured on the path which does the accumulating: the real chord member ``registry.tasks.harvest.call_md_metadata_files_to_db`` - the task a harvesting run's import chord builds - over 240 stored documents, the three spike documents of the harvest test data with a fresh file identifier on every copy so that each one imports as a new record, in chunks of ten records. One worker, one slot unless stated::

    =====  =====  ======  =========  =============
         K  slots  wall s  pids seen  peak child kB
    =====  =====  ======  =========  =============
         1      1  407.22        510        178348
         5      1   80.99         54        183116
        25      1   52.01         11        188048
      1000      1   46.10          1        206880
      1000      4   12.96          4        187764
    =====  =====  ======  =========  =============

The gap between the first row and the fourth - 407 s against 46 s for the same 240 documents - is the pool's churn, not the import: those documents take 46 s when one child keeps them all. Fitted across the four single-slot rows, one replacement costs about 0.6 s, so a child which recycles after 1000 tasks pays it six times in a million records. "pids seen" counts every pid the sampler saw under that worker's master; the 510 of the first row is the pool replacing the slot again and again, not 24 tasks.

The same sampler over 240 tasks of ten records in one child, 2400 documents and 478 s, without ever reaching the bound, answers what a child actually keeps: it starts at 172 MB of resident set, sits at 211 MB from its first minute, and the curve is flat from there - its slope over the second half of the run measures 0 kB/s. The 40 MB are the warm-up of the interpreter, the ORM caches and the geo stack, not an accumulation which grows with the work. This is the measurement behind two decisions of the release: the 1000 of the default, and the memory bound below.

That bound, ``CELERY_WORKER_MAX_MEMORY_PER_CHILD``, ships **off**, and what it measures is the reason. Celery compares ``getrusage(RUSAGE_SELF).ru_maxrss`` - the highest resident set the child ever reached, shared pages included (``billiard/compat.py``) - against the kB the deployment names, and a fresh child of this project is already near 170 MB of that quantity. A bound below the peak of the deployment's own biggest import (211 MB on the path above) does not bound anything: it replaces the child after every task and pays the 0.6 s each time. The check also runs only *after a completed task* (``billiard/pool.py``), so the document which allocates past its container never meets the bound before it dies - it is no OOM guard, and the memory of the fleet is ``CELERY_WORKER_CONCURRENCY`` times whatever a child holds, which is the slot question of this page and not this one. A deployment which has watched its own children and wants the replacement anyway names the kB it wants.

The revocation window
#####################

``CELERY_WORKER_REVOKES_MAX`` is not a setting of ``MrMap/settings.py`` and can not be one: celery builds the window in ``celery/worker/state.py`` from the *environment* of the worker process (``REVOKES_MAX = _int_env('CELERY_WORKER_REVOKES_MAX', 50000)``), before any application configuration is read. The name this file carried for it measured inert for the same reason the recycling knob did (#1615) - and its absence is not harmless, because the abort of a big catalogue revokes far past celery's 50000: ``registry/models/harvest.py`` names over 600000 queued ids for the BKG catalogue, and a revocation the window already forgot is a message which runs again. ``docker-compose.yml`` therefore hands the variable to ``celery-worker`` with **2000000**, the old intent of the inert setting, and ``backend/tests/django/test_celery_worker_config.py`` pins both halves of what a unit test can see: that celery really reads the environment, and that the project carries no second, inert copy of the name. Which value the variable reaches the service with is the half a compose question, not a test question: ``docker compose config`` renders it.

The guard against the whole class
#################################

Both findings of #1615 are one failure: a ``CELERY_*`` name in ``MrMap/settings.py`` for which celery has no reader is configured, answered by ``celery -A MrMap inspect conf`` and ignored by the worker - a number an operator trusts. The namespace does not warn about it; it writes the value onto a key nobody reads. ``NoInertCelerySettingTests`` therefore asks every ``CELERY_`` attribute of the project against ``celery.app.defaults.DEFAULTS`` and names the near misses when one is not on that table, so a renamed knob can not go inert a second time. It is the guard for the class and not for the last spelling, and a deployment's own settings override is subject to the same rule.

The start-up check
##################

Because a narrowed worker is allowed but a drifted one is a silent failure, every worker checks itself at start-up. The ``celeryd_after_setup`` hook ``MrMap.celery.check_consumed_queues`` compares the queues the application declares with the queues this worker consumes and logs an ``ERROR`` naming each declared queue the worker does not consume, together with the tasks bound to it::

    ERROR worker celery@worker-1 does not consume 1 of the queues the app declares: 'harvest-import' carries: registry.tasks.harvest.call_md_metadata_file_to_db, registry.tasks.harvest.call_md_metadata_files_to_db. Messages published to these queues are never read; this is right only if another worker consumes them (#1040).

For a split fleet this line is the confirmation that the split is as intended; for a single worker - the stock case - it is the misconfiguration which would otherwise cost hours of stranded work. A worker which consumes all declared queues, the default, logs nothing.
