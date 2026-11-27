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

## GitHub Native First and agent independence

MrMap is a geospatial management application, not an agent orchestration or
development-management platform. Adapt the development workflow to native GitHub
capabilities and avoid custom development-management software; when a desired workflow
is unsupported, simplify or change the process before introducing custom automation.
Use native issues, parent/sub-issues, dependencies, assignees, Draft PRs and Projects.
A person or external coordinator assigns one worker after checking blockers and
conflicting work. Assignment is not a lock; dependencies are not enforced merge gates.
Core runtime, build, deployment, migrations, CI, monitoring, backup/recovery, tests
and releases must work without an agent platform, MCP client or LLM credentials.
OpenHands, OpenCode, Codex and other clients are optional. AI-specific features use
replaceable providers, isolated credentials and validated outputs. Optional model-written
documentation narrative must not make a coding-agent platform a build dependency.

## Standard First — reuse before reinventing

MrMap owns geospatial management, domain workflows, resource relationships,
domain authorization policies and their user-facing representation. It is not
a general-purpose backup, observability, authentication, testing,
documentation or infrastructure-management platform.

Before designing an epic, introducing an architectural component or adding
generic functionality, evaluate these options in order:

1. Existing MrMap implementations and installed dependencies.
2. Native framework, database, browser and infrastructure capabilities.
3. Applicable open standards (especially OGC, ISO, JSON:API and OpenAPI).
4. Maintained open-source libraries or standalone upstream software.

Prefer configuration, composition and small integration adapters. Do not
introduce a parallel engine, duplicate source of truth, general-purpose
framework or service when an existing solution meets the requirement.
Use domain-local code for genuinely MrMap-specific behavior; upstream generic
fixes to shared libraries where practical. Do not replace working code or
add dependencies merely because alternatives exist.

For a new dependency or nontrivial architectural component, record a concise
comparison in the issue or PR: existing reuse points, relevant upstream
documentation, selected approach, remaining custom code and why it is needed.
Evaluate license, maintenance, security, compatibility with pinned versions,
resource and operational overhead, migration/rollback and testability.
Validate material uncertainty with a small representative proof of concept.
Prefer fewer dependencies and optional infrastructure; no mandatory external
service or agent runtime without explicit maintainer approval.

Keep existing security, data integrity, authorization, compatibility and
review guarantees. Standard software is not a reason to weaken domain
semantics or replace authoritative application state with sampled telemetry.
Apply this rule proportionately: routine fixes need no separate ADR or
approval workflow; material unresolved trade-offs follow the existing human
decision process.


### Minimal implementation and stop rule

- For epics and generic cross-cutting functionality, **configuration first**:
  identify the smallest supported standard solution and narrow the scope before
  implementing. Prefer adapting our workflow to an upstream tool over extending
  the tool with custom orchestration. Existing issues/PRs are not exempt.
- If generic infrastructure (release, docs, testing, backup, monitoring, CI,
  workflow/state machine, evidence or registry tooling) still needs custom code,
  demonstrate the specific upstream gap with a small test and obtain an explicit
  maintainer decision **before** implementing a new engine or substantial adapter.
  An existing approved issue is not approval for unplanned architectural scope.
- Deliver only the required behavior; stop once acceptance criteria are met.
  Do not add speculative features, parallel sources of truth, frameworks,
  simulated platforms or future-proofing. Prefer deleting obsolete code/tests
  to maintaining two systems. Keep domain, security and data integrity checks.
- Reviewers must challenge unnecessary custom code and scope expansion even when
  CI passes. For material tooling changes, the PR should briefly identify reused
  components, remaining custom code and why it is necessary; request simplification
  rather than repeatedly fixing an avoidably complex design.

This rule requires no new tooling, automated policy checker or additional
approval process for ordinary domain fixes. Apply existing human decisions only
to material unresolved trade-offs.

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
  application; their offline suites are `scripts/test_*.py`, run together by
  `scripts/check_repo_tooling.sh` (needs neither `gh` nor the network). The retired claim
  board and eligibility checker (`scripts/wip`, `scripts/next_eligible.py`) were removed on
  2026-11-25 once the #1391 exception that had kept them alive finished (#1794); their
  history and retirement conditions stay readable in git and in
  `docs/source/development/github-flow-transition.rst`.
  Development execution and resource management belong to the external environment.
  AO is retired. Optional clients do not authorize reviews, merges, thread resolution,
  access changes or permanent-branch writes. Ask a person on the issue for actions
  outside the worker's authority. Do not add a scheduler, daemon or CI watcher here.
  `scripts/nginx_routing_smoke.py` asserts which URLs the nginx of the frontend answers with the
  SPA and which it proxies to the backend (`python3 scripts/nginx_routing_smoke.py`; two containers
  of the nginx the frontend image is built on, no stack). A new frontend route whose name starts
  with a proxied prefix belongs in its table, which is how #1036 would have been caught.
  `scripts/static_mounts_smoke.py` asserts that no compose mount shadows the static roots the
  frontend image serves (`python3 scripts/static_mounts_smoke.py`; it reads `docker compose
  config` and starts nothing). A mount at, above or inside `/var/www/mrmap` is the failure #922
  removed and #1027 re-reported: a named volume there wins over the image, and rebuilds silently
  stop reaching the browser.
  `scripts/migration_graph_smoke.py` asserts that the migration graph of (branch ∪ develop) still
  has one leaf per app (`python3 scripts/migration_graph_smoke.py`; host Python plus the `git`
  CLI, no docker, no `gh`, no network, a fifth of a second). Two branches which each add a
  `0038` are green alone and red in the merge queue, because two leaf nodes of one app is what
  `makemigrations` refuses with "Conflicting migrations detected"; run it before pushing a branch
  that adds a migration and it names both leaves, the file of each and the number to renumber to.
  Its offline checks are `python3 scripts/test_migration_graph_smoke.py` (synthetic graphs plus
  one throw-away git repository; needs neither docker nor the network).
  `scripts/otlp_storage_smoke.py` asserts the optional metrics/traces stores of #1778 against
  ADR-0003: the pinned images and flags, the volume, retention and byte bounds, that neither
  store publishes a host port, that Grafana's two datasources and their pinned plugins are the
  only readers, and - `--live` - that a hand-written OTLP/HTTP histogram and span are accepted,
  queryable and retrievable in an isolated Compose project (`python3 scripts/otlp_storage_smoke.py
  --live --json evidence.json`; two stores plus one probe container, own project name, no
  application service). The offline half starts nothing and is what CI can afford; `--live` is
  the reproducible evidence the issue asks for. Requests are issued from a container of the
  check's own on `mrmap-internal`, never from a host socket, because the deployment publishes no
  port for either store and the check must work against a remote or rootless Docker daemon.
  `scripts/release_gates.py` decides what a release candidate may claim (#1583, epic #1577): the
  OpenAPI/JSON:API contract diff against the committed baseline (today `pre-baseline`, measured 0
  tags, with the reviewed 0.x reading declared in the manifest), the version bump and the
  `### Migration notes` the range owes, the migration graph plus the staged #1180 boundaries and
  fake or unapproved-destructive migrations, and the promotion attestation binding a candidate
  SHA to its tests/Sonar/dependency/artifact evidence; the baseline, ledger and #1180 constraint
  files in `scripts/` are reviewed content — the PR that edits one is the review (`python3
  scripts/test_release_gates.py` runs the 63-check suite offline; `.github/workflows/
  release-gates.yml` runs the gates; docs: `docs/source/development/release-compatibility-gates.rst`).
  `scripts/release_promotion.py` is the protected path a planned version takes from develop to
  master (#1584, epic #1577): five idempotent human-gated steps — `plan` reads the planned candidate
  (VERSION, its projection, the manifest and the folded changelog section must agree), `evidence`
  plus `preflight` bind CI's conclusions and the gate reports into the one attestation of
  `release_gates.py promote`, `open-release-pr` freezes `release/v<version>` at the candidate and
  opens the PR to master (a person merges — that merge IS the release decision), `finalize`
  tree-checks master against the tested candidate before pushing the annotated tag and the GitHub
  release in the same run, and `sync` opens the reviewed master→develop sync PR; it never pushes a
  permanent branch, never moves a tag or release branch that stands elsewhere, and refuses rolling
  aliases while no reviewed alias ledger exists (Q1 of #1578 fixed the tag shape and approved no
  alias — ADR-0002). `.github/workflows/release-promotion.yml` dispatches the
  steps behind the protected `release-stable` environment (an administrator must create it WITH
  required reviewers before the first run — GitHub auto-creates a missing environment unprotected);
  `python3 scripts/test_release_promotion.py` runs the 31-check offline suite (synthetic
  repositories, journaling `gh` shim) via `scripts/check_repo_tooling.sh`; docs:
  `docs/source/development/release-promotion.rst`).
  `scripts/release_lifecycle.json` is the machine-readable release lifecycle — the
  #1585 interface the documentation automation (#1604) generates from and the interface
  tests (#1586) verify against: channels, phases with their actors, the protected
  promotion environment, the Sphinx `sphinx_multiversion` tag selection that documents
  released versions. `python3 scripts/test_release_lifecycle.py` (offline, part of
  `scripts/check_repo_tooling.sh`) fails when the description drifts from the workflows,
  the scripts or `docs/source/conf.py` it names. The operator-facing prose it feeds is
  `docs/source/administration/release-operator-runbook.rst`, the entry page of the new
  `docs/source/administration/` portal section.
  `scripts/decisions` is the decision-request protocol described under "Asking for human
  decisions": numbered questions, `Q7: C` answers verified against GitHub's
  `author_association`, append-only audit-trail comments and a generated view of the issue's
  Decision register. Its offline checks are `python3 scripts/test_decisions.py` (every
  GitHub call stubbed, no `gh`, no network); CI runs no job for `scripts/`, so run them by
  hand when touching either tool.
  `scripts/test_validator_retirement.py` is the guard that the ETF validator retired by
  #1529 (epic #1527) does not creep back: it sweeps the tracked Compose, VS Code, Sonar and
  `docker/` surfaces for the validator's name and — where docker is present, probing for it
  and skipping the affected checks out loud where it is not — resolves every committed
  Compose variant and fails when a validator service, its build context or its old host
  port 5557 appears, or when the shared networks no longer survive the resolution
  (`python3 scripts/test_validator_retirement.py`).

### Asking for human decisions

Design questions an agent cannot answer itself — normative ISO/OGC readings,
product scope, migration risk appetite — are asked with `scripts/decisions`, not
as prose, so the answers stay findable. A human answers `Q7: C`; `record` verifies
via GitHub's `author_association` that the answer came from an OWNER, MEMBER or
COLLABORATOR and not a Bot, appends audit-trail comments, and `register` syncs the
issue's "Decision register" table from that trail.

- Answering a design question is a design decision. It is not the `agent: approved`
  label and not a pull-request review; those stay with people, and no recorded answer
  may be presented as if it granted either.
- Ask with a stated recommendation and only a handful of questions at a time (the tool
  refuses more). Requests posted through the tool carry a machine marker; a hand-written
  request in the same shape is still read, but the tool warns that its provenance cannot
  be verified.
- After answers arrive: `scripts/decisions --issue N record --write` (idempotent —
  re-running records nothing twice), then `scripts/decisions --issue N register --write`.
  A body a human edited while the write was prepared stops the write; rerun.
- When a named owner keeps the decision (e.g. @armin11 for standards reviews), record
  with `--gate 'Q1-Q6=@armin11:reason'`: answers are kept as preferences and the row
  reads `Awaiting @armin11`, never `Accepted`, until that owner answers or overrides.
- Silence records nothing; a row never reads `Accepted` while its evidence names an
  unanswered question; prose run together or naming two options is flagged for
  clarification, never guessed. A human can undo a recorded outcome with `reopen` or
  `override --outcome ... --source <comment-url>`, which verify the cited comment the
  same way answers are.
- After a context loss an agent resumes from the issue alone:
  `scripts/decisions --issue N scan` says what is asked, answered and open. Schema,
  reaction rules and the offline checks: `docs/source/development/decision-requests.rst`.

## Authoritative sources

Link to these instead of copying them into an `AGENTS.md`:

- `docs/architecture.md` — domain overview (services, update jobs, monitoring, security proxy).
- `docs/source/development/project-structure.rst` — app layout rationale and project vocabulary.
- `docs/source/development/definition_of_done.rst` — checklist to run before opening a pull request.
- `docs/source/development/github-flow.rst` — the canonical contribution workflow.
- `docs/source/development/github-flow-transition.rst` — migration inventory and operator actions.
- `.github/workflows/quality-assurance.yml` — what CI enforces: pre-commit checks, Behave scenarios and unit tests.
- `.github/workflows/script-tests.yml` — the repository tooling in `scripts/`, via `scripts/check_repo_tooling.sh`. Separate job on a bare runner, because the QA container binds only `./backend` and cannot reach `scripts/` at all.
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
  `flower` 5655, `victoria-logs` 5514, plus pgadmin and grafana) and
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
  transient registry failure, `0` on a hit. To decide between pulling and building without paying
  for either, `--exists` answers the publish question in about half a second (no docker, nothing
  downloaded) — existence only, never a substitute for the resolve when the image is really wanted.

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

- A host short of memory can layer `docker-compose.lightweight.yml` LAST to run a stack without the
  observability (VictoriaLogs, Grafana) and admin (pgAdmin, Flower) tier, and with the four check
  containers profiled so a plain `up -d` cannot boot whole suites as background services (#1614). It
  changes nothing that already runs and nothing CI does: `docker compose run <service>` starts a named
  service regardless of its profile, so every command above is unaffected. Validate a combination
  before starting it with `python3 scripts/compose_profiles_smoke.py` (config only, starts nothing);
  `docs/source/development/compose-profiles.rst` is the service matrix and says what each tier is worth.

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

#### Resource ownership before starting another stack

The operator/external execution environment owns host/container resource limits,
admission and concurrency. Confirm that it can carry the selected workload before
starting Docker; full suites need more headroom than targeted checks. Account for
parent cgroup limits, other running jobs and disk, rather than host RAM alone.
If that environment has not admitted the work, do not start another stack.
MrMap provides no capacity or agent scheduling system. Keep each job's isolated
Compose state and ownership/cleanup rules above; do not change limits, interrupt
workers or remove another job's resources to make room.

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
- Changes under `scripts/` — for example the human decision protocol in `decisions` — are verified with
  `scripts/check_repo_tooling.sh`. It runs every suite of that tooling offline, in seconds, and is
  the same command CI runs in its own job: the QA container binds only `./backend`, so it cannot
  reach these files at all. Redirect its stdin (`scripts/check_repo_tooling.sh </dev/null`):
  `test_pr_classify.py` reads a PR history from standard input in one of its checks, and with stdin
  left open it blocks there forever — the harness prints the suites finished so far and then stalls,
  which reads as a hang rather than as a failure.
- Add or update tests when behavior changes.
- In a `check()`-based suite, a check must be able to *report* a failure: read what a check asserts
  through a lookup that yields a value on absence (`res.get("scope")`, a helper returning `None`
  rather than `findings[0]`), and pass the detail as a single operand (`"... %s" % (detail,)`).
  Indexing into the result directly makes the suite die on a `KeyError` or a `%` formatting error
  the moment the tool regresses, so the remaining checks never run and the regression reads as a
  crash instead of a failed check. Prove a new check is load-bearing by reverting the fix it covers
  and reading the failure list, not by asserting that it would fail.
- Do not modify tests merely to make an incorrect implementation pass.
- Report commands run, their results, and any check that could not be run.

### SonarCloud findings

Agent pre-push Sonar setup is documented in `docs/source/development/code-quality.rst` under
"Agent Sonar setup": the external launcher injects `SONAR_TOKEN`, and
`python3 scripts/git_checks.py install --sonar` enables the required static preflight. Credentials
stay in the process environment; the full CI coverage gate still applies.

SonarCloud scans the new code of a change and answers the pull request with its findings. Solve a
reported finding where it was reported: fix the flagged code or resolve the finding in the report.
Do not push new code around a finding to work around it — new code is scanned as new code too, the
finding stays open and the report ends up with more new issues than before.

A genuine false positive is the exception: a normative OGC/ISO/INSPIRE identifier that only looks
like an insecure URL or an IP address is suppressed with a `NOSONAR` comment carrying the reason on
the reported line, as `docs/source/development/code-quality.rst` describes. Rewriting the
identifier itself is not an option — it breaks document matching against upstream services.

## Git conventions

- Branch names are `<type>/<short-topic>`.
- `develop` is the default development and integration branch.
- `master` is reserved for stable releases.
- Base new branches and worktrees on current `origin/develop`.
- Use GitHub Flow: one small independently safe issue and PR, based on current
  `origin/develop`, with an explicit `--base develop`. Epics are native parent issues;
  a parent, title prefix or slug does not require an integration branch.
- Follow `docs/source/development/github-flow.rst` for the canonical workflow and
  `docs/source/development/github-flow-transition.rst` for the cutover inventory.
- Existing branch arrangements may finish only as explicit temporary exceptions agreed
  with their owners. Retargeting, branch deletion and live protection/access changes stay
  with people; preserve unique commits, reviews and active work.
- The mandatory epic branch contract and its automatic strict rollout were superseded
  by #1592; #1593 removes their tooling and redundant project synchronization. Native
  Projects and manual updates follow `docs/source/development/github-flow.rst`.
- Only the same repository's `develop` branch may target
  `master` in a pull request.
- Maintainer-directed synchronization from `master` back
  to `develop` is allowed.
- Use merge commits when synchronizing permanent branches.
- Never directly push to `master` or `develop`.
- Never delete, rename or force-push permanent branches.
- Never delete permanent branches during PR cleanup.
- Never force-push or rebase a branch open for review.
- Merge the integration target into a task branch only
  when needed to resolve conflicts or dependencies.
- Human approval and merge requirements remain mandatory.
- These rules also apply to agent skills and orchestration.
- Commit messages are short lowercase summaries. The *pull request title* is
  what carries the change class, and CI checks it: write
  `<type>[(<scope>)][!]: <summary>` there, with a type from
  `python3 scripts/pr_classify types`. A merge keeps only the title, so a class
  or a `!` written into a commit message never reaches `develop`
  (`docs/source/development/commit-classification.rst`).
- Keep unrelated formatting or refactoring out of a change; a pull request
  whose commits name a different class than its title is usually two changes.

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

### Assigning work

A person or external coordinator explicitly assigns one worker per issue. Before
starting, check native GitHub issue dependencies, assignees, linked branches and open
Draft PRs; skip work that is already assigned or actively developed, and ask the owners
on the issue when ownership conflicts. Assignees and dependencies are planning signals,
not atomic locks or automatic merge gates. Keep the single-worker model per issue.
Approval and pause labels (`agent: approved`, `agent: paused`) remain human-owned.

No claim board, eligibility checker, heartbeat comment or epic resolver exists or is
required; `docs/source/development/github-flow.rst` is canonical. The retired tools,
their claims and the Agent Work Board remain read-only history in git and in
`docs/source/development/github-flow-transition.rst`. Never take over another worker's
assignment and never interrupt another agent; reconciling stale work stays with people.

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
