# MrMap

MrMap is a web application with a Django backend and a React/TypeScript frontend.

## Read first

The `AGENTS.md` nearest to the files you edit is the most specific one and wins over this file.

- `backend/AGENTS.md` — backend conventions, commands and CI gates.
  `backend/registry/AGENTS.md` — layout of the registry monolith.
- `frontend/AGENTS.md` — frontend conventions and commands.
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
- `.github/workflows/quality-assurance.yml` — what CI enforces: pre-commit checks, Behave scenarios, unit tests, Sonar.
- `CONTRIBUTING.md` — issue and pull request rules.

## Environment

- Run Docker Compose commands from the repository root and combine `docker-compose.yml` with
  `docker-compose.dev.yml`, as the IDE tasks in `.vscode/tasks.json` do.
- They read the root `.env` and, for backend services, `docker/backend/.mrmap.env`. Missing values
  fail early with a `Please configure ...` message; ask for them instead of inventing values.
- Application and test services share one image (`docker/backend/alpine.Dockerfile`), so any Django
  management command can be run in a one-off container.
- Frontend commands run from `frontend/` and need `npm install` once.

## Development guidelines

### General

- Make the smallest change necessary to solve the requested problem.
- Do not refactor unrelated code.
- Follow the style and architecture of the surrounding code.
- Reuse existing abstractions before creating new ones.
- Avoid adding dependencies unless necessary.
- Preserve backwards compatibility unless explicitly instructed otherwise.
- Do not silently change behavior outside the requested scope.

### Never do

- Do not hand-edit generated artifacts: migrations under `backend/*/migrations/`,
  `backend/locale/**/*.mo`, compiled frontend output.
- Do not add a migration unless the requested change alters the database schema; CI fails on model
  and migration drift in both directions.
- Do not bring up the whole stack (`docker compose up`) to verify a change; use the targeted
  commands documented in the area files.
- Do not change API contracts (JSON:API resource types, relationships, filter names, pagination,
  error shapes) or behaviour outside the requested scope.
- Do not use `npm run lint` or `npm run format` for a scoped change; they rewrite all of `src/`.

### Running shell commands

- Never wrap commands in `sleep` or other artificial waits, and never poll with sleep loops (`sleep 5 && ...`, `sleep && tail ...`, retry-until-sleep patterns).
- Run commands without any delay and read the exit code and output directly.
- For long-running commands, start them in the background with the output redirected to a temp file, then read that file when the result is actually needed.
- Batch independent commands, searches, and reads into a single call instead of spacing them out over time.

### Before modifying code

1. Inspect the relevant files and surrounding implementation.
2. Search the codebase for similar implementations.
3. Identify existing utilities, components, managers, querysets, or abstractions that can be reused.
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
| Frontend type checking, tests, production build | `frontend/AGENTS.md` |
| Starting the development stack | `.vscode/tasks.json`, `docs/source/development/getting-started.rst` |
| Debugging WebSocket notifications | `backend/cheatsheet.md` |
