.. _background-notifications:

========================
Background notifications
========================

Harvestings, service updates, registrations and monitoring runs are background work: they outlive the request which started them and many of them run at once. This page describes the three things the project must not lose track of while doing that - **which feedback the user is promised and where** (the notification rules), **what exactly travels over the websocket** (the integration contract, ``backend/notify/`` to ``frontend/src/jsonapi/components/Realtime/``), and **how the legacy notification behavior was retired** and what an operator checks when the activity goes quiet. The approved design is epic #1203; the acceptance tests behind the contract are ``backend/tests/django/notify/test_realtime_delivery.py`` and the frontend specs named below (issue #1209).

The one-line rule: **a direct action of the user is answered with a react-admin notification; background work is never toasted per task or per step.** Background work reports over the realtime bus and is *read* from surfaces which aggregate it - the AppBar activity panel, the background process list and the open run screen.

The notification rules
######################

Direct UI feedback
    Every mutation the user started (a save, a button, a dialog) reports through react-admin's ``useNotify()`` and is rendered by react-admin's own ``<Notification />`` host. That is the standard for direct feedback and stays it; there is no second toast machinery in the frontend.

Background operations
    A background process announces itself on *every* step - a ``HarvestingJob`` writes its own row on each phase of its workflow, a ``BackgroundProcess`` reports per task. None of these announcements produces a toast. The frontend subscribes to what it *displays* (see the contract below) and merges the pushed records into the screens it already renders:

    * the **AppBar activity panel** (``components/Resource/BackgroundProcess/BackgroundActivityPanel.tsx``) shows the ten most recent processes of the user with status, phase, progress and a details link, plus a badge while anything runs. Its page size of ten is the bound on a flood: whatever the deployment announces at once, this surface never renders more.
    * the **BackgroundProcess list** answers the full history, including failures - which is what keeps an error discoverable after the panel's newest-ten window, after a reload and after a snackbar would have vanished.
    * an **open run screen** (``RealtimeShowContextProvider``) and an open list (``RealtimeListBase``) apply the pushed records directly; a create or delete makes the list refetch, because only the server's ordering decides whether the new row belongs to the page.

No toast per update, and no state lost
    The transport is allowed to *drop* intermediate announcements (the next one carries the complete record, see the ``immediate`` flag below), but a user must not lose a result by looking away: the panel, the list and the run screen all read the stored state, so a failure stays visible after a reload - nothing important lives only in a transient toast.

Aggregate counts of a burst
    A thousand queued processes are one panel badge and a bounded list, not a thousand notifications. If a deployment wants completion notices per operation again, that is the aggregate bridge of #1205's design - a summary over the stored state - not a per-task toast reintroduced.

Who announces what
    The publishers are the ``post_save``/``post_delete`` receivers in ``backend/notify/signals.py``:

    .. list-table::
       :header-rows: 1
       :widths: 25 75

       * - Announced record
         - Publisher
       * - ``BackgroundProcess``
         - every save and delete; the terminal states ``completed``, ``failed`` and ``aborted`` carry ``done_at`` and are flagged ``immediate``
       * - ``HarvestingJob``
         - every phase transition (progress and measurements are annotations - the receiver re-reads the job through ``with_process_info()`` so the push carries exactly what the endpoint answers)
       * - ``ServiceAlert``
         - an invalidation message with empty ``ids`` on harvesting state changes (#1030); the subscribers refetch their scoped alerts, the message itself carries no records

    Two preconditions decide whether an announcement happens at all:

    * the writing code runs with a request bound to the simple_history context - in a web request automatically, in a celery task because ``extras/tasks.py`` binds one; a background write from a bare management command or shell announces nothing, by design,
    * the write actually commits: announcements go out through ``send_msg_on_commit``, because a client which refetches while the transaction is still open would read the pre-update state.

The integration contract
########################

Transport
    ``/ws/default/`` of the ASGI application (``MrMap/asgi.py``), authenticated like the API: a knox ``?token=`` query parameter (``notify/auth.py``) or the session cookie. An anonymous connection is refused at connect; ``RealtimeBus`` builds the URL from the ``VITE_API_*`` configuration and passes the stored token.

Subscription
    The channel layer is one flat namespace, so a connection must *ask* for what it wants. ``notify/consumers.py`` accepts and undoes subscriptions with JSON frames::

        {"action": "subscribe",   "topic": "resource/BackgroundProcess/<uuid>"}
        {"action": "unsubscribe", "topic": "resource/BackgroundProcess/<uuid>"}

    Only topics matching ``resource/<Type>[/<pk>]`` (``TOPIC_PATTERN`` in ``notify/utils.py``) are joined; anything else is ignored - group names may not contain a ``/``, so both sides translate through ``group_name()`` and never hand the layer a name it would reject with a ``TypeError``. The frontend mirrors its local subscriptions onto the socket (``dataProvider.subscribe``/``unsubscribe``) and re-announces every live subscription whenever a *new* socket is attached - after a reconnect the server knows none of them.

Message shape
    One JSON document per announcement::

        {
          "topic": "resource/BackgroundProcess/<uuid>",
          "event": {
            "type": "updated",                  // created | updated | delete
            "payload": {
              "ids": [<primary key as the database answers it>],
              "records": [ { JSON:API primary data, exactly what the endpoint answers } ]
            }
          }
        }

    The ``ids`` carry the raw pk - a number for an auto pk - while ``records`` are in the full JSON:API shape with string ids; the delivery tests pin both.

    The record is rendered with the resource's own serializer, so the push and the API can never disagree about a field - that is the point of carrying the complete record and is what makes collapsing legal.

Topic layout and its one consequence
    ``created`` events are announced on the resource-wide topic ``resource/<Type>``; ``updated`` and ``delete`` on the per-record topic ``resource/<Type>/<pk>``. A client subscribed to one process's topic therefore never receives its *create* - the surfaces which must learn of new work (``RealtimeListBase``, the activity panel) subscribe to the resource-wide topic *in addition to* the topics of the records on their page.

Delivery rules at the consumer
    Channels creates one consumer instance per connection; the debounce bookkeeping hangs off that instance, never off the class:

    * at most one non-``immediate`` message per topic and connection per second (``debounce = 1000``) - a process which reports every step floods its own topic, not the user,
    * ``immediate`` messages are never collapsed: the create of a work item and the message carrying its terminal state. A client which misses one keeps showing a progress bar which will never finish,
    * disconnect leaves every joined group and forgets the window - a reconnected, resubscribed connection is served immediately.

Client behavior on top
    ``RealtimeBus`` keeps the socket: it reconnects with an exponential backoff capped at 10 s over at most 10 attempts and reports the ready state through ``HttpClientContext``. While the bus is not ``OPEN`` the aggregate surfaces fall back to polling (the activity panel refetches every 20 s). A pushed ``updated`` is merged into the current list/show data; a ``created``/``delete`` triggers a refetch of the page.

Extending it with a new background resource
    A new kind of background work joins the bus by being saved like the others and getting a receiver modeled on ``notify/signals.py``: build the payload with ``build_action_payload``, flag the messages the client must never miss as ``immediate``, and keep the topic at ``resource/<JsonApiType>``. On the frontend no new code is needed to display it - ``RealtimeListBase`` and ``RealtimeShowContextProvider`` subscribe by resource name.

Migration from the legacy behavior
##################################

There were two generations of background feedback before the bus carried all of it; both are gone and neither may come back unnoticed.

Redux-shaped ``TaskResult`` messages
    The first deployment pushed celery ``TaskResult`` rows in a redux-flavored shape (``{'type': 'taskResults/add', 'payload': ...}``) over a single shared group. The receivers behind it had been commented out for years; a skipped, non-reproducible test kept the shape nominally documented. Issue #1179 removed the receiver block together with the ``threads`` relation itself, leaving an explanatory comment in ``notify/signals.py``; issue #1209 removed what still documented the shape -- the skipped ``test_signals.py`` and the legacy payload examples in ``backend/cheatsheet.md``. (The read-only ``/api/v1/notify/task-results/`` endpoint remains; it is the job detail data, not a notification.) Nothing in the current chain speaks that shape; operators read this page instead of the cheatsheet's examples.

The persistent per-process snackbar
    The second generation rendered *one persistent notistack snackbar per background process*: ``SnackbarObserver`` reacted to every ``resource/BackgroundProcess`` bus event and kept a custom ``taskProgress`` snack alive per process until it finished. On a real deployment with concurrent harvesting that is the flood the epic was opened for - the screen covered with its own progress bars, failures unreadable under them. Epic #1203 retired it: issue #1204 removed ``SnackbarProvider``, ``SnackbarObserver``, ``ShowShortInfoBackgroundProcess`` and ``BackgroundProcessAlert`` and moved the one transient *direct-action* notice that was left over (the map transfer notice) to ``useNotify``. The bus contract above did not change; only the consumer which rendered a toast per message is gone, because the aggregate surfaces already carried everything the stack carried, and more durably.

The durable rule for new work
    Direct feedback: ``useNotify``. Background feedback: subscribe to the bus, render an aggregate. A new custom snackbar provider, toast queue or per-task notification is a violation of this page, whatever it renders. With #1225 merged, the custom snackbar stack is retired; the guard spec ``components/Layout/noCustomSnackbars.spec.ts`` -- landing as a follow-up commit of the pull request which documents this page, once #1225 is on master -- fails the test suite when a custom snackbar stack reappears in ``frontend/src``. The backend delivery tests below keep the transport honest.

Operator troubleshooting
########################

Everything on the chain is quiet by default - a missing redis, a dropped websocket or a publisher without a request bound produces no user-visible error, the activity simply stops updating while the API still answers. Read the symptom against this table:

.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - Symptom
     - First thing to check
   * - Panel/list update only on reload (or only every 20 s)
     - The polling fallback is answering. Check the browser's network tab for the ``/ws/default/`` socket: refused anonymous → token handling; never opened → the ASGI server does not route websockets (``daphne`` fronts ``MrMap/asgi.py``; plain WSGI cannot serve it).
   * - Some clients receive, others never do
     - ``CHANNEL_LAYERS`` must be the *same* redis at every process which publishes or consumes (web servers *and* celery workers). ``InMemoryChannelLayer`` in a multi-process deployment delivers only within one process and is otherwise silent - it belongs in tests only.
   * - ``WARNING can't send websocket message, ... is no topic`` in the backend log
     - A publisher built a topic outside ``TOPIC_PATTERN`` (``notify/utils.py``) - check the ``resource_type`` of the ``build_action_payload`` call.
   * - ``WARNING can't send websocket message`` with a stack trace in DEBUG
     - The payload build or the layer failed; most often a serializer error on an instance which lacks the annotations the serializer expects - the receivers re-read through the annotated queryset (``process_info()``, ``with_process_info()``) for exactly this reason.
   * - Rows change in the API, the frontend never reacts (during harvesting or a task)
     - The writing code runs without a request on the simple_history context - it is not reached through the web request or ``extras/tasks.py``; no announcement is made and none is logged. Bind a request (see the publish helpers of ``tests/django/notify/test_realtime_delivery.py`` for the minimal form) or accept silence for that write path.
   * - One client keeps showing a process below 100 % while the list says it failed
     - The terminal (``immediate``) message was lost - typically a redis flush/restart exactly at the terminal transition. This is why the surfaces are refetch-based aggregations and not push-only; the client recovers with the next refetch or reload.
   * - A screen subscribed to a process never learned that the process was created
     - By contract (topic layout above): a per-record topic carries no ``created``. Subscribe to ``resource/<Type>`` as well - ``RealtimeListBase`` already does.
   * - Reconnect storms after a restart
     - Expected once: clients retry up to 10 times with capped backoff and re-announce their subscriptions; the panel's polling covers the window. If a client never recovers after 10 attempts, the page reloads it (the surfaces are refetch-based, so nothing is lost).

Inspecting the bus by hand
    From a shell in the backend container (``docker compose run --rm backend python manage.py shell_plus``), an announcement can be published and watched like any other:

    .. code-block:: python

        from channels.layers import get_channel_layer
        from asgiref.sync import async_to_sync
        from notify.utils import group_name

        topic = "resource/BackgroundProcess"
        async_to_sync(get_channel_layer().group_send)(group_name(topic), {
            "type": "send.msg",
            "json": {"topic": topic,
                     "event": {"type": "created",
                               "payload": {"ids": [], "records": []}}},
            "immediate": True,
        })

    A browser tab with the app open reacts to it exactly as it does to a real announcement; if it does not, the socket, not the publisher, is the problem.

Tests which guard this page
###########################

* ``backend/tests/django/notify/test_realtime_delivery.py`` - end-to-end delivery over real websocket connections: subscription isolation, bounded progress bursts with terminal messages never dropped, 1000+ creates arriving complete, reconnect with clean state, concurrent harvesting runs kept apart.
* ``backend/tests/django/notify/test_consumer_fanout.py`` and ``test_harvesting_signals.py`` - the per-connection mechanics and the payload annotations, at unit level.
* ``frontend/src/providers/dataProvider.spec.tsx`` (subscription mirroring, replay after reconnect), ``frontend/src/jsonapi/components/Realtime/RealtimeBus.spec.tsx`` (reconnect policy, ready-state reporting), ``frontend/src/components/Resource/BackgroundProcess/BackgroundActivityPanel.spec.tsx`` (bounded display, keyboard, responsive bounds), ``frontend/src/i18n/backgroundActivity.spec.ts`` (both languages carry every status the panel can show).
