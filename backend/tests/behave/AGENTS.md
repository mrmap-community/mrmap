# Backend Behave scenarios

Gherkin scenarios are the executable specification of the JSON:API and of the OGC endpoints.
`backend/AGENTS.md` says to treat them as authoritative descriptions of expected behaviour, so a
change to user visible behaviour starts here, not in the viewset.

Paths below are relative to `backend/tests/behave/`, commands run from the repository root.

## What lives where

| Path | Contents |
| --- | --- |
| `features/csw/`, `features/json:api/<area>/...` | the scenarios, one file per endpoint or workflow |
| `steps/steps.py` | the generic vocabulary: endpoint, payload, query params, headers, cookies, one step per HTTP method, status / JSON / XPath assertions |
| `steps/manual_updates.py` | the pattern for domain steps: state setup and state assertions of one workflow |
| `environment.py` | fixture loading (`before_all`, `before_feature`), a fresh API client per scenario (`before_scenario`), failure dump (`after_step`) |
| `../../../docker-compose.dev.yml` (`behave` service) | how the suite is executed, incl. the coverage wrapper |
| `../../../.github/workflows/quality-assurance.yml` (`acceptance-tests`) | the CI gate that runs all features except `@skip` and uploads `backend/acceptance-tests-coverage-report.xml`, which the service writes into its bind mount `/opt/mrmap` |

`behave-django` runs the scenarios through Django's test client inside a `TestCase` (`--simple`): no
browser, no live server, no Celery worker. A run migrates a `test_mrmap` database from the current
models unless `--keepdb` reuses it. There is no frontend and no HTTP server involved — the
`http://localhost:8000` prefix in a feature is just a path the test client strips.

## Running scenarios

Pick the cheapest tier that covers the change. Measured on this checkout: starting the container and
importing Django costs ~15 s in every tier, so T0 for the **whole** suite takes 21 s without ever
touching a database, a warm `--keepdb` scenario takes 23 s, a cold run that has to migrate
`test_mrmap` first takes 91 s, and the complete suite takes 3 min.

```bash
# T0 - wiring only: reports undefined or mismatching steps without running any scenario
docker compose -f docker-compose.yml -f docker-compose.dev.yml run --rm behave /bin/sh -c \
  "python manage.py behave --noinput --dry-run 'tests/behave/features/json:api/registry/service/wms/manual_update.feature'"

# T1 - a single scenario, the red/green loop
docker compose -f docker-compose.yml -f docker-compose.dev.yml run --rm behave /bin/sh -c \
  "python manage.py behave --simple --noinput --keepdb 'tests/behave/features/json:api/registry/service/wms/manual_update.feature:12'"

# T2 - one area
docker compose -f docker-compose.yml -f docker-compose.dev.yml run --rm behave /bin/sh -c \
  "python manage.py behave --simple --noinput --keepdb --no-skipped 'tests/behave/features/json:api/registry/service/wms'"

# T3 - what CI runs (default command of the service, coverage included)
docker compose -f docker-compose.yml -f docker-compose.dev.yml run --rm behave
```

Rules that these commands encode:

- **Quote the path.** Most features live below `features/json:api/`; the colon is parsed as
  `FILE:LINE` otherwise. `feature.feature:12` runs a single scenario and is the fastest loop.
- **One behave run at a time.** It uses the same `test_mrmap` database as a `django-tests`
  container; overlapping runs drop each other's tables and fail with unrelated errors.
- **`--keepdb` (`-k`) is Django's**, not behave's, and is the difference between minutes and seconds
  on a repeat run. Drop it after any model or migration change, or when a failure mentions the
  database schema — a kept database is not migrated.
- **`--dry-run` runs without a test database.** behave-django switches to
  `ExistingDatabaseTestRunner`, and behave skips all environment hooks during a dry run — that is why
  no fixture is loaded there. Keep every hook free of writes you would not want in the development
  database, because that is the database such a run is connected to. A dry run leaves every step
  `untested` and still reports one feature as `failed` although no step failed (its
  `Scenario Outline` is not expanded there) while exiting with 0 — read the exit code and the step
  counts, not the feature count.
- **Flags that clash with the Django management command are renamed.** `-c`, `-k`, `-r`, `-S`, `-v`,
  `--no-color`, `--runner`, `--simple` and `--version` must be passed to behave as `--behave-*`
  (see `behave_django/management/commands/behave.py`). `--tags`, `--name`, `--format`, `--outfile`,
  `--dry-run` and `--no-skipped` pass through unchanged.
- **Machine readable output**: add `--format=json --outfile=/tmp/behave.json --behave-no-color` to
  get a parseable result instead of ANSI coloured text. The exit code is the gate; `after_step`
  already prints the body of the response that failed.
- Only the `@skip` tag has a meaning in CI (`--tags=-skip`). Everything else is descriptive.
- `backend/behave.ini` holds the defaults: the feature path and `-@skip`. That is why
  `python manage.py behave --dry-run` needs no argument here. CI and the VS Code task pass their own
  options, and a command line option always wins over the config file.

## The suite is green

State of `tests/behave/features` on this checkout:

| | passed | failed | error | skipped |
| --- | --- | --- | --- | --- |
| features (47) | 45 | 0 | 0 | 2 |
| scenarios | 216 | 0 | 0 | 10 |

Behave **is** therefore a green/red gate: a red T3 run belongs to the change that made it red, and
`definition_of_done.rst` is answered by the four counts. The 10 skipped scenarios are the two `/csw`
features at the end of this file.

Two conventions keep it green, and the harness enforces both so that no scenario has to repeat them:

- **The send steps negotiate JSON.** `steps/steps.py` adds `HTTP_ACCEPT: application/vnd.api+json`
  to every request unless the scenario sets that header itself. Without it DRF answers with the
  browsable API renderer (`extras.utils.BrowsableAPIRendererWithoutForms` is first in
  `DEFAULT_RENDERER_CLASSES`) and `context.response.json()` raises
  `ValueError: Content-Type header is "text/html; charset=utf-8", not "application/json"`.
- **Endpoints that are not JSON:API say so.** `LoginView` and `LogoutView` set
  `renderer_classes = [JSONRenderer]` and the schema view answers with `application/json`, so
  `features/json:api/auth/*.feature` and `retreive_schema.feature` override the header in their
  `Background:`. A `406` in a new scenario means endpoint and scenario disagree about the media
  type: decide which one is wrong instead of silencing it.

Never "repair" a red scenario by deleting its assertion, and never widen the Accept default to make
a `406` disappear — it is the only thing that catches a view that stopped serving JSON:API.

`after_step` prints the failing step with its file and line, the status and the content type, the
response body, and for an HTML response the hint instead of the whole page — so a red run explains
itself without drowning the log.

### Why the CSW features stay skipped

`features/csw/get_capabilities.feature` and `features/csw/get_records.feature` are `@skip` because
the `/csw` endpoint answers every request that reaches them with a 500:

- A missing `SERVICE` or `REQUEST` parameter hits `csw/views.py:54` / `csw/views.py:56`, which build
  `MissingRequestParameterException` / `MissingServiceParameterException` without the
  `service_type` and `service_version` arguments `OGCServiceException` requires →
  `TypeError: OGCServiceException.__init__() missing 2 required positional arguments`. The proxy
  (`registry/proxy/mixins.py:57`) shows the calling convention that is expected here. Even with that
  fixed, the report body is built from `owsExceptionReport.xsd`, which yields an empty
  `<ows:ServiceExceptionReport/>` for `("csw", "Exception", "2.0.2")` instead of the OGC report the
  scenarios expect.
- Every `GetRecords` request — with or without filter — fails in
  `registry/ows_lib/csw/builder.py:208` with `TypeError: can only join an iterable` while the query
  is built from GET query parameters.

Both are production fixes in the OWS layer, not scenario fixes; the reason is also written above the
`@skip` tag in each file. Unskip them together with those fixes and expect the XML comparison of
`get_capabilities.feature` to need attention.

## Writing or changing a scenario

1. Look for a feature that already covers the behaviour — the file is named after the endpoint, so
   `grep -rn "<api path>" features/` answers it in one step.
2. Write or extend the scenario **before** the implementation, run T0 to see the undefined steps,
   then implement steps and production code until the scenario is green.
3. Placement mirrors the API path: `features/json:api/registry/<area>/<resource>/<verb>_<resource>.feature`.
   A workflow that crosses resources goes into the folder of the resource it is about.
4. The `Feature:` title is an identifier: `<Resource> <Verb> Endpoint`, unique across the suite
   (titles are used to pick fixtures, see below).
5. `Background:` holds only the endpoint, the content type and the payload template — plus the
   `HTTP_ACCEPT` header of an endpoint that does not serve JSON:API (see "The suite is green"). Login
   belongs to the scenario, because "anonymous" is often the behaviour under test.
6. One scenario per observable behaviour, named after the behaviour
   ("Anonymous users cannot queue updates"), not after the status code. Use `Scenario Outline` +
   `Examples` for permission or filter matrices instead of copy-paste scenarios.
7. Assert what carries the behaviour: the status code *and* the payload attribute, plus a domain
   `Then` if the promise is made in the database.
8. Scenarios must not depend on one another. Behave pushes a context layer per scenario, so
   everything a scenario or its `Background` puts on `context` is gone in the next one — but the
   fixtures are loaded **once per feature and are not restored**: setup that changes rows has to be
   reverted by its own domain step (`remove_update_settings` does that) instead of relying on
   scenario order. Features run in alphabetical path order; do not exploit it.

## Step vocabulary

Search before adding a step: `grep -rn "<wording>" steps/`. Reuse beats invention, and a step that
reads like the existing ones is what keeps the scenarios reviewable.

| Vocabulary (`steps/steps.py`) | Steps |
| --- | --- |
| request target | `I use the endpoint {url}`, `I set the content type of the request to {content_type}`, `I set the request payload to:`, `I set a queryparam "{param}" with value "{value}"`, `I set the header "{name}" with value "{value}"`, `I set the cookie "{name}" with value "{value}"` |
| authentication | `I am logged in as {user} with password {password}`, `I use token based authentication for user "{user}"`, `I use token authentication as {user}`, `I enforce csrf checks`, `I logout the current user` |
| execution | `I send the request with GET/POST/PATCH/DELETE method` |
| assertions | `I expect the response status is {status}`, `I expect that response json has an attribute "{path}"[ with value "{value}"]`, `I expect that there is a xpath "{xpath}"[ with value "{value}"]`, `I expect that response xml content is:`, `I expect that "{n}" queries where made` |
| mocking | `I mock the function "{func}" of the module "{module}" with return value as object` (stopped in `after_scenario`) |

- Add a **generic** step to `steps.py` only when it works without knowledge of a model.
- Add a **domain** step to `steps/<domain>.py`, one module per area mirroring the feature folder;
  `manual_updates.py` is the template: `Given` steps that create rows and permissions
  (`assign_perm`), `Then` steps that compare database state.
- Parse style is `{param}` or `"param"`; stack `@given`/`@then` decorators on one function when the
  same wording is both setup and assertion, as the existing steps do.
- Everything stored on `context` beyond the table above is domain state and belongs next to the
  domain step that reads it.

## Test data

- `before_all` loads `accounts/fixtures/test_users.json`: `User1` and `User2` (password equals the
  username) plus the groups `Group1`, `Group2` and `Default-Permissions`. The admin superuser and
  guardian's `AnonymousUser` row come from `post_migrate` while the test database is created; the
  credentials are `DJANGO_ADMIN_USER` / `DJANGO_ADMIN_PASSWORD` from `.env`, which is what the
  `Basic` header in `auth/login.feature` encodes.
- Feature fixtures live in `registry/fixtures/`, `notify/fixtures/` and `accounts/fixtures/`:
  `test_wms.json` (2 WMS, 9 layers, operation urls), `test_wfs.json` (2 WFS, 5 featuretypes),
  `test_csw.json` (3 CSW, 2 harvesting jobs), `test_mapcontext.json` (2 mapcontexts, 11 layers,
  group object permissions), `test_datasetmetadata.json` (plus the XML files under
  `tests/django/test_data/`), `test_keywords.json` (159 keywords), `test_crs.json`,
  `test_monitoring.json`, `test_allowed_wms_operation.json`, `test_allowed_wfs_operation.json` and
  `test_background.json`.
- A feature declares its data with tags: `@fixtures:test_keywords.json @fixtures:test_wms.json`.
  Without such a tag the legacy chain in `environment.py` derives the fixtures from the `Feature:`
  title, which is why titles have to stay unique. **New features always carry the tags**: matching
  nothing means the scenarios run against an empty database and can pass on
  `meta.pagination.count == 0` without testing anything.
- Fixture UUIDs are referenced by scenarios and by steps (the WMS
  `cd16cc1f-3abb-4625-bb96-fbe80dbe23e3` is also `SERVICE_ID` in `steps/manual_updates.py`), and some
  scenarios address integer pks such as `mapcontextlayers/9`. Changing a fixture therefore means
  grepping for the old value in `features/` and `steps/`.
- Fixture files reference each other by natural key, so list them in dependency order:
  `@fixtures:test_keywords.json` **before** `test_wms.json`, `test_wfs.json` or `test_csw.json`,
  which otherwise abort the feature with
  `DeserializationError: Keyword matching query does not exist`. The tags are loaded in the order
  they are written on the feature.
- These fixtures are shared with the Django unit tests: check `grep -rl <fixture-name> ../../django`
  before editing one.

## Green is not always asserted

- `I expect that "{n}" queries where made` counts the queries of the request performed by the last
  send step (`CaptureQueriesContext` in `steps/steps.py`); a scenario that never sent a request fails
  with `AttributeError: context.queries`. The count is everything the request touched: session and
  permission lookups, the queryset, the count for pagination and the `include`d relations. The
  numbers in the 14 scenarios that carry it were measured, not guessed — a jump is the endpoint
  having gained queries, so fix the endpoint or write down in the pull request why the extra query
  is justified.
- `... with value "false"` compares `str(bool(value))` with the expected word, so an assertion on a
  falsy value can fail. Everything else goes through `assertJSONEqual` first and a string comparison
  after it, so write the value the way the renderer prints it (`0`, `null`, `WebMapService`).
- JSON paths are dotted and index lists with `data.[0].id`; `_traverse_json` falls back to the
  response root when an intermediate value is falsy, so assert on leaf values.
- There is no Celery worker and no network in a scenario. Mock with the step above or create the
  state a task would have created; never wait for background work.
- `--use-existing-database` is not a shortcut: it points the run at the configured database, and the
  hooks then load their fixtures into it.

## Where scenarios are missing

Roughly two thirds of the route prefixes registered in `../../registry/urls.py` are not addressed by
any scenario. Nothing covers the WFS and CSW update jobs and settings, `layer-mappings` and
`featuretype-mappings`, the `*-proxy-settings` and `*-authentication` records, the monitoring probes,
probe results and `wms-monitoring-runs`, the harvesting sub-resources, `service-metadata`,
`metadata-contacts`, `mime-types`, `licences`, `referencesystems`, `historical-wfs`, `historical-csw`
and `historical-featuretypes`. `/csw` has no executed scenario at all, see "Why the CSW features stay
skipped" above.

To re-check that list without a database:

```bash
cd backend && python3 - <<'PY'
import glob, re
src = open('registry/urls.py').read()
segments = set(re.findall(r"register\(\s*[r]?['\"]([^'\"]+)['\"]", src))
features = ''.join(open(f).read() for f in
                   glob.glob('tests/behave/features/**/*.feature', recursive=True))
missing = sorted(s for s in segments if s.strip('/').split('/')[-1] not in features)
print(f'{len(segments) - len(missing)} of {len(segments)} registered route'
      ' segments appear in a feature')
print(', '.join(sorted(missing)))
PY
```

That heuristic counts a route as covered when a scenario names it; it is a starting point for
choosing work, not a coverage report.

## Definition of done for a scenario change

- The scenario was red before the production change and green after it, with the T1 command and its
  exit code in the report.
- The T2 run of the touched area and the T3 run were executed before the pull request; their counts
  are compared against the baseline above, as `definition_of_done.rst` asks for.
- New or changed steps went into the right module and the table in this file was updated.
- `../.venv/bin/flake8 tests/behave/environment.py tests/behave/steps/<module>.py` from `backend/`
  reports nothing new for the files you touched. CI excludes `tests/` from its tree-wide run, and
  `steps/steps.py` carries pre-existing `F811` findings from its `step_impl` naming — do not add to
  them, and do not rename them on the side.
- Every new `Feature:` has `@fixtures:` tags and a unique title, and no `@skip` was added without a
  tracked reason.


