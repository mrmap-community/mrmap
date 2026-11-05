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
  application; `scripts/wip` is the work claim board described under "Claiming work", and
  `scripts/test_wip_board_sync.py` checks its board writes offline (`python3
  scripts/test_wip_board_sync.py`, needs neither `gh` nor the network). `scripts/agent_capacity` is
  the host capacity gate described under "Check host capacity before starting another stack".
  `scripts/agent_supervisor` (command: `scripts/agent-supervisor`) is the OpenCode agent supervisor
  described in `docs/source/development/agent-supervisor.rst`; its approval gate decides which
  issue an agent may start, its scheduler decides which of those to start next against this very
  claim board and `scripts/agent_capacity`, its runner starts that one worker in its own worktree,
  process group and Compose project and stops it again, and `watch-prs` follows the CI of the pull
  requests those workers opened. The watcher resumes the same session for a failure that names a
  test, a lint rule or a build — once per head SHA, within `ci_repair_attempts` — and hands
  everything else to a human through `scripts/wip ask`; it never approves, reviews, merges,
  enqueues or reruns a workflow. Five offline checks cover the supervisor (`python3
  scripts/test_agent_supervisor_approvals.py`, `..._scheduler.py`, `..._capacity.py`,
  `..._runner.py` and `..._ci.py`; each needs neither `gh` nor the network nor a container, and
  none of them can write to a repository). The supervisor never claims an issue from its own
  checkout — the runner files `scripts/wip claim` from inside the worker's own worktree, which is
  the only way that claim's heartbeat can be refreshed. What a worker must never do (merge,
  review, force push) is handed to it as deny permissions, not as prompt wording, and that applies
  to a resumed worker as much as to a started one. An agent never applies
  `agent: approved` itself — a human does.

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

  This override file belongs to the local-build flow; the preferred prebuilt startup below carries
  the standard resets for the backend services itself.

#### Preferred agent startup: prebuilt dependency images

Instead of building the dependency images once per checkout, run the stack on the centrally built,
immutable images published by `.github/workflows/dev-images.yml` —
`ghcr.io/mrmap-community/mrmap-backend-dev:<fp>` and `ghcr.io/mrmap-community/mrmap-frontend-dev:<fp>`.
This is the preferred path; everything below this subsection keeps describing the fully supported
local-build fallback. The dependency fingerprint `<fp>` changes only when a dependency input changes
(requirements, Dockerfile, resolved base image), never on a source edit. Full background, resolver
semantics, troubleshooting and measured startup timings: `docs/source/development/prebuilt-images.rst`.

- Backend checks — one resolve per checkout pins every service sharing
  `docker/backend/alpine.Dockerfile` (`backend`, `django-tests`, `behave`, `pre-commit-check`,
  Celery) to the immutable tag and replaces their `build:` sections:

  ```bash
  export MRMAP_BACKEND_DEV_FP=$(python3 scripts/dev_image_id.py --resolve --image backend --build)
  export COMPOSE_FILE="docker-compose.yml:docker-compose.dev.yml:docker-compose.prebuilt.yml"
  ```

  `docker-compose.prebuilt.yml` carries the standard port and `container_name` resets of the
  override above, so backend checks need no job-local override file. The resolver uses a matching
  local image, else pulls the pinned tag, else — with `--build` — runs the sanctioned local fallback
  build under the same immutable tag; it exits `3` when the tag was never published, `4` on a
  transient registry failure, `0` on a hit.

- Frontend checks — layer the dependency image that seeds the project's `node_modules` volume
  instead of running `npm ci` on every start:

  ```bash
  export MRMAP_FRONTEND_IMAGE_FP=$(python3 scripts/dev_image_id.py --resolve --image frontend --build)
  export MRMAP_FRONTEND_DEV_IMAGE=ghcr.io/mrmap-community/mrmap-frontend-dev:${MRMAP_FRONTEND_IMAGE_FP}
  export COMPOSE_FILE="docker-compose.yml:docker-compose.dev.yml:docker-compose.prebuilt-frontend.yml:/tmp/agent-$COMPOSE_PROJECT_NAME.override.yml"
  ```

  The job-local override is needed here: `docker-compose.prebuilt-frontend.yml` does not reset the
  `container_name` pinned by `docker-compose.dev.yml`, so add
  `frontend-tests: { container_name: ${COMPOSE_PROJECT_NAME}-frontend-tests }` to it.

- Never combine `run --build` with the prebuilt files. Their `build:` sections are `!reset`, so
  `--build` is a **silent no-op** that keeps running the pinned image — compose reports no error,
  and the local source changes you thought you rebuilt into the image are not in it. With a prebuilt
  file in `COMPOSE_FILE` the pinned image is fixed; changes to `backend/.requirements/*` or a
  `package-lock.json` change the fingerprint, so re-run the resolve to get a (new) correct image.
- Isolation is for state; images are shared work. The unique project name, its network and named
  volumes and the one `django-tests` per stack stay exactly as they are: that state is disposable
  per job and never shared. The immutable `<fp>` images and their layers are the opposite —
  reusable by every job on the host, deliberately kept after a stack is torn down, and never
  removed as task cleanup (the no-global-prune rule below covers them).
- Local-build fallback: a project name is also the image prefix, so a fresh stack gets its own tag
  (`docker compose config --images` shows `<project>-<service>`) and `run` builds that tag because
  it is missing; with a warm BuildKit cache the layers are already there and that costs about a
  minute, not a rebuild. Build once per checkout (`docker compose build django-tests`) and do not
  add `--build` to `run` here either: a rebuild is only needed when `backend/.requirements/*` or
  `docker/backend/alpine.Dockerfile` changed, never on a branch switch, because the application code
  arrives over the bind mount. When several stacks of one checkout should share one build outright,
  pin the built services (`backend`, `django-tests`, `behave` and `pre-commit-check` share one
  Dockerfile and one set of build args) to a tag of your choosing in the job-local override — at
  the price that jobs with different requirement sets then overwrite each other's tag.
- A worktree has no `.env` (it is ignored, not tracked), so copy it and
  `docker/backend/.mrmap.env` from the main checkout before the first Compose command in it;
  otherwise every command fails with `required variable DJANGO_SECRET_KEY is missing a value`.
- Start only the services the selected check needs (`postgis`, `redis` and `mapserver` for the
  backend checks; nothing for `frontend-tests`), then use `docker compose ... run --rm --no-deps`
  for the check itself rather than `up` for test services. `--rm` removes the one-off container when
  it exits; dependencies, project networks and named volumes can remain until the end of the job.
- Never run `down`, `--remove-orphans` or volume removal against a project this job did not create,
  in particular the developer's. Never run `down` or `up` from a directory whose `.env` or compose
  file belongs to another project — a copied `.env` still carries the developer's
  `COMPOSE_PROJECT_NAME`; pass `-p <exact-project>` and make sure the compose files are the ones
  this job copied.
- Before creating temporary resources, register shell cleanup with `trap` for normal exit, failure
  and interruption (`EXIT`, `INT`, `TERM`), or use the runner's equivalent `finally` mechanism. Keep
  cleanup active for the full lifetime of background checks and preserve their exit status. For a
  verified job-owned disposable project, tear down with `docker compose -p <exact-project> down
  --volumes` using the same project name and Compose files, the override still in `COMPOSE_FILE` —
  **never add `--remove-orphans`**: it matches orphans by compose-file path, not project, and once
  wiped a foreign stack despite an exact `-p`. Before the `down`, counter-check the labeling with
  `docker ps -a --filter label=com.docker.compose.project=<exact-project>`: only own resources may
  be labeled. This volume removal is only for that disposable project's data; retain shared volumes
  and reusable images and build caches.
- After checks and before handing the task back, verify zero leftovers by exact name — containers,
  networks and volumes. Clean up on failed checks too.
  Report any leftovers with their exact names and the reason they remain. After an interrupted
  session, recover ownership from the job's recorded project/container names before removing
  anything; a stopped container or matching name prefix alone does not establish ownership. Never use
  global `docker system prune`, `docker container prune`, `docker volume prune`, or bulk removal of
  other jobs' resources as task cleanup.

#### Check host capacity before starting another stack

Isolation keeps jobs from corrupting each other, but it does not make the host
bigger — and on an agent host the jobs do not own the machine either: the
OpenCode session and the dockerd that starts its test stacks share one container
cgroup, so the room that matters is the cgroup's, not the machine's. Before
starting a new agent Compose stack — as a nightly runner deciding whether to
launch one more job, or before any `docker compose up` in a fresh worktree — run
`scripts/agent_capacity`. It is host-only Python with no network and no
application dependency: it reports the 15-minute load per core, the **effective**
memory (the smaller of `MemAvailable` and the headroom of this cgroup and every
parent, counting what cannot be reclaimed), free disk on `/`, the running
`mrmap-agent-*` stacks and agent processes and the memory pressure, prints a
single verdict line and exits `0` when the job still fits or `1` when it does
not. It refuses newcomers; it never pauses, renices or kills a running job.

Ask for the class of work you are about to start: `scripts/agent_capacity`
decides about a heavy Compose test stack (the default), `--need process` about
one more agent worker without a stack, `--json` answers for a program, and
`--stacks`/`--processes` pass counts a caller already keeps. The counts are
prospective — the job being asked about is included, so `stacks 2 (max 3)` fits
and `stacks 3 (max 3)` does not. The thresholds are environment overrides so a
job can tune the gate without editing the file: `AGENT_MAX_LOAD_PER_CORE` (1.5),
`AGENT_STACK_MIN_MEM_GB` (6), `AGENT_PROCESS_MIN_MEM_GB` (2), `AGENT_MIN_MEM_GB`
(16, the floor when no memory limit of this cgroup is visible),
`AGENT_MEM_RESERVE_GB` (2), `AGENT_MEM_NEAR_CEILING_PCT` (90),
`AGENT_MAX_MEM_PRESSURE` (10), `AGENT_MIN_DISK_GB` (100), `AGENT_MAX_STACKS` (3)
and `AGENT_MAX_PROCESSES` (6); inside a 16 GiB agent container `AGENT_MAX_STACKS=1`
is the honest setting. It never opens a socket and caps its `docker ps` call with
a timeout, so a host that is merely offline or whose docker daemon is stuck still
gets a verdict instead of hanging. What each metric means, why page cache is not
charged against a cgroup, how to read the same numbers by hand, the measured
before/after, and the operator runbook for the ceiling itself — raise the agent
container's limit or move the docker daemon out of it, and what to measure either
way (#1054): `docs/source/development/agent-capacity.rst`. The admission rules
have offline checks — `python3 scripts/test_agent_capacity.py`, which needs
neither docker nor the network.

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
- Base every new branch and worktree on current `origin/master` after a `git fetch origin`; create
  worktrees with `git worktree add <dir> -b <type>/issue-<N>-<topic> origin/master`. Being current
  matters exactly here: once the branch exists, the merge queue is what tests it together with
  master.
- Do not merge `origin/master` into a branch before opening the pull request, and not before every
  push while it is under review. Bring master in only when the branch actually needs it — a real
  conflict, a change from master this branch depends on to build or test, or a stated
  compatibility reason — and name which one in the merge commit. An unconditional pre-push merge
  re-runs the entire CI set for a commit that changes nothing about the change, and the merge
  queue already tests the integration of this head with master on a merge commit it builds itself.
- Never force-push or rebase a branch that is open for review: review comments and inline findings
  are anchored to commits, and a rewritten branch loses the diff a reviewer is reading. Rebase
  freely while a branch is still private. When master moves under a reviewed branch, push the new
  work as ordinary commits on top; if there is a genuine conflict, resolve it with a merge commit
  and let the queue re-test the combination.
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
- `scripts/wip ask "<question>"` hands the whole question to GitHub, not just
  the one-line reason: it posts the full text as one machine-managed question
  comment (`<!-- agent-question client=<tag> id=<id> -->`) on the issue, then
  runs the `wait` flow with a one-line summary. It is idempotent per client —
  re-`ask` while the question is still open refreshes that comment instead of
  stacking another — so a blocked job can be re-run without spamming the issue.
  Add `--issue N` to point at a specific issue; otherwise it uses the branch.
- `scripts/wip answers` reads the answers back: it lists the current client's
  open questions and the human replies to them (comments newer than the
  question, ignoring the machine-managed claim/question/board comments), prints
  the answer text, and stamps an answered question so it is never surfaced
  twice. Read it after a `Needs user` claim, then `scripts/wip claim` to resume.
- Run `scripts/wip done` when the pull request is ready for review or the
  work is abandoned.
- The claims are also a merge gate: do not merge a pull request whose issue
  still shows a live claim — live means a client is working and not finished,
  the board even names what it waits for. Run `scripts/wip ls` before
  merging; when the merge finishes your own work, release your claim
  (`scripts/wip done`) as part of being ready.
- Check `scripts/wip ls` before picking up an issue; somebody may hold it.
- The claim comments (`<!-- agent-claim ... -->`), the `status: wip` label and
  the board issue are machine-managed; never edit them by hand. `claim`, `wait`
  and `done` refresh the board as they run; regenerate it by hand with
  `scripts/wip board` when a refresh warned.
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
- Squashing the migration history to initial migrations was evaluated and rejected: the 35
  migration files are light and a cold targeted test run costs 18-20 s, with or without `--keepdb`.
  Raise the squash again when a cold targeted run exceeds ~60 s or the migration file count passes
  ~100.
