# Debugging websocket notifications

The notification rules (topics, message shape, debounce, reconnect) are
documented in `docs/source/development/background-notifications.rst`. This
page is only how to poke at a running stack by hand.

## Send a message from the backend shell

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml \
    run --rm backend python manage.py shell_plus
```

```python
>>> from notify.utils import send_msg
>>> send_msg({
...     "topic": "resource/BackgroundProcess/11111111-1111-1111-1111-111111111111",
...     "event": {"type": "updated", "payload": {"ids": [], "records": []}},
... })
```

`send_msg` looks up the channel layer group of the topic and drops (with a
warning) anything whose topic does not translate to a group name, so a typo
never reaches the layer. Run the shell inside the `backend` service: only
there does the shell see the Redis channel layer the ASGI application
broadcasts over.

The frontend refetches as soon as a message arrives, so `ids` and `records`
may be empty — the message is only the invalidation. Inside an open
transaction use `send_msg_on_commit` instead, otherwise the client refetches
the state from before the update.

## Message shape

```python
{
    "topic": "resource/HarvestingJob",                    # created
    "topic": "resource/HarvestingJob/<pk>",              # updated / deleted
    "event": {"type": "created|updated|deleted",
              "payload": {"ids": [...], "records": [...]}},
}
```

`notify.utils.build_action_payload` builds exactly this from a serializer,
and the signals in `notify/signals.py` publish it whenever a model with a
listener is saved. `send_msg(..., immediate=True)` marks the messages the
consumer must not collapse into its debounce window — that is the create
event and the terminal state of a background process.

## Watch the fan out without a browser

The client joins a topic with a subscribe frame and leaves it again with an
unsubscribe frame:

```json
{"action": "subscribe", "topic": "resource/BackgroundProcess/<pk>"}
```

A connection that never subscribes only receives the messages published to
the static `default` group. The end-to-end tests in
`tests/django/notify/test_realtime_delivery.py` drive exactly this protocol
against the real ASGI application with a `WebsocketCommunicator` — the
fastest way to see what a client would receive is to extend one of them.

## Legacy

Before the Background Job Center (epic #1203) every celery task announced its
`TaskResult` over the websocket and the frontend toasted about it. The
receiver which did that is retired; `TaskResult` records and the read-only
`/api/v1/notify/task-results/` endpoint still exist for the job detail
screens, but background work is announced as `BackgroundProcess` records
now, per the topics above.
