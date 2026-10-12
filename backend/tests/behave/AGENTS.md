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
| `steps/periodic_updates.py` | periodic WFS/CSW job creation and unfinished-job reuse assertions |
| `steps/automatic_updates.py` | WMS/WFS additions, removals and reviewed identifier renames |
| `steps/statistical.py` | Service-specific feature type history for daily statistics assertions |
| `environment.py` | fixture loading from the `@fixtures:` tags of a feature (`before_all`, `before_feature`), a fresh API client per scenario (`before_scenario`), failure dump (`after_step`) |
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
- **A kept database also accumulates rows.** `loaddata` only writes the fields a fixture names, so a
  value a fixture dropped stays in the table, and `before_all` creates its users again on every run,
  which pushes the integer pks forward. A scenario that addresses a fixed pk — the `Organization` `1`
  in `add_webmapservices.feature` — can then fail with `Invalid pk "1" - object does not exist`
  although nothing is broken. Recreate the database instead of arguing with it; a `--simple` run never
  creates one, so do it in two steps:

  ```bash
  docker compose -f docker-compose.yml -f docker-compose.dev.yml run --rm -e SQL_DATABASE=postgres behave /bin/sh -c \
    "python -c \"import os,psycopg; psycopg.connect(host=os.environ['SQL_HOST'],user=os.environ['SQL_USER'],password=os.environ['SQL_PASSWORD'],dbname='postgres',autocommit=True).execute('DROP DATABASE IF EXISTS test_mrmap WITH (FORCE)')\""
  docker compose -f docker-compose.yml -f docker-compose.dev.yml run --rm -e SQL_DATABASE=mrmap behave /bin/sh -c \
    "python manage.py shell -c \"from django.test.utils import setup_databases; setup_databases(verbosity=0, interactive=False)\""
  ```

  The T3 command has no `--keepdb` and destroys the test database itself, which is why CI can not see
  any of this.
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
| features (48) | 46 | 0 | 0 | 2 |
| scenarios | 302 | 0 | 0 | 10 |

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
5. `Background:` holds the endpoint, the `HTTP_ACCEPT` header of an endpoint that does not serve
   JSON:API (see "The suite is green"), the content type and the payload template of the endpoints
   that take one, plus the login or the mock that *every* scenario in the file needs
   (`logout.feature`, `add_webmapservices.feature`). Nothing else: request parameters that carry the
   behaviour belong to the scenario, because a `filter[...]` in a `Background` hides what the
   assertions are counting. Login stays in the scenario whenever "anonymous" is the behaviour under
   test.
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

9. A denial asserts *why* it was denied, not only the status code. A JSON:API endpoint answers a 4xx
   with `{"errors": [{"detail": ..., "status": "403", "code": ...}]}` — there is no `title` — so the
   status step is followed by the code that names the reason:

   ```gherkin
   Scenario: Can't delete as anonymous user
       Given I am an anonymous user
       When I send the request with DELETE method
       Then I expect the response status is 403
       Then I expect that response json has an attribute "errors.[0].code" with value "not_authenticated"
   ```

   `not_authenticated` is a client that never identified itself, `permission_denied` a client that may
   not do this, `not_found` a resource that is gone. Naming the actor with `I am an anonymous user`,
   instead of leaving the login out, is what lets a table column carry it. `auth/login`, `auth/logout`
   and `/api/schema` answer plain `application/json` (see "The suite is green"), so they have no
   `errors` array. A scenario that deletes something reads the resource back afterwards, so that its
   204 is followed by a 404.

## Scenario outlines

An endpoint is usually probed with the same steps once per search, filter or include parameter. Those
families are `Scenario Outline`s with one `Examples` table, so covering a new parameter means adding a
row:

```gherkin
Scenario Outline: Can <action>
    Given I set a queryparam "<param>" with value "<value>"
    When I send the request with GET method
    Then I expect the response status is 200
    Then I expect that response json has an attribute "meta.pagination.count" with value "<count>"

    Examples:
        | action          | param                   | value | count |
        | search by title | filter[search]          | WMS1  | 1     |
        | filter by title | filter[title.icontains] | WMS1  | 1     |
```

- Name the columns after what varies and put the readable case name into the first one: behave
  substitutes `<action>` when it prints `Scenario Outline: Can search by title -- @1.1`, so the report
  stays as readable as the files that had one scenario per row.
- One row is one scenario, run with all `Background` steps. **An outline saves no runtime and no HTTP
  calls**, it only removes the duplicated text. `feature.feature:12` still addresses a single row, and
  every row inserted above it shifts that line number.
- Fold only scenarios that are the same behaviour over different inputs. A scenario that asserts more
  than the outline does — a query count, a second attribute, an attribute path that differs per case —
  stays on its own, because a table column can not make a step optional. The same holds when similar
  shapes carry different meanings, such as a group filter and a user filter that keeps shared rules.
- A request payload can not become a column, since it is a docstring and a cell is one line. Keep the
  payload the scenarios share in the `Background` and let the scenarios that deviate set their own.
- Keep a value out of the table when it is wider than the table is long — the GeoJSON polygon of a
  `filter[bboxLatLon.contains]` — and leave that scenario on its own, with a comment saying why.

## Filter and sort scenarios

A list endpoint with a filterset advertises dozens of `filter[...]` parameters, and the schema
documents fewer `sort` fields than the endpoint accepts. One scenario per parameter would be hundreds
of scenarios that all run the same code, so the suite covers **one row per filter class and per
hand written method**, not one row per parameter:

| Code path | Covered in | Measured detail |
| --- | --- | --- |
| auto generated `exact`, `contains`, `icontains`, `in` | `registry/service/wms/list_webmapservices.feature`, `notify/backgroundprocess/list_backgroundprocesses.feature` | `contains` is case sensitive and `icontains` is not, which is why both are listed next to each other |
| typed filters (`CharFilter`, `NumberFilter`, `BooleanFilter`, `UUIDFilter`, `DateTimeFilter` with `gte` / `lte` / `range`) | `registry/service/wms/list_webmapservices.feature`, `registry/service/wms/list_historical_webmapservices.feature`, `registry/harvesting/list_harvestingjobs.feature` | `filter[historyDate.range]` takes two ISO 8601 values separated by a comma |
| collection filters (`NumberInFilter`, `UUIDInFilter`) | `registry/security/list_related_allowedwebmapserviceoperations.feature`, `registry/harvesting/list_harvestingjobs.feature` | the allowed-operations filterset declares its lookups inside the field name (`filter[id.in]`), the others as lookups of a parameter |
| GIS lookups `contains`, `covers`, `intersects`, `equals` | `registry/service/wms/layer/list_layers.feature`, `registry/service/wms/list_webmapservices.feature` | one whole-world polygon and one small rectangle is what separates the four; the counts differ per lookup |
| choice and relation filters | `registry/security/list_related_allowedwebmapserviceoperations.feature`, `notify/backgroundprocess/list_backgroundprocesses.feature` | a filter whose model field has choices answers `invalid_choice`, not an empty list |
| hand written `method=` filters | `registry/service/wms/list_historical_webmapservices.feature` (`delta`, `delta_size__gt`, `changed_or_created`, `changed_or_deleted`), `registry/harvesting/list_harvestingjobs.feature` (`is_unready`), `registry/security/list_related_allowedwebmapserviceoperations.feature` (`access_group`, `access_user`) | these carry logic of their own, so each gets its own scenario and asserts a count instead of a `200` |
| `sort` | `registry/security/list_webmapserviceoperations.feature`, `registry/security/list_related_allowedwebmapserviceoperations.feature`, `registry/service/wms/list_historical_webmapservices.feature`, `registry/service/wms/layer/list_layers.feature`, `registry/harvesting/list_harvestingjobs.feature`, `registry/metadata/list_datasetmetadata.feature`, `notify/backgroundprocess/list_backgroundprocesses.feature` | asserts `data.[0].id`, so the order and not only the answer, plus one scenario with a field that does not exist |

Three rules make such a table worth having:

- Assert the **count or the first id**. A filter that is wired to the wrong column answers `200` with
  everything, and a sort that is ignored answers `200` in table order. `meta.pagination.count == 2`
  on a list of two rows says nothing about the order the scenario claims to test.
- Take every value from the fixture the feature already loads. A made-up uuid asserts that the lookup
  returns nothing, which is exactly what a broken lookup returns.
- Sort scenarios follow a caller. `grep -rn "sort=" ../../../frontend/src` is the short list of fields
  that have to keep working; do not add a scenario for a column nobody orders by.

A rejected parameter belongs to the contract, so an endpoint that got a new filter also gets one
scenario that asks for a parameter which does not exist. The code names where the value failed:

| Value refused | `errors.[0].code` | Example |
| --- | --- | --- |
| a `filter[...]` or `sort` that was never configured | `invalid` | `filter[not_a_field]`, `sort=not_a_field` |
| a value outside the choices of the field | `invalid_choice` | `filter[processType]` with free text |
| anything but a complete uuid for a uuid filter | `invalid` | `filter[id.contains]` with eight hex digits — the uuid validator runs before the lookup, so a uuid filter can not search *inside* a uuid |

**A generated test over the whole schema was tried and dropped.** Looping the parameters of
`/api/schema` through one scenario can only assert "answered", which is the one thing a filter
scenario must not assert, and it turns every schema edit into a red suite without naming a behaviour.

Two gaps are worth knowing before reading too much into a green list scenario:

- `sort` is validated against `ordering_fields`, and where a viewset does not set it, the accepted set
  is broader than the `sort` enum of the schema — the same field can be sortable on one endpoint and
  refused on the next (`wms-operations` and `wfs-operations` differ in their sort surface).
- Two number filters that look the same are not: `contains` on a generated filterset falls back to a
  char filter and compares the integer primary key as text, so `filter[id.contains]` with `2` finds the
  second harvesting job. The allowed operations declare `id__contains` by hand as a `NumberInFilter`,
  which parses the value into a list, and there the same parameter answers with nothing. Both are
  asserted with their measured count, because a schema reader can not tell the two apart.

- A declared filter can break the endpoint instead of refusing the value.
  `registry/filters/security.py` declares `id__exact` of the allowed operations as a `NumberInFilter`
  with `lookup_expr="exact"`, so the list it produces reaches a lookup that expects one number and
  `filter[id.exact]` answers `500` with `TypeError: int() argument must be ... not 'list'`. The scenario
  that would cover it is written out as a comment in
  `features/json:api/registry/security/list_related_allowedwebmapserviceoperations.feature`; assert it
  as a `200` together with the fix, never as a `500`.

Diagnosing a red filter scenario needs `--no-capture -f plain`: behave re-formats the log records it
captured for the scenario it is about to report, and formatting one of mrmap's records raises
`TypeError: not all arguments converted during string formatting` inside behave, which stops the run
before the failing assertion is ever printed.

## Step vocabulary

Search before adding a step: `grep -rn "<wording>" steps/`. Reuse beats invention, and a step that
reads like the existing ones is what keeps the scenarios reviewable.

| Vocabulary (`steps/steps.py`) | Steps |
| --- | --- |
| request target | `I use the endpoint {url}`, `I set the content type of the request to {content_type}`, `I set the request payload to:`, `I set a queryparam "{param}" with value "{value}"`, `I set the header "{name}" with value "{value}"`, `I set the cookie "{name}" with value "{value}"` |
| authentication | `I am logged in as {user} with password {password}`, `I am an anonymous user`, `I use token based authentication for user "{user}"`, `I use token authentication as {user}`, `I enforce csrf checks`, `I logout the current user` |
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
- A feature declares its data with one tag per file: `@fixtures:test_keywords.json
  @fixtures:test_wms.json`, in the order `loaddata` should read them — that order is what resolves
  foreign keys between fixture files, so copy it when a new feature needs the same set.
  `@no_fixtures` says the scenarios need nothing beyond those users. `before_feature` refuses a feature
  with neither tag, and one with both, so a feature can no longer run against an empty database and
  pass on `meta.pagination.count == 0` without testing anything. These tags replaced a mapping that
  picked the files out of the `Feature:` title; with that mapping gone, a title no longer has to stay
  unique for the suite to work.
- The tags were generated from what each feature actually loaded, which was not always what its title
  suggested: `mapcontextlayer/list_mapcontextlayers.feature` never matched the old mapping (its title
  reads `MapContexLayers`) and therefore still runs without `test_mapcontext.json`. Adding that fixture
  means re-measuring every count in that feature, so do it on its own.
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

Inside the endpoints that *do* have a list scenario, the open part is narrower and known (see "Filter
and sort scenarios"): no fixture row exists for an update job or a monitoring run, so the two sort
fields of the frontend that order those lists — `sort=doneAt` of `ServiceUpdateJobsCard` and
`sort=dateDone` of `MonitoringRunsCard` — are not asserted anywhere, and neither is
`sort=dateCreated` of `HarvestingActivityCard`, which would be unstable anyway because the loaded jobs
have no `date_created`. `periodic-harvesting-jobs` is ordered by id in the frontend and has no feature
at all. Adding one of them starts with a fixture, not with a scenario.

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
- Every new `Feature:` carries `@fixtures:` tags or `@no_fixtures`, its scenarios and outlines read as
  the rules above say, and no `@skip` was added without a tracked reason.


