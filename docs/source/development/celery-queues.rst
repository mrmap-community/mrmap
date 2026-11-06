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

The number of slots a worker runs with is ``CELERY_WORKER_CONCURRENCY`` in the ``.env`` of the deployment (see :ref:`development-environment`), which ``docker-compose.yml`` passes to ``celery-worker``. Unset, celery keeps its own default of one slot per CPU core; ``auto`` sizes the prefork pool by the cgroup quota of the container. It exists precisely so that growing a worker never requires overriding the worker command - and thereby freezing the queue list of the release the override was written for.

A deployment which deliberately splits its workers - one worker per group of queues, each started with its own ``-Q`` - remains possible; it just has to know what it is doing, which is the next section.

The start-up check
##################

Because a narrowed worker is allowed but a drifted one is a silent failure, every worker checks itself at start-up. The ``celeryd_after_setup`` hook ``MrMap.celery.check_consumed_queues`` compares the queues the application declares with the queues this worker consumes and logs an ``ERROR`` naming each declared queue the worker does not consume, together with the tasks bound to it::

    ERROR worker celery@worker-1 does not consume 1 of the queues the app declares: 'harvest-import' carries: registry.tasks.harvest.call_md_metadata_file_to_db, registry.tasks.harvest.call_md_metadata_files_to_db. Messages published to these queues are never read; this is right only if another worker consumes them (#1040).

For a split fleet this line is the confirmation that the split is as intended; for a single worker - the stock case - it is the misconfiguration which would otherwise cost hours of stranded work. A worker which consumes all declared queues, the default, logs nothing.
