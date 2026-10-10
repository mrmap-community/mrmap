# Backend tests

Django test suites. Commands and timings are in `../AGENTS.md`; this file covers how the tests are
written.

## Layout and naming

- `tests/django/` mirrors the app layout: `tests/django/registry/` for `registry/`, etc.
- Modules are named `tests_*.py` below `tests/django/registry/` and `test_*.py` below
  `tests/django/notify/` and `tests/django/system/`. Follow the folder you edit, otherwise the
  runner will not discover the file.
- Behave scenarios (Gherkin) live in `tests/behave/features/`; most paths contain a colon
  (`features/json:api/...`), so quote them on the command line. The run commands, the step
  vocabulary and the green baseline of that suite are in `tests/behave/AGENTS.md`.

## Data

- Fixtures are JSON files resolved through the app's `fixtures/` directories, listed per test class
  in `fixtures = [...]`. Keep the list minimal and include everything the tested model requires: a
  missing value for a required field makes `setUpClass` fail, which hides every test of that class.
- Prefer `TransactionTestCase` only when real commits are required (Celery task bodies,
  `on_commit` callbacks, database functions). It truncates all tables, which is slow and removes
  rows that `post_migrate` created — see the anonymous user note below.
- Use `self.captureOnCommitCallbacks(execute=True)` to assert work that is registered with
  `transaction.on_commit`, as the update job and harvesting tests do.

## Requests against the API

Two styles exist; pick the one matching the neighbor tests:

- `rest_framework.test.APIClient` goes through the full stack (URL routing, content negotiation,
  permissions). Post JSON:API bodies with `format="vnd.api+json"`; that is also what
  `REST_FRAMEWORK["TEST_REQUEST_DEFAULT_FORMAT"]` uses for `APIClient` requests.
- `rest_framework.test.APIRequestFactory` builds a request and calls the view directly, skipping
  middleware and content negotiation.

Content negotiation bites in tests: `DEFAULT_RENDERER_CLASSES` starts with
`extras.utils.BrowsableAPIRendererWithoutForms`, so a request without an `Accept` header is answered
with **HTML**, and `response.json()` fails on it. Assert JSON:API payloads with
`HTTP_ACCEPT="application/vnd.api+json"`.

## Permissions and the anonymous user

django-guardian maps an `AnonymousUser` request to the database user named `AnonymousUser`
(`registry/managers/security.py`, `registry/proxy/mixins.py` and the proxy permission classes query
it by username). Guardian creates that row on `post_migrate`, but a `TransactionTestCase` running
earlier in the same process flushes all tables and the deferred `post_migrate` of that flush never
fires. Tests that assert anonymous access therefore create it themselves:

```python
get_user_model().objects.get_or_create(username="AnonymousUser")
```

Without that row, a permission check fails with `accounts.models.users.User.DoesNotExist` instead of
returning 403, and the failure only appears in full-suite runs.

## External systems

Tests run without network access. Patch the HTTP layer of the module under test instead of calling
out, for example `patch("system.status.requests.Session")` or
`patch("registry.tasks.harvest.run_harvesting.apply_async")` for Celery hand-off.

## Rules

- Do not add a migration or edit an existing one to make a test pass; CI fails on model and
  migration drift in both directions.
- When a test fails because production code never populated a field, fix the production path and add
  a regression test; `tests/django/registry/tests_harvest_history.py` and
  `tests/django/registry/models/tests_update.py` are examples of that pattern.
- Full-suite runs must not overlap with any other `django-tests` container (shared `test_mrmap`
  database).