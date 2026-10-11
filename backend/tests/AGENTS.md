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

## Query count assertions

`tests/django/registry/tests_query_performance.py` keeps the read endpoints from answering a list
with one query per row. It measures requests instead of calling a view:

```python
self.assertQueriesIndependentOfRows('/api/registry/wfs')
self.assertQueriesIndependentOfRows('/api/registry/wfs', **{'include': 'operationUrls'})
self.assertIncludeAddsAtMost(12, 'service', '/api/registry/layers')
self.assertNoSlowObjectPermissions('/api/registry/layers')
```

* `assertQueriesIndependentOfRows` compares the fixture answer with the same answer reduced to one
  row and attributes every query to the table its `FROM` clause names. A table that is joined into
  the answer stays at one query, a table that is queried per row grows with the rows, so the
  assertion does not need to know which table the endpoint answers. Pass `single={...}` where
  `filter[id]` does not reduce the answer: the historical endpoints answer a `history_id` as `id`
  but filter the id of the changed object, so they are reduced with `page[size]`.
* `assertIncludeAddsAtMost` measures the same endpoint with and without an `include` and only
  compares the two, so it does not depend on how many queries the endpoint costs on its own. Use it
  for an include that is known to be imperfect; its number carries a comment naming the relations
  that make up the cost, so it is known what to bring down once it is fixed.
  `assertQueriesDoNotExceed` is the same idea against a fixed number and is used where a request has
  no second request to compare with.
* `assertNoSlowObjectPermissions` asserts that no object of the answer logged the warning of
  `ObjectPermissionCheckerSerializer`, which is the fallback of a serializer that got no permission
  checker and determines the permissions of every object it serializes.
* How many rows an endpoint answers depends on what other tests did, which matters for the
  historical endpoints. An assertion that compares two requests of the same endpoint is stable, an
  absolute budget is not.
* `include` is only part of the answer; the links of a relation are serialized without it too.
  `select_related` on the queryset of the viewset and `prefetch_for_not_includes` narrow those
  queries, and the tests of an include are written twice - with and without the `include` - to keep
  both paths.
* Permission checks are shared per request: the viewset attaches its `ObjectPermissionChecker` to the
  request in `extras/viewsets.py`, and `ObjectPermissionCheckerSerializer` in `extras/serializers.py`
  reuses it, also for the serializers that the JSON:API renderer builds for `included` resources.
  Without that, every serialized object counts its own permission queries.
* A relation that is not included is answered as a related resource, so it only needs the id of the
  related object and, for a relation seen from the other side, the column that points back. That is
  what the entries of `prefetch_for_includes` and `prefetch_for_not_includes` limit themselves to,
  and the reason why a key of `prefetch_for_includes` may only prefetch the relation it is named
  after with all its fields. The tests therefore also assert the content of an included resource:
  its attributes and the ids of its own relations. A prefetch that is narrowed too far, or a second
  prefetch of the same relation name that overrides the wide one, fails there and not only in a
  query count.

## Rules

- Do not add a migration or edit an existing one to make a test pass; CI fails on model and
  migration drift in both directions.
- When a test fails because production code never populated a field, fix the production path and add
  a regression test; `tests/django/registry/tests_harvest_history.py` and
  `tests/django/registry/models/tests_update.py` are examples of that pattern.
- Full-suite runs must not overlap with any other `django-tests` container (shared `test_mrmap`
  database).