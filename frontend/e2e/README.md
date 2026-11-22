# Browser acceptance harness (issue #1034)

Playwright acceptance tests for the **built SPA served by nginx** — the same
image the production compose files build (`docker/nginx/nginx.Dockerfile`),
never the Vite development server. This is the final browser gate of the
frontend-walk epic #948: #941 (deep links), #942 (asset 404), #943 (#1035
included — sort contract and Language list), #944 (`sort` in the schema),
#945 (filter labels), #946 (boot transfer and caching), #947 (GeoJSON map
states) and #1036 (`/csw-client` routing), with #1034 (PortalSearch) as its
subject.

The directory is deliberately outside the application: `frontend/package.json`
scripts, the `tsconfig.json` include (`src/`), the ESLint run (`./src`) and the
Vite build never touch it. It has its own pinned `package.json` (+ lock file)
and runs inside the `mcr.microsoft.com/playwright` image.

## 1. The stack

A job-local, isolated stack per `AGENTS.md` ("Docker ownership and cleanup for
parallel agents"), built from the revision under test:

```bash
cd <worktree-root>
export MRMAP_AGENT_PROJECT=mrmap-agent-<issue>-<run-id>       # e.g. mrmap-agent-1034-1119
export COMPOSE_PROJECT_NAME=$MRMAP_AGENT_PROJECT
export COMPOSE_FILE="docker-compose.yml:docker-compose.dev.yml:docker-compose.prebuilt.yml"
export MRMAP_BACKEND_DEV_FP=$(python3 scripts/dev_image_id.py --resolve --image backend --build)
export EXTERNAL_BASE_URL=localhost EXTERNAL_PORT=18085 EXTERNAL_SCHEME=http
export MRMAP_BUILD_REVISION=$(git rev-parse HEAD)             # stamped into the bundle (#1579)

docker compose up -d postgis redis mapserver backend
docker compose up -d frontend        # builds the nginx image: npm install + vite build
```

`EXTERNAL_*` is what the bundle is built against and what the `frontend`
service publishes — port 18085 here, so the browser and the API share one
origin behind nginx. Pick a free host port if 18085 is taken. The backend
runs the dev overlay (`DJANGO_DEBUG=1`) of the standard development stack;
the acceptance surface is the nginx edge and the built bundle, identical to
production for everything this suite measures (compression, routing, cache,
assets, SPA behaviour).

## 2. The fixtures

```bash
docker compose run --rm --no-deps -T backend \
  python manage.py shell -c "$(cat frontend/e2e/acceptance_seed.py)"
```

The seed flushes the disposable acceptance database and loads the
repository's own behave fixtures (`test_users`, `test_keywords`, `test_crs`,
`test_csw`, `test_wms`, `test_datasetmetadata`), so the browser gate sees the
same deterministic rows the Gherkin suite pins by PK. It then creates the
login user `acceptance` (password `Acceptance-e2e` — a fixture-only local
credential, a superuser, which sees every seeded record through the audited
break-glass of decision Q6=A), points WMS1 at the compose mapserver (real
GetMap answers) and gives the dataset records the three geometry shapes of
#947: a valid polygon, an EMPTY MultiPolygon and no geometry at all. The PKs
and titles the specs assert are in `helpers/fixtures.ts`.

## 3. The run

```bash
docker run --rm --network host --ipc=host \
  -v "$PWD/frontend/e2e:/e2e" -w /e2e \
  -v mrmap-e2e-node-modules:/e2e/node_modules \
  -e E2E_BASE_URL=http://localhost:18085 \
  mcr.microsoft.com/playwright:v1.65.1-jammy \
  bash -lc 'npm ci --no-audit --no-fund && npx playwright test'
```

`--network host` reaches the published `frontend` port from the agent host's
network namespace; the browsers live in the image (`PLAYWRIGHT_BROWSERS_PATH`
is baked in), the test package is pinned to `@playwright/test` 1.65.1 matching
the image. Artifacts land in `.output/` (gitignored): `results.json`, traces
and screenshots of failures, and `boot-metrics.json` — the measured #946
numbers (transferred vs decoded bytes per large payload).

Environment caveats recorded at the first full green run (2026-11-19,
develop e68310921): the page's `index.html` also references two leaflet
scripts from the unpkg CDN — the harness needs outbound network, and tile
requests to openstreetmap.org shape the map's backdrop but no assertion
depends on them. The numbers of #946 are only comparable within this stack —
the issue's rule against comparing unlike environments applies.

## 4. The Gherkin layer (issue #1689)

`playwright-bdd` 9.2.1 compiles `features/*.feature` into `.features-gen/`
(gitignored) and the result runs as the `bdd` **project of this same config** —
one runner, one login state, one artifact directory for both layers. It is not
a second runtime: no Vite server, no second browser, no second stack.

```bash
# one command for everything: generated scenarios + the plain specs of #1034
bash -lc 'npm ci --no-audit --no-fund && npm test'

# the Gherkin layer alone, and the tiers of it
npm run bdd:gen            # compile only — fails on an undefined step
npm run bdd:smoke          # the @smoke tier, i.e. everything but the canary
npm run bdd:test           # every scenario including the canary
npm run bdd:demonstrate    # the canary alone: must exit nonzero (#1689 AC)
npm run bdd:steps          # the step grammar as documentation
```

`npm test` excludes `@intentional-failure`: that scenario asserts text the
application never renders, which is the proof that a red scenario fails the run
loudly and leaves a trace. It is opt-in by name, never part of a green tier.

Where to put a scenario, and what a step may say, is specified by #1688 (step
grammar) and #1687 (waiting and assertion invariants): a step is one of
`Given/When/Then` of the grammar, all UI knowledge lives in
`support/adapters/`, and no step waits on a timeout or a CSS selector.
