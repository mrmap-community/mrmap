---
name: MrMap Testing
description: "Writing or debugging MrMap tests — Django unit tests (tests/django), Behave Gherkin acceptance scenarios (tests/behave), Vitest frontend specs, fixtures, query-count assertions, test isolation/stack ownership, or coverage gates."
---

# MrMap Testing

Task skill for the three test suites. The nearest `AGENTS.md` wins; the authorities are
`backend/tests/AGENTS.md` (unit tests), `backend/tests/behave/AGENTS.md` (scenarios, run tiers,
step vocabulary, fixture tags, green baseline) and `frontend/AGENTS.md` +
`frontend/src/components/AGENTS.md` (specs). This skill routes into them and keeps the sharp edges
visible.

## Activation

Load when the task adds or debugs any test: `backend/tests/django/`, `backend/tests/behave/`,
`frontend/**/*.spec.ts(x)`, fixtures under `*/fixtures/`, or a failing CI test job.

## Mandatory project rules (sources named)

- Never modify a test merely to make an incorrect implementation pass; a test that fails because
  production never populated a field means fixing the production path plus a regression test
  (root `AGENTS.md`, `backend/tests/AGENTS.md`).
- Naming decides discovery: `tests_*.py` under `tests/django/registry/`, `test_*.py` under
  `tests/django/notify/` and `tests/django/system/` — follow the folder you edit
  (`backend/tests/AGENTS.md`).
- No network in tests; patch the HTTP layer of the module under test (`patch("…requests.Session")`)
  and the Celery hand-off (`patch("<task module>.apply_async")`, `celery.canvas.chord/Signature`)
  — examples in `backend/tests/AGENTS.md` and `tests/django/registry/tasks/tests_harvesting.py`.
- Behave runs with `--simple` (fixture strategy), `--keepdb` for the red/green loop, quoted paths
  (`json:api/` colon); tiers T0–T3 and every caveat in `backend/tests/behave/AGENTS.md`. The suite
  is green — a red T3 belongs to your change.
- Never "repair" a red scenario by deleting an assertion or widening the default `Accept` header;
  a `406` names a real endpoint/scenario disagreement (`backend/tests/behave/AGENTS.md`).
- Every new feature file carries `@fixtures:<file>.json` tags (dependency order!) or
  `@no_fixtures` — `before_feature` refuses anything else.
- One `django-tests`/`behave` run per Compose stack (shared `test_mrmap` database); each job in its
  own stack per root `AGENTS.md` "Docker ownership"; `scripts/agent_capacity` before starting a
  stack, `--need suite` before the full unit suite.

## Recommended patterns (project code, mirror these)

- Unit: `django.test.TestCase` + class `fixtures = [...]`; `APIRequestFactory` for direct viewset
  calls, `APIClient` with `format="vnd.api+json"` / `HTTP_ACCEPT="application/vnd.api+json"` for
  full-stack requests; `XpathTestCase` from `tests/django/contrib.py` for XML;
  `self.captureOnCommitCallbacks(execute=True)` for on-commit work; `TransactionTestCase` only for
  real commits (and then ensure the `AnonymousUser` row exists).
- Behave: write the scenario red first (T0 shows undefined steps), placement mirrors the API path,
  `Feature:` title = `<Resource> <Verb> Endpoint`; assert count/first-id for filters/sorts, denial
  reason codes for 4xx; reuse the step vocabulary — `grep steps/` before adding a step
  (`backend/tests/behave/AGENTS.md`).
- Query performance: extend `tests/django/registry/tests_query_performance.py`
  (`assertQueriesIndependentOfRows`, `assertIncludeAddsAtMost`, `assertNoSlowObjectPermissions`)
  rather than inventing absolute query budgets.
- Frontend: Vitest specs colocated, mocking the react-admin surface as the existing specs do
  (`frontend/src/components/AGENTS.md`); run targeted (`npx vitest --run <path>`) while iterating.

## Anti-patterns

- Guessing pks/uuids — take values from the fixture the feature already loads; grep fixtures
  before editing shared ones (`backend/tests/behave/AGENTS.md`).
- Scenarios that depend on execution order or on rows a previous scenario left behind.
- `@skip` without a tracked reason; renaming existing steps that other features share.
- Dotfile spec named `.spec.ts`; `node:test` imports in Vitest specs (`frontend/AGENTS.md`).
- Running the full suite for a one-file change — scope while iterating, broaden per risk
  (`definition_of_done`).

## Framework references (recommendations, not project rules)

- Django test tools: https://docs.djangoproject.com/en/stable/topics/testing/
- Behave/behave-django: https://behave.readthedocs.io/ — Vitest: https://vitest.dev/

## MCP dependencies

None. Tests run against their own `test_mrmap`, which no MCP points at; when a fixture's real
shape is unclear, read the fixture JSON or use `docker compose run --rm backend python manage.py
shell` inside the job's own stack. **Optional:** the read-only `postgres` server (repo
`opencode.json`, see `docs/development/mcp-servers.md`) reads the developer's *slot* DB — fine
for comparing against production-like rows while debugging, never a substitute for asserting
inside the test itself.

## Verification (the skill's deliverable is green checks)

1. Targeted run of exactly what you changed (Django label or behave file:line; vitest path).
2. Area tier before hand-back: behave T2 of the touched area, T3 (`run --rm behave`) for
   acceptance-visible work; frontend `lint` + `type-check` + specs (commands in
   `backend/AGENTS.md`, `frontend/AGENTS.md`).
3. Coverage rules: unit + acceptance `.coverage` combine from the same checkout, CI gate is 75%
   combined; frontend floors are rollout floors — never lower them to pass
   (`docs/source/development/code-quality.rst`).
4. Report commands run, exit codes, and anything not run (root `AGENTS.md` "Verification").

## Security constraints

- Test fixtures are shared and public: no real credentials, tokens or personal data in fixtures
  or scenario bodies; use `test_users.json` conventions (`User1`/`User2`).
- A test never weakens production guards to pass (permission checks, timeouts, parser hardening).

## Explicit exceptions

- `TransactionTestCase` is required (not an anti-pattern) for Celery bodies, `on_commit` and DB
  functions — with the `AnonymousUser` re-creation caveat.
- Scenarios asserting measured query counts exist (14 scenarios) — updating a measured number is
  allowed when the change genuinely shifts it, with the reason in the PR text
  (`backend/tests/behave/AGENTS.md`, "Green is not always asserted").
