# Agent Skills (OpenCode)

Status: introduced 2026-11-16. Lives in `.opencode/skills/` (project scope) — automatically
discovered by OpenCode (V2) from the repository root; **no OpenCode configuration change and no
MCP change is required or made** for them. This file documents the skills, their activation, how
they fit the instruction hierarchy, and how to maintain them.

## Why skills exist

`AGENTS.md` files carry *always-applied* constraints and are read by every agent session. Skills
carry *task-specific* procedure: they are advertised to the model by their `description` only and
their body is loaded on demand (OpenCode's `skill` tool) when a task matches. That keeps prompts
light while making deep, verified guidance available exactly when relevant.

## Instruction hierarchy

| Layer | Carries | Files | Conflict rule |
| --- | --- | --- | --- |
| `AGENTS.md` (root + per-area) | Global constraints, mandatory architecture rules, security boundaries, environment/Docker ownership, git & claiming workflow | `AGENTS.md`, `backend/AGENTS.md`, `backend/registry/AGENTS.md`, `backend/tests/AGENTS.md`, `backend/tests/behave/AGENTS.md`, `frontend/AGENTS.md`, `frontend/src/components/AGENTS.md`, `frontend/src/jsonapi/AGENTS.md` | The `AGENTS.md` **nearest to the edited files wins** (declared in root `AGENTS.md`). |
| Skills (this dir) | Task-specific activation, patterns, anti-patterns, verification checklists — each one links to its sources instead of restating them | `.opencode/skills/<id>/SKILL.md` | Skills **never override** `AGENTS.md`; every skill states this and names its authoritative sources. A skill that contradicts `AGENTS.md` is a bug in the skill — fix the skill. |
| MCP servers | External capabilities only. The repo base config `opencode.json` (committed upstream via PR #1431, on `develop`) defines the doc servers (`django-docs`, `react-admin-docs`, `mui-docs`, `mui-x-docs`, GitMCP pinned to the exact framework versions), `orm-lens`, a `postgres` stub, `playwright` and a `sonarqube` stub; `docs/development/mcp-servers.md` is authoritative | repo `opencode.json` + per-checkout `.opencode/opencode.json` (mode 600, git-ignored, holds the read-only DSN); user `opencode.jsonc` (preserved unchanged) | Skills declare MCP dependencies explicitly; **all eight work without any MCP** and use the configured servers as optional accelerators. `postgres` is role-restricted read-only; `sonarqube` needs a human OAuth sign-in (`/mcps`). |
| CI | Deterministic enforcement: flake8/drift/translations, Behave, unit tests, frontend lint/type-check/coverage (combined backend gate 75%), CodeQL security-extended, SonarCloud | `.github/workflows/quality-assurance.yml`, `script-tests.yml`, `codeql.yml` | Skills tell the agent to run CI's commands locally (in a job-local stack); they add no new gates. |

Framework *recommendations* (Django/DRF/react-admin/Celery/lxml/OGC docs) are referenced inside
skills under "Framework references (recommendations, not project rules)" — they are never phrased
as mandatory project rules. Proposed directions that the project does not yet mandate are marked
as such (e.g. extending hardened lxml parsing in `mrmap-ogc`).

## Available skills

| ID | Purpose | Activates on (frontmatter `description`) | MCP deps (all optional) |
| --- | --- | --- | --- |
| `mrmap-django-orm` | Models, managers/QuerySets (`querys/`), expressions, simple-history, migrations, query performance | Backend database code, N+1/perf work on registry | `django-docs`, `orm-lens`, `postgres` |
| `mrmap-drf-jsonapi` | Viewsets, serializers, filtersets, nested routes, drf-spectacular schema, JSON:API contract preservation | API-layer files under `backend/`, schema-visible changes | `django-docs`, `postgres` |
| `mrmap-react-admin` | React 19 / react-admin v5 screens, schema-driven `jsonapi/` layer, reuse gate, i18n, Vitest | Anything under `frontend/src/` | `react-admin-docs`, `mui-docs`, `mui-x-docs`, `playwright` (visual checks only) |
| `mrmap-celery` | Tasks, queues (`celery_queues.py`), BackgroundProcess progress, beat/DB scheduler, on_commit enqueueing, WebSocket invalidations | `registry/tasks/`, `notify/`, celery settings, 202-style endpoints | `postgres` |
| `mrmap-ogc` | Capabilities/mappers per version, `ows_lib` rules, `/csw`, exception reports, untrusted XML, outbound-request hardening | OGC/ISO XML, WMS/WFS/CSW code paths, monitoring probes | none (no MCP covers OGC/ISO) |
| `mrmap-security` | Guardian object permissions, security proxy, auth (session/Basic/Knox/WS), secrets, SSRF/XML surfaces | Permissions, proxy, auth, credentials, outbound HTTP | `postgres` (introspection only), `sonarqube` (findings) |
| `mrmap-testing` | Unit-test conventions, Behave tiers T0–T3 & fixture tags, Vitest, query-count asserts, coverage gates | Adding/debugging any test, fixtures, red CI jobs | `postgres` (slot DB reads only) |
| `mrmap-github-workflow` | Claiming (`scripts/wip`), branches/worktrees, PR readiness (definition of done), `scripts/decisions`, human-only acts | Starting issue work, branch/PR steps, board/decision tooling | `sonarqube` (PR findings) |

Cross-references between skills exist (e.g. `mrmap-ogc` ↔ `mrmap-security`, `mrmap-testing` ←
area skills); OpenCode lists all skills each step, so agents can load several.

## How activation works (verified 2026-11-16, OpenCode 2.2.5)

1. OpenCode discovers `.opencode/skills/<id>/SKILL.md` per its documented project search
   (`https://opencode.ai/docs/skills/`); the skill **ID is the directory name**.
2. Each model step the model sees only `id + name + description` — so descriptions above name
   concrete paths/symptoms; that is the activation contract.
3. The agent (or an orchestrator's worker session) loads a skill by calling the `skill` tool with
   the exact ID; the user can force-load with `@mrmap-…`.
4. The body (minus frontmatter) plus the skill's base directory join the conversation; supporting
   files are read only if the skill references them (none currently ship extras).

All eight skills were validated end-to-end at introduction: discovery in the live session, load via
the `skill` tool, and a read-only fact-check of every referenced path/command against the checkout.

## Interaction with the external orchestrator (AO)

* Orchestration stays external to the repository (root `AGENTS.md`); skills add no scheduler, hook
  or watcher and change no claim/branch/PR behaviour.
* A worker session gets the skills automatically because they live in the checkout: discovery is
  from the project root, so any worktree of this repo exposes them.
* Skills are read-mostly guidance; they never authorize an action. The human-only acts
  (approve/merge/resolve/`agent: approved`) remain human-only regardless of which skills are loaded
  (`mrmap-github-workflow` encodes the deferral path).
* Capacity: skills point at `scripts/agent_capacity` before any stack; they add no new stack starts.

## Adding or changing a skill

1. Create `.opencode/skills/<kebab-id>/SKILL.md`; frontmatter: `name` (display) and
   `description` (when to use — this is the only text seen before loading; keep it factual and
   path-precise). No other config needed; reload-free discovery is automatic.
2. Keep the section shape used by all eight: Activation → Mandatory rules (sources named) →
   Recommended patterns → Anti-patterns → References → MCP dependencies → Verification → Security
   constraints → Explicit exceptions.
3. **Link, don't copy.** Facts that live in `AGENTS.md`/docs stay there; a skill quotes at most
   the sentence it enforces, with the source path beside it.
4. Distinguish explicitly: project rule (has a source file), framework recommendation (has an
   upstream URL), house direction/proposal (labelled as such). Never silently promote a
   recommendation into a rule.
5. Validate like this file's introduction did: (a) the skill appears in the model's skill list;
   (b) it loads via the `skill` tool; (c) run one representative read-only task following only the
   skill's instructions; (d) diff-check its claims against the code.

## Maintenance

* Re-validate the affected skill whenever a referenced `AGENTS.md` section, CI job, `scripts/`
  tool, or documented command changes; the skills name their sources precisely to make that grep
  possible: `grep -rn "AGENTS.md\|docs/" .opencode/skills/`.
* Keep descriptions honest: if a skill is never loaded, its description is wrong; if it loads when
  unwanted, its description is too broad.
* Skills must not start Docker stacks or touch credentials on their own — verification steps always
  route through the job-local-stack rules in root `AGENTS.md`.
* Remove skills that stop earning their keep (their guidance fully absorbed into `AGENTS.md` or
  dead code paths) rather than letting them drift; deleting a directory is the whole un-install.

## Known notes

* `CONTRIBUTING.md` says base work on `develop` while root `AGENTS.md` bases agent branches on
  `origin/master`; per the hierarchy the `AGENTS.md` wins for agent work. Skills follow `AGENTS.md`
  and do not restate `CONTRIBUTING.md` beyond the issue-first rule. (Pre-existing divergence, not
  introduced by the skills.)
* No framework-docs or database-inspection MCP was configured when the skills were introduced
  (2026-11-16). This changed on 2026-11-17: the project now commits an MCP base config
  (`opencode.json`, PR #1431 — currently on `develop`, not yet on `master`) plus
  `scripts/mcp-setup.sh` for the per-host read-only DB wiring; `docs/development/mcp-servers.md`
  documents it. The skills keep working **with or without** these servers — each one's
  "MCP dependencies" section is written so the server accelerates, never gates, the work.
* Wiring notes from 2026-11-17 (this rig): `scripts/mcp-setup.sh` currently fails on documented
  `.env` files (bug #1434), so the read-only role/forwarder were provisioned by its documented
  manual steps; the DSN lives in the git-ignored `.opencode/opencode.json` (mode 600) as
  `environment.DATABASE_URL` — the stub's `options.url` is inert for stdio servers — and the MCP
  `timeout` field is **milliseconds** (`15` times out instantly; use `15000`). `sonarqube` stays
  disabled until a person signs it in through `/mcps` (OAuth, never via a shell `opencode mcp
  auth`).
* Skill bodies duplicate a single title line for standalone readability; the loader adds its own
  heading — harmless, ~1 line per load.
