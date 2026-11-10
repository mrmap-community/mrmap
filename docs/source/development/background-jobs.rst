.. _background-jobs:

================
Background jobs
================

Long running work in MrMap is a *background process* (``registry``/``notify``: the model
``BackgroundProcess``, the celery machinery behind it and its websocket notifications). Before
#1203 every process which decided announced its own snackbar; a harvest of a thousand records which
failed at the end answered with a thousand toasts, and the "what is running right now" question had
no single answer. The deployment now has one **Background Job Center**: an activity counter in the app
bar which opens a drawer of the running, waiting, failed and recently completed processes, with
notifications constrained by rules instead of per-message.

This page documents the three contracts the center rests on, how the client behaves against them and
what an operator or developer has to know when something looks wrong.

The state contract
##################

The api answers a process by its ``status`` (``pending``, ``running``, ``completed``, ``failed``,
``aborted``). The Job Center reads three additional, derived fields on the same endpoint
(``/api/backgroundprocesses/``), so no second model or endpoint was introduced (#1207):

.. list-table::
   :header-rows: 1
   :widths: 20 80

   * - Field
     - Meaning
   * - ``state``
     - The logical state: ``queued``, ``running``, ``retrying``, ``failed``, ``completed``,
       ``aborted``. It is ``status`` with one difference: a ``running`` process whose last log line is
       an error and which will be retried answers ``retrying`` instead of ``running``.
   * - ``isRetrying``
     - Whether the process is currently in a retry - derived from the worker's own retry log, not from
       a client heuristic.
   * - ``errorSummary``
     - The first line of the most recent error log, or nothing. Enough to tell *why* in a list row;
       the full log stays on the process' own screen.

The fields are serializer methods over the process' log - the model and its migrations are unchanged.
``date_created`` and ``done_at`` are filterable (``exact``, ``gt``, ``lt``, ``range``) because the
drawer's "completed in the last 24 h" tile asks with ``doneAt_filter_lookup_gt``.

A client which talks to an older deployment will not see these fields; the Job Center maps
``status`` onto the same six states itself and only the ``retrying`` distinction degrades into
``running``.

The realtime contract
#####################

``notify`` pushes process events over the websocket the frontend already holds (see
:ref:`development-communication` for the bus itself):

* ``created`` and ``deleted`` of any process arrive on the resource-wide topic
  ``resource/BackgroundProcess``;
* ``updated`` of one process arrives **only** on its own topic ``resource/BackgroundProcess/<id>`` -
  a client which wants the progress of a process subscribes to that process (this is the same rule
  ``RealtimeListBase`` uses everywhere else);
* the consumer debounces non-immediate updates by one second, while terminal transitions (the moment
  ``done_at`` is set) are sent immediately.

The Job Center therefore subscribes to the per-id topics of the newest ``100`` active processes it
tracks. Older active processes stay visible but only refresh with a page of the api. The aggregate
counters are never pushed: the app bar pill, the drawer tiles and the counted tab labels poll the
collection endpoint every ten seconds through one shared filter set, so they stay accurate even while
more than a thousand processes churn and the client store holds only a bounded window of them.

Notification rules
##################

The bridge between the event stream and ``useNotify`` is deliberately quiet (#1205):

* **A failure is announced once per process**, as a warning, when it transitions into ``failed`` -
  not once per log line, not once per duplicate event. The client store never lets a terminal process
  move back, so a re-delivered message cannot announce the same failure twice.
* **Completions are aggregated**: processes which finish within a three second quiet window are told
  together in one success message ("3 background jobs completed"). A bulk run of fifty tasks ends in
  one toast, not fifty.
* **Hydration never announces anything.** On page load and on every reconnect the store is rebuilt
  from the api (newest active page and newest terminal page); replaying that as notifications would
  tell the user again what they may already have read, and a reconnect after a night offline would
  wake a wall of toasts.
* **Progress updates never announce.** A progress event only moves the bar.
* Deleting a process removes its row from the view; nothing is announced.

This is the whole toast budget of background work. Anything louder was the bug the epic replaced.

The client store
################

``frontend/src/components/Resource/BackgroundProcess/JobCenter/`` holds one context
(``BackgroundJobCenterProvider``, mounted by ``Layout``) with a store bounded to
``MAX_TRACKED_JOBS`` (300) processes: the drawer shows a window of the work, the full list and the
history live on the resource's own screens. When the cap is reached the oldest terminal processes are
dropped first, then the oldest active ones, and the drawer says so in its footer. The store:

* keys processes by ``String(id)`` because the list endpoint answers integers and the websocket
  answers strings;
* ignores updates of processes it does not hold (a dropped process is brought back by an api page,
  not by a stray message);
* treats the first terminal state it has ever seen as the state that stands, so out-of-order events
  cannot resurrect a decided process.

Troubleshooting
###############

.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - Symptom
     - Look at
   * - The drawer shows nothing while jobs run
     - The websocket (``realtimeIsReady`` in the client, the ``notify`` service on the server). While
       the bus is down the store falls back to polling the two api pages every twenty seconds, so
       even with a dead socket the drawer is never emptier than twenty seconds behind.
   * - The pill counters lag by a few seconds
     - By design: the counts are polled every ten seconds and not pushed.
   * - A retrying process shows "running"
     - Either the deployment's api does not answer ``state`` yet (old backend, new frontend) or no
       ``TaskResult`` row of the process' own task ids reads ``RETRY``; ``isRetrying`` is the
       overlap of ``celery_task_ids`` with the task attempts held in a retry (#1179).
   * - One process stopped updating in the drawer
     - It is older than the newest hundred active processes, or its terminal transition was already
       folded in: the store's terminal state never moves back. The api page and the reload answer.
   * - A process which failed long ago announced itself now
     - It should not: hydration is silent. If a *live* event announced it, the transition genuinely
       happened now (e.g. an abort settling after a worker loss).

Migration notes
###############

* ``notistack`` was removed with the snackbar stack it drove: ``SnackbarProvider``,
  ``SnackbarObserver``, ``ShowShortInfoBackgroundProcess``, ``BackgroundProcessAlert`` and
  ``BackgroundActivityPanel`` are gone. Everything that announces goes through react-admin's
  ``useNotify`` and the ``<Notification />`` in the layout - map transfer controls migrated in the
  same change.
* There is no "retry a process" action anywhere: no endpoint restarts a decided process, so the
  center offers only what the api supports (aborting via ``AbortBackgroundProcessButton``, which sets
  ``phase: abort``).
