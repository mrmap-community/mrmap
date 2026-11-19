---
name: MrMap Celery and Background Work
description: "Working on MrMap background work — Celery tasks (registry/tasks, notify), task queues, django-celery-beat periodic tasks, BackgroundProcess progress records, WebSocket (Channels) notifications to the frontend, retry/monitoring behaviour, or on_commit task enqueueing."
---

# MrMap Celery & Background Work

Task skill for asynchronous work in `backend/`. The nearest `AGENTS.md` wins. Behavioural detail
lives in `docs/source/development/background-jobs.rst`,
`background-notifications.rst` and `celery-queues.rst`; this skill routes into them and the code.

## Activation

Load when the task touches `backend/registry/tasks/`, `backend/notify/`, `MrMap/celery.py`,
`MrMap/celery_queues.py`, `backend/system/scheduler.py`, periodic-task creation (`*/apps.py`
`post_migrate` hooks), or an API action that must return 202 and finish in the background.

## Mandatory project rules (sources named)

- Enqueue **only** from `transaction.on_commit(...)` — a task must never see uncommitted rows
  (pattern throughout `registry/tasks/harvest.py`, `registry/tasks/update.py`).
- Progress is reported through the `BackgroundProcess` model, not `task.update_state`: use
  `notify.tasks.BackgroundProcessBased.update_background_process(...)` (guarded single UPDATE,
  terminal state cannot be overwritten, fan-out via `post_save`) and `log_process()`
  (`notify/tasks.py`, `notify/models.py`).
- Queue names are declared once in `MrMap/celery_queues.py` and selected with `queue=` on
  `@shared_task`; there are no `CELERY_TASK_ROUTES` — do not introduce a routing split
  (root of this section: `MrMap/celery.py`, docs `celery-queues.rst`). A worker without `-Q`
  consumes all queues; a declared queue without a consumer logs ERROR at startup.
- Tasks serialize as JSON only (`CELERY_ACCEPT_CONTENT`) — never pickle payloads.
- Periodic tasks come from the **database** (`django_celery_beat` DatabaseScheduler); rows are
  created idempotently in `post_migrate` hooks (`registry/apps.py`, `notify/apps.py`,
  `system/apps.py`) — follow that pattern, don't add a static `CELERY_BEAT_SCHEDULE`.
- One-shot tasks that must not overlap use `extras.tasks.SingletonTask` / `singleton_lock`
  (pg advisory lock).
- The API side of background work is `extras.viewsets.AsyncCreateMixin`: create the
  BackgroundProcess, register the pre-decided task id with `append_celery_task_ids`, then
  `apply_async(task_id=...)` and answer 202 (`extras/viewsets.py`).
- Frontend updates: publish `resource/<Type>[/<pk>]` invalidations through
  `notify.utils.send_msg_on_commit` / `invalidate_service_alerts` — clients refetch; the payload may
  be empty (`notify/utils.py`, `backend/cheatsheet.md`).

## Recommended patterns (project code, mirror these)

- Module per domain in `registry/tasks/` (`service`, `harvest`, `update`, `monitoring`,
  `alerts`, `security`); task bases per domain (`HarvestingTask`, …).
- Retries: inherit the retry policy of `BackgroundProcessBased` (`autoretry_for`,
  `retry_backoff`) instead of hand-rolled loops; transient Redis/DB errors are the retried class.
- Chords/groups for fan-out with bounded `max_retries` (`registry/tasks/harvest.py`).
- External HTTP inside tasks keeps its timeout — capabilities download uses
  `session.send(..., timeout=15)` with `session.proxies = settings.PROXIES`
  (`registry/tasks/service.py`); see skill `mrmap-ogc` for the request rules.

## Anti-patterns

- `apply_async` inside an open transaction (missing `on_commit`) — the classic lost-row race.
- Doing long or remote work in the request/response path instead of a task.
- Polling/sleeping to wait for a task — in code, tests or the shell (root `AGENTS.md` "Running
  shell commands"); state flows through `BackgroundProcess` and WebSocket invalidations.
- Bypassing `BackgroundProcess` with a bespoke progress model — it is the single operational
  record (#1104 epic tracks its evolution).
- Relying on the Celery DB pool inside workers (settings deliberately disable pooling for celery
  processes — unfinished transactions).

## Framework references (recommendations, not project rules)

- Celery: https://docs.celeryq.dev/ — django-celery-beat:
  https://django-celery-beat.readthedocs.io/ — Channels: https://channels.readthedocs.io/

## MCP dependencies

None. Debug live notification flow with `manage.py shell_plus` in the `backend` service per
`backend/cheatsheet.md` (only there the Redis channel layer is visible). **Optional:** the
read-only `postgres` server (repo `opencode.json`, see `docs/development/mcp-servers.md`) can
inspect `django_celery_beat` rows and status tables of the running slot DB without opening a
shell; degrade to `shell_plus` when it is not configured.

## Verification (commands in `backend/AGENTS.md`, `backend/tests/AGENTS.md`)

1. `../.venv/bin/flake8 <files>` from `backend/`.
2. Targeted tests: the task's mirror under `tests/django/registry/tasks/`, notify tests under
   `tests/django/notify/` (naming differs per folder); patch `apply_async` on the task's dotted
   module path, and `transaction.on_commit` per `tests/django/` examples.
3. Delivery path changed: run `tests/django/notify/test_realtime_delivery.py` (real ASGI app via
   `WebsocketCommunicator`).
4. Ask `scripts/agent_capacity` before starting any stack, `--need suite` before the full suite
   (root `AGENTS.md`).

## Security constraints

- Task kwargs end up in the broker/Redis — never pass credentials, tokens or user passwords into
  a task; pass ids and re-read in the task under the proper permission context
  (`extras/tasks.py` carries the current user into the task).
- Tasks fetch external documents under skill `mrmap-ogc` rules (timeout, redirect containment,
  untrusted XML); do not log response bodies containing credentials.

## Explicit exceptions

- `CELERY_TASK_ALWAYS_EAGER` in tests is allowed, but code with on-commit publishing must guard
  against it (see `notify/utils.invalidate_service_alerts`).
- `system/` uses its own status/health mechanisms (heartbeat file in `system/scheduler.py`) — do
  not route operational health through BackgroundProcess.
