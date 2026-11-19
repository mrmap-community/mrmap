---
name: MrMap Django ORM
description: "Working on MrMap backend database code — Django models, managers, QuerySets (registry/querys), ORM expressions, PostgreSQL/PostGIS queries, django-simple-history paths, or model/migration changes. Also use for query performance (N+1, select_related/prefetch, CTEs) on the registry app."
---

# MrMap Django ORM

Task skill for database-side work in `backend/`. It complements, never overrides: the `AGENTS.md`
nearest to the edited files wins (root, `backend/`, `backend/registry/`). Read `backend/AGENTS.md`
and `backend/registry/AGENTS.md` before writing new database code — they are the inventories of
what already exists.

## Activation

Load this skill when the task touches: `registry/models/`, `registry/managers/`,
`registry/querys/` (spelling is intentional), `registry/expressions/`, `extras/managers.py`,
`extras/models.py`, `backend/*/migrations/`, or a query-performance problem.

## Mandatory project rules (sources named)

- Business logic lives in model methods, QuerySets/managers and mappers — not in viewsets or
  serializers (`backend/AGENTS.md`, "Architecture").
- Reuse before inventing: look in `extras/managers.py` (`DefaultHistoryManager`, `with_history()`),
  `registry/querys/`, `registry/managers/` and `registry/expressions/` before writing a new
  selection path (`backend/registry/AGENTS.md`).
- django-simple-history is load-bearing: history must survive bulk writes and deletes — use
  `simple_history.utils.bulk_create_with_history` / `bulk_update_with_history`
  (used in `registry/mappers/persistence/handler.py`, `registry/models/update.py`), and inspect
  existing history managers/signals before touching those paths (`backend/AGENTS.md`).
- Migrations: only when the requested change alters the schema; never hand-edit or add one to make
  a test pass; CI fails on model/migration drift in both directions (`AGENTS.md` "Never do",
  `backend/tests/AGENTS.md`). Run `python3 scripts/migration_graph_smoke.py` before pushing a
  branch that adds a migration (root `AGENTS.md`).
- Reusable selection logic goes into existing querysets/managers, not into a view (`backend/AGENTS.md`).
- Lookup tables shared by imports are written with the `"get_or_create"` persistence mode
  (ordered `bulk_create` + `ignore_conflicts`); inserting them row-by-row deadlocks concurrent
  harvest workers (#817, `backend/registry/AGENTS.md`).

## Recommended patterns (project code, mirror these)

- QuerySets per aggregate in `registry/querys/`; one manager module per aggregate in
  `registry/managers/`; security-scoped selection through the security managers
  (`registry/managers/security.py` — see skill `mrmap-security`).
- Reusable SQL pieces as `django-cte` CTEs and `Func` expressions in `registry/expressions/`
  (`layer_ctes.py`, `search.py`, `durations.py`) instead of `raw()` SQL.
- Prefer DB-side annotation/filtering and existing `select_related`/`prefetch_related` helpers;
  keep querysets lazy (`backend/AGENTS.md`).
- Derived service state (alerts) is annotated in `registry/querys/alerts.py` — extend that
  derivation, never re-implement alert logic (`docs/architecture.md`, "Attention").

## Anti-patterns

- Python-side filtering/looping over querysets that the database can answer.
- Per-row queries in a loop where `prefetch_for_includes` / `prefetch_for_not_includes`
  (`extras/viewsets.py`) exist — read endpoints are guarded by
  `tests/django/registry/tests_query_performance.py`.
- Copying a manager/queryset into a feature to adjust one detail — extend it (`AGENTS.md` "Never do").
- Raw SQL string interpolation (CodeQL security-extended runs in CI).
- Reopening the migration-squash idea without meeting its stated threshold
  (root `AGENTS.md`, "Verification reality check").

## Framework references (recommendations, not project rules)

- Django QuerySet API: https://docs.djangoproject.com/en/stable/ref/models/querysets/
- django-simple-history: https://django-simple-history.readthedocs.io/
- django-cte: https://github.com/dimagi/django-cte — PostGIS: https://docs.djangoproject.com/en/stable/ref/contrib/gis/

## MCP dependencies

None required — every rule above is checkable with `makemigrations --check` and the test
containers. **Optional**, configured by the repo's committed `opencode.json`
(`docs/development/mcp-servers.md`) and skipped gracefully when absent:

- `django-docs` — GitMCP over `django/django` pinned to the running version; authoritative for
  framework behaviour questions instead of relying on training data.
- `orm-lens` — read-only static analysis of the checkout: `nplusone_scan` before claiming a
  query is N+1-free, `drift` as a second migration-drift opinion (CI's `makemigrations --check`
  stays the gate).
- `postgres` — read-only (`mcp_readonly` role) against the developer's running slot DB through a
  127.0.0.1-only forwarder; for schema introspection and quick read queries, never for writes or
  dumping user data.

## Verification (commands in `backend/AGENTS.md`, Docker rules in root `AGENTS.md`)

1. `../.venv/bin/flake8 <touched files>` from `backend/` (~1 s, same findings as CI).
2. Targeted Django tests in the job's own stack (`django-tests ... --keepdb`); drop `--keepdb`
   after model/migration changes.
3. If migrations changed: `pre-commit-check` (drift + translations) and
   `python3 scripts/migration_graph_smoke.py`.
4. If a read endpoint's query shape changed: run `tests/django/registry/tests_query_performance.py`.

## Security constraints

- Every model used through the API keeps its guardian object-permission path intact; never widen a
  manager queryset used by `security.prepare_with_security_info` (see skill `mrmap-security`).
- Never log or persist credentials/DB URLs; environment values come from `.env` — ask, don't invent.

## Explicit exceptions

- Adding a migration is legitimate only when the user requested a schema change or the accepted
  issue states one; otherwise explain the implication first (root `AGENTS.md`, "Working with
  uncertainty").
- `TransactionTestCase` is allowed (and sometimes required) for task bodies/`on_commit` — see
  skill `mrmap-testing`.
