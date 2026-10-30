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

- Before starting containers, inspect `docker compose ls` and `docker ps -a` with Compose project
  labels. Record the project name and any containers that already exist. Reuse compatible shared
  dependencies instead of creating another stack for each test command. Keep the same project name
  throughout a job; do not change `.env` to select it.
- Use `docker compose ... run --rm` for checks, rather than `up` for test services. `--rm` removes
  the one-off container when it exits; dependencies, project networks and named volumes can remain.
  Use `--no-deps` when the required dependencies are already running and ready, and for
  `frontend-tests`, which has no service dependencies. Start only missing services needed by the
  selected check.
- Treat the developer's existing Compose project and any dependencies reused by multiple jobs as
  shared. Never run `down`, `--remove-orphans`, or volume removal against that project. Record exact
  names or IDs of temporary containers this job creates and remove those on completion; leave shared
  services and the frontend dependency cache available to other jobs.
- If a job needs an isolated stack, choose a unique project name such as
  `mrmap-agent-<issue>-<unique-run-id>` and pass `--project-name` on every Compose command. Verify that
  the name is unused before creating resources, and record the Compose files and ownership for
  cleanup. A different project name alone is insufficient: the development configuration publishes
  fixed host ports (including 5555, 5556 and 8090) and defines fixed `container_name` values. Resolve
  those conflicts in a temporary override before starting the required services; use a separate
  checkout for concurrent source changes.
- Before creating temporary resources, register shell cleanup with `trap` for normal exit, failure
  and interruption (`EXIT`, `INT`, `TERM`), or use the runner's equivalent `finally` mechanism. Keep
  cleanup active for the full lifetime of background checks and preserve their exit status. For a
  verified job-owned disposable project, clean up using the same project name and Compose files:
  `docker compose --project-name "$MRMAP_AGENT_PROJECT" -f docker-compose.yml -f docker-compose.dev.yml down --volumes --remove-orphans`
  (include any temporary override used at startup). This volume removal is only for that disposable
  project's data; retain shared volumes and reusable images/build caches.
- After checks and before handing the task back, verify that this job's temporary containers and,
  for an isolated project, its networks and volumes are gone. Clean up on failed checks too. Report
  any leftovers with their exact names and the reason they remain. After an interrupted session,
  recover ownership from the job's recorded project/container names before removing anything; a
  stopped container or matching name prefix alone does not establish ownership. Never use global
  `docker system prune`, `docker container prune`, `docker volume prune`, or bulk removal of other
  jobs' resources as task cleanup.

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
- Backend Docker test runs sharing PostgreSQL must not overlap: they create the same `test_mrmap`
  database and destroy each other mid-run. Use the host-wide lock in `backend/AGENTS.md`, including
  across worktrees and Compose test services.
- Frontend lint, strict type checking and tests with coverage are required CI checks. Historical red
  baselines were removed by the code-quality cleanup; see `frontend/AGENTS.md`.
- Scope backend lint runs to the files you touched (`../.venv/bin/flake8 <paths>` from
  `backend/`) during development. CI also checks migrations and translations; see
  `backend/AGENTS.md`.
