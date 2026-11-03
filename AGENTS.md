# MrMap

MrMap is a web application with a Django backend and a React/TypeScript frontend.

## Read first

The `AGENTS.md` nearest to the files you edit is the most specific one and wins over this file.

- `backend/AGENTS.md` — backend conventions, commands and CI gates.
  `backend/registry/AGENTS.md` — layout of the registry monolith.
- `frontend/AGENTS.md` — frontend conventions and commands.
  `frontend/src/components/AGENTS.md` — the shared UI components and the reuse gate before a new one.
  `frontend/src/jsonapi/AGENTS.md` — the schema-driven UI layer.

Before implementing changes, inspect the surrounding code and existing project patterns. Prefer extending existing abstractions over introducing new ones.

## Project structure

Backend paths are relative to `backend/`, frontend paths to `frontend/src/`.

- `registry/` — spatial service registry monolith: OGC services, metadata, harvesting, update jobs, monitoring, security proxy, OWS handling.
- `notify/` — background processes and task notifications delivered over WebSockets (Django Channels).
- `accounts/` — guardian based permissions, groups and users.
- `system/` — system status of the deployment, status logging, periodic task scheduler.
- `csw/`, `mapbender_compatibility/` — OGC CSW endpoint and legacy MapBender compatibility endpoints.
- `extras/` — shared Django/DRF building blocks: base viewsets, permissions, schema helpers, fields, managers, decorators, tasks. Look here before writing new generic code.
- `MrMap/` — project root: `settings.py`, `urls.py`, `celery.py`, `asgi.py`, management commands.
- `tests/` — `tests/django/` unit tests, `tests/behave/` acceptance tests written in Gherkin.
- `components/` — frontend UI components and feature areas, including `components/Resource/<Resource>/` screens.
- `jsonapi/` — frontend OpenAPI/JSON:API layer: schema parser, types, hooks, schema-driven components.
- `providers/`, `context/` — frontend data access, authentication, translations, system time and shared contexts.
- `ows-lib/`, `react-ows-lib/` — OWS domain logic and its React binding.
- `i18n/` — frontend translations in `en.ts` and `de.ts`; both languages are updated together.
- `docs/`, `docker-compose*.yml`, `.github/workflows/` — documentation, runtime stacks and CI.
- `scripts/` — host-side maintenance tools run from the repository root, not part of the deployed
  application; `scripts/wip` is the work claim board described under "Claiming work".

## Authoritative sources

Link to these instead of copying them into an `AGENTS.md`:

- `docs/architecture.md` — domain overview (services, update jobs, monitoring, security proxy).
- `docs/source/development/project-structure.rst` — app layout rationale and project vocabulary.
- `docs/source/development/definition_of_done.rst` — checklist to run before opening a pull request.
- `.github/workflows/quality-assurance.yml` — what CI enforces: pre-commit checks, Behave scenarios and unit tests.
- `CONTRIBUTING.md` — issue and pull request rules.

## Environment

- Run Docker Compose commands from the repository root and combine `docker-compose.yml` with
  `docker-compose.dev.yml`, as the IDE tasks in `.vscode/tasks.json` do.
- They read the root `.env` and, for backend services, `docker/backend/.mrmap.env`. Missing values
  fail early with a `Please configure ...` message; ask for them instead of inventing values.
- Application and test services share one image (`docker/backend/alpine.Dockerfile`), so any Django
  management command can be run in a one-off container.
- Frontend commands run from `frontend/`. `node`/`npm` are usually not on the host; use the
  `frontend-tests` service instead (see `frontend/AGENTS.md`).

### Workspace bootstrap

Only relevant in a fresh checkout — check before re-running, a normal development workspace already
satisfies most of it.

- Backend lint loop only: `python3 -m venv .venv && .venv/bin/pip install -r backend/.requirements/dev.txt`
  (`dev.txt` brings flake8 and autopep8; `backend/requirements.txt` adds base and docs on top).
- Nothing further is provisioned on the host. GDAL/GEOS and Node are deliberately absent and must not
  be installed — everything that needs them runs in Docker
  (`docs/source/development/getting-started.rst`), and a host copy at a different version yields
  results that disagree with CI. Node dependencies belong to the `frontend-tests` named volume, not
  to the host checkout.
- Installing MrMap itself is out of scope for agent work; see `docs/source/installation/`.

### Docker ownership and cleanup for parallel agents

- Every job runs its checks in **its own Compose stack**. Do not reuse the developer's stack or the
  stack of another job: two backend runs against one PostgreSQL destroy each other's data (the
  `django-tests` and `behave` commands both create and flush `test_mrmap`), and shared dependencies
  get restarted by whichever job needs them. Jobs run checks concurrently without any lock.
- Choose a unique project name such as `mrmap-agent-<issue>-<unique-run-id>` and keep it for the
  whole job; do not change `.env` to select it. Record the name and the override file for cleanup.
- A project name alone is not enough: the development configuration publishes fixed host ports
  (5555, 5556, 8001, 8003, 8080, 8090) and pins `container_name` (`backend-dev`,
  `mrmap-frontend-tests`), so a second stack cannot start beside the first. Write one job-local
  override that frees them, and add it to `COMPOSE_FILE`:

  ```bash
  export MRMAP_AGENT_PROJECT=mrmap-agent-852-1103
  cat > /tmp/agent-$MRMAP_AGENT_PROJECT.override.yml <<'YAML'
  # Compose merges sequences; only `!reset` clears the inherited ones.
  services:
    backend:
      container_name: ${COMPOSE_PROJECT_NAME}-backend
      ports: !reset []
    behave:
      ports: !reset []
    mapserver:
      ports: !reset []
    postgis:
      ports: !reset []
    redis:
      ports: !reset []
  YAML
  export COMPOSE_PROJECT_NAME=$MRMAP_AGENT_PROJECT
  export COMPOSE_FILE="docker-compose.yml:docker-compose.dev.yml:/tmp/agent-$MRMAP_AGENT_PROJECT.override.yml"
  ```

  With that in the environment, the `-f docker-compose.yml -f docker-compose.dev.yml` of the
  examples elsewhere can be dropped. Run all Compose commands from the repository root: the
  `COMPOSE_FILE` paths are relative to it. Other services pin host ports as well (`frontend` 8000,
  `flower` 5655, `inspire-validator` 5557, `victoria-logs` 5514, plus pgadmin and grafana) and
  `frontend-tests` pins its container name; add them to the override when a check needs them.
- Isolation is for state: the unique project name, its network and named volumes and the one
  `django-tests` per stack stay exactly as they are. Built images are not job state. A project name
  is also the image prefix, so a fresh stack gets its own tag (`docker compose config --images`
  shows `<project>-<service>`) and `run` builds that tag because it is missing; with a warm
  BuildKit cache the layers are already there and that costs about a minute, not a rebuild. Build
  once per checkout (`docker compose build django-tests`) and do not add `--build` to `run`: a
  rebuild is only needed when `backend/.requirements/*` or `docker/backend/alpine.Dockerfile`
  changed, never on a branch switch, because the application code arrives over the bind mount.
  When several stacks of one checkout should share one build outright, pin the built services
  (`backend`, `django-tests`, `behave` and `pre-commit-check` share one Dockerfile and one set of
  build args) to a tag of your choosing in the job-local override — at the price that jobs with
  different requirement sets then overwrite each other's tag.
- A worktree has no `.env` (it is ignored, not tracked), so copy it and
  `docker/backend/.mrmap.env` from the main checkout before the first Compose command in it;
  otherwise every command fails with `required variable DJANGO_SECRET_KEY is missing a value`.
- Start only the services the selected check needs (`postgis`, `redis` and `mapserver` for the
  backend checks; nothing for `frontend-tests`), then use `docker compose ... run --rm --no-deps`
  for the check itself rather than `up` for test services. `--rm` removes the one-off container when
  it exits; dependencies, project networks and named volumes can remain until the end of the job.
- Never run `down`, `--remove-orphans` or volume removal against a project this job did not create,
  in particular the developer's.
- Before creating temporary resources, register shell cleanup with `trap` for normal exit, failure
  and interruption (`EXIT`, `INT`, `TERM`), or use the runner's equivalent `finally` mechanism. Keep
  cleanup active for the full lifetime of background checks and preserve their exit status. For a
  verified job-owned disposable project, clean up using the same project name and Compose files:
  `docker compose down --volumes --remove-orphans` with the override still in `COMPOSE_FILE`. This
  volume removal is only for that disposable project's data; retain shared volumes and reusable
  images and build caches.
- After checks and before handing the task back, verify that this job's containers, networks and
  volumes are gone. Clean up on failed checks too.
  Report any leftovers with their exact names and the reason they remain. After an interrupted
  session, recover ownership from the job's recorded project/container names before removing
  anything; a stopped container or matching name prefix alone does not establish ownership. Never use
  global `docker system prune`, `docker container prune`, `docker volume prune`, or bulk removal of
  other jobs' resources as task cleanup.

## Development guidelines

### General

- Make the smallest change necessary to solve the requested problem.
- Do not refactor unrelated code.
- Follow the style and architecture of the surrounding code.
- Reuse existing abstractions before creating new ones. The inventories of what exists are
  `frontend/src/components/AGENTS.md` (shared UI components), `frontend/src/jsonapi/AGENTS.md` (the
  schema layer), `backend/AGENTS.md` and `backend/registry/AGENTS.md` (`extras/` plus the registry
  layout). Read the closest one before writing a new unit of UI, API or database code.
- Avoid adding dependencies unless necessary.
- Preserve backwards compatibility unless explicitly instructed otherwise.
- Do not silently change behavior outside the requested scope.

### Never do

- Do not hand-edit generated artifacts: migrations under `backend/*/migrations/`,
  `backend/locale/**/*.mo`, compiled frontend output. Regenerate with the generator instead — catalogs
  go through `makemessages` then `compilemessages`. CI regenerates the German catalog and fails when the
  committed `django.po` differs, and `backend/.bash_scripts/check_translations.sh` fails on an empty
  `msgstr`, but nothing fails on a `#, fuzzy` entry — and `compilemessages` skips those, so a fuzzy
  message silently falls back to the English msgid at runtime. Clear the flag when you translate and
  rebuild the `.mo` in the same change.
- Do not add a migration unless the requested change alters the database schema; CI fails on model
  and migration drift in both directions.
- Do not bring up the whole stack (`docker compose up`) to verify a change; use the targeted
  commands documented in the area files.
- Do not change API contracts (JSON:API resource types, relationships, filter names, pagination,
  error shapes) or behaviour outside the requested scope.
- `npm run lint` is read-only. Do not use whole-tree `npm run lint:fix` or `npm run format` for a
  scoped change; they rewrite files across `src/`.
- Do not copy a shared component, serializer, viewset or manager into a feature folder to adjust one
  detail; extend it or wrap it. A fork drops the tests and later fixes of the original and both copies
  drift. If a new file really is needed, name the alternatives that were considered in the commit
  message, and file the new code where its reuse potential is.

### Running shell commands

- Never wrap commands in `sleep` or other artificial waits, and never poll with sleep loops (`sleep 5 && ...`, `sleep && tail ...`, retry-until-sleep patterns).
- Run commands without any delay and read the exit code and output directly.
- For long-running commands, start them in the background with the output redirected to a temp file, then read that file when the result is actually needed.
- Batch independent commands, searches, and reads into a single call instead of spacing them out over time.

### Before modifying code

1. Inspect the relevant files and surrounding implementation.
2. Search the codebase for similar implementations — of the whole unit being built (a card, a screen, a
   serializer field, a permission class), not only of the helper that is about to be written. Search by
   capability and by the user-visible wording, not by the name of the new thing: an existing component
   is usually named after the screen it first appeared on, and it is reusable elsewhere because it reads
   its data from a context.
3. Identify existing utilities, components, managers, querysets, or abstractions that can be reused,
   and adapt to them — provide their context, or extend them — before writing an equivalent.
4. Consider backend/frontend interactions before changing API-facing behavior.

### Verification

After modifications:

- Run the most relevant existing tests, targeted first and broader suites when scope or risk
  warrants it.
- Run the checks CI enforces for the area you changed: type checking and tests on the frontend;
  flake8, pending migrations and translation checks on the backend (see `backend/AGENTS.md`).
- Add or update tests when behavior changes.
- Do not modify tests merely to make an incorrect implementation pass.
- Report commands run, their results, and any check that could not be run.

### SonarCloud findings

SonarCloud scans the new code of a change and answers the pull request with its findings. Solve a
reported finding where it was reported: fix the flagged code or resolve the finding in the report.
Do not push new code around a finding to work around it — new code is scanned as new code too, the
finding stays open and the report ends up with more new issues than before.

A genuine false positive is the exception: a normative OGC/ISO/INSPIRE identifier that only looks
like an insecure URL or an IP address is suppressed with a `NOSONAR` comment carrying the reason on
the reported line, as `docs/source/development/code-quality.rst` describes. Rewriting the
identifier itself is not an option — it breaks document matching against upstream services.

## Git conventions

- Branch names are `<type>/<short-topic>`, for example `feature/service-update` or
  `housekeeping/cleanup-frontend-src`.
- Commit messages are short lowercase summaries of the change, for example "adds ...", "fixes ...",
  "implements ...".
- Keep unrelated formatting or refactoring out of a change.

### Filing issues

- Always label at creation: `gh issue create --labels 'type: bug' ...`. The web form takes the label
  from the issue template's front matter (`type: bug`, `type: story`, `type: housekeeping`,
  `type: documentation`), but `gh issue create` bypasses the template and files the issue unlabeled,
  where it slips past the triage views. Use the same taxonomy the templates use; `status:`,
  `priority:` and `phase:` labels belong to maintainers, and pull requests carry none.
- An issue that belongs to an epic carries the epic's slug as a title prefix: `harvest-load: what
  breaks and how`. The slug is declared on the epic's first body line (`slug: <kebab-name>`,
  lowercase, ≤ 20 chars, like a branch name); the epic title itself carries no prefix. The machine
  relation is authoritative and separate from the title: `gh issue edit <epic> --add-sub-issue
  <child>` registers the native sub-issue link, the title prefix is only its readable echo. When
  link and prefix disagree, fix the prefix.

### Claiming work

Several agents and machines work on this repository in parallel; which client
works on what lives in GitHub, not in chat sessions. `scripts/wip` (host
Python + `gh`, no application dependency) maintains it: one claim comment per
issue and client, the `status: wip` label, and the pinned "🤖 Agent Work
Board" issue listing the active claims.

- Run `scripts/wip claim` from the repository root before the first file edit
  or commit of a session; the issue number comes from the `issue-<N>` part of
  the branch name. Claiming is idempotent, so re-running is always safe.
- Claiming refuses while another client holds a fresh claim on the issue; the
  message names the holder and its heartbeat. Then pick a different issue —
  never work two clients on one issue. A claim whose heartbeat went stale
  passes with a warning; `scripts/wip claim --force` takes a foreign claim
  over deliberately, e.g. after the holder was confirmed gone.
- Run `scripts/wip claim` again after every `git push`; it refreshes the
  heartbeat, and a claim without a heartbeat for three days is flagged stale
  on the board.
- When a step needs a human — before asking a question, requesting a
  permission decision or waiting for credentials — run
  `scripts/wip wait "<what you need>"`; the board lists the claim under
  *Needs user* (first) until the next `scripts/wip claim` marks it running
  again.
- Run `scripts/wip done` when the pull request is ready for review or the
  work is abandoned.
- The claims are also a merge gate: do not merge a pull request whose issue
  still shows a live claim — live means a client is working and not finished,
  the board even names what it waits for. Run `scripts/wip ls` before
  merging; when the merge finishes your own work, release your claim
  (`scripts/wip done`) as part of being ready.
- Check `scripts/wip ls` before picking up an issue; somebody may hold it.
- The claim comments (`<!-- agent-claim ... -->`), the `status: wip` label and
  the board issue are machine-managed; never edit them by hand. Regenerate
  the board with `scripts/wip board`.
- If `gh` is not authenticated on the host, say so once and continue without
  claiming; claiming must never block the actual work.


## Working with uncertainty

If requirements are ambiguous, prefer behavior consistent with the existing codebase.

Do not invent APIs, models, fields, components, or project conventions. Inspect the implementation first.

If a requested change would require a significant architectural change, API contract change, or database migration that was not explicitly requested, explain the implication before proceeding.

## Common commands

The project uses dedicated Docker containers for running tests. Prefer the test containers instead
of running test commands directly in the application containers. The exact commands live in the area
documents:

| Task | Documented in |
| --- | --- |
| Django unit tests, Behave scenarios, flake8, migration and translation checks | `backend/AGENTS.md` |
| Behave run tiers, step vocabulary, fixture tags and the green baseline | `backend/tests/behave/AGENTS.md` |
| Frontend type checking, tests, production build | `frontend/AGENTS.md` |
| Frontend resource screens and their specs | `frontend/src/components/AGENTS.md` |
| Writing or debugging backend tests | `backend/tests/AGENTS.md` |
| Starting the development stack | `.vscode/tasks.json`, `docs/source/development/getting-started.rst` |
| Debugging WebSocket notifications | `backend/cheatsheet.md` |

## Verification reality check

- `flake8` runs in ~1 s from the host virtualenv (`backend/../.venv/bin/flake8`); everything else
  needs Docker, because `backend/MrMap/settings.py` calls `gdal_info()` and GDAL/GEOS are not
  installed on a plain host.
- Backend Docker test runs must not share a PostgreSQL: they create the same `test_mrmap` database
  and destroy each other mid-run. Give every run its own Compose stack (see "Docker ownership and
  cleanup for parallel agents"), then runs from different jobs and worktrees may overlap freely.
- Frontend lint, strict type checking and tests with coverage are required CI checks. Historical red
  baselines were removed by the code-quality cleanup; see `frontend/AGENTS.md`.
- Scope backend lint runs to the files you touched (`../.venv/bin/flake8 <paths>` from
  `backend/`) during development. CI also checks migrations and translations; see
  `backend/AGENTS.md`.
