.. _test-memory:

==========================
Memory during test runs
==========================

The optional ``docker-compose.test-low-memory.yml`` layer limits Django and
Vitest to **one worker**. It is a test-only concurrency preset for constrained
hosts, independent of the deployment's ``MRMAP_LOW_MEMORY`` web/pool setting.
One comparison on a single host is recorded below; its results do not establish
a general saving across hosts. Normal CI retains Django's four workers and
Vitest's default worker policy.

Activation
==========

In an isolated job-owned Compose project prepared according to ``AGENTS.md``
(port/container-name resets, prebuilt dependency resolution and cleanup), append
this file after the existing layers::

    export COMPOSE_FILE="$COMPOSE_FILE:docker-compose.test-low-memory.yml"
    docker compose run --rm --no-deps django-tests
    docker compose run --rm --no-deps frontend-tests npm run test-coverage

The backend dependencies (``postgis redis mapserver``) must already be running
in that project. Frontend checks need no dependencies. Keep the frontend
container-name override when using its prebuilt image. Local builds, both
prebuilt layers and ``docker-compose.lightweight.yml`` compose with this preset;
``lightweight`` profiles services and does not select test concurrency.

All collected tests, coverage instrumentation, reporters and thresholds are
shared with the normal mode. Django still creates its own test database;
parallel overrides still use Django's separate per-worker clones. The named
``.coverage.unit`` data file, multiprocessing coverage and XML aggregation
remain in the same command. Behave retains its serial ``--simple`` runner,
fixtures and acceptance coverage. Never run two Django/Behave jobs against one
project's PostgreSQL.

For intermediate benchmark arms or an explicit override::

    docker compose run --rm --no-deps -e MRMAP_TEST_WORKERS=2 django-tests
    docker compose run --rm --no-deps -e MRMAP_TEST_WORKERS=2 frontend-tests npm run test-coverage

``MRMAP_TEST_WORKERS`` is a container environment variable; the preset supplies
it centrally to both services. ``run -e`` overrides it. Remove the preset to
restore the defaults (Django 4, Vitest automatic); a host shell variable alone
is not passed into the containers. Direct Vitest invocations can use
``MRMAP_TEST_WORKERS=1 npm run test-coverage`` inside their Node environment.
Vitest rejects empty, fractional, zero and invalid explicit limits. No pool,
heap, database, shared-memory or production settings change with this preset.
Serial tests may take substantially longer. This mode does not waive the
``scripts/agent_capacity`` admission decision, even on a 16-GiB host.

Allocation sources and limits of the evidence
============================================

The measured starting point is :ref:`runtime-memory-baselines` (#1613), not a
new measurement of this change. That full four-worker run attributed 2885 MiB
peak charge / 2854 MiB committed to the Django container, and 1595 MiB charge /
432 MiB committed to PostgreSQL. The test container's imports/private worker
allocations and PostgreSQL's page cache explain different parts of the peak.
The full stack reached 7350 MiB charge / 4973 MiB committed; those values must
not be added to an ancestor cgroup which already includes the same pages.

#1055's historical comparison found 225 s with four workers, 356 s with two
and 655 s serially. Its whole-cgroup peaks (12.1 GiB with four, 12.5 GiB
serially) do **not** establish a serial memory improvement. Preserve the
four-worker default until a comparable memory-and-runtime experiment justifies
changing it. Test-database creation and cloning are distinct startup phases;
the current evidence does not isolate their allocation peaks. PostGIS
extension/migration setup, shared buffers and connection pools are therefore
left intact rather than tuned speculatively.

Behave's current hooks use ``APIClient`` and rollback isolation, not Selenium
or WebDriver. Its ``shm_size: 2gb`` is a tmpfs capacity, not a 2-GiB physical
reservation. Reducing that cap alone would not demonstrate a RAM saving.
The separate Playwright harness already has ``workers: 1``, no video, and
failure-only traces/screenshots (``frontend/e2e/playwright.config.ts``).
There is no evidence here of leaked browser processes or fixtures; adding
cleanup/GC calls without measuring a leak would change lifecycle semantics
without an established benefit.

Vitest currently uses jsdom and Istanbul coverage. Its automatic worker count
can multiply independent transforms and jsdom/import allocations on larger
hosts. The preset only caps workers: isolation, worker pool, transform caching,
coverage of untested source and instrumentation remain shared. Switching pools,
reusing test environments or reducing coverage needs separate evidence.

Reproducible comparison
=======================

Use the existing ``scripts/stack_memory_profile`` sampler. Run baseline and
candidate revisions on the same host and dependency fingerprints with a fresh
isolated project per arm. Keep the fixture/test selection identical. Record
cold and warmed runs separately and repeat arms to expose cache/order effects.
Before starting dependencies, run ``scripts/agent_capacity --need suite`` for a
full Django arm (``--need stack`` for targeted/Behave/frontend). Stop if refused.
Register cleanup before creating resources, and verify exact project labels
and zero leftover containers, volumes and networks afterwards per ``AGENTS.md``.
Do not clear global caches or remove reusable images to manufacture a cold run.

Record the revision, image fingerprints, CPU model/core count (``lscpu``),
kernel (``uname -r``), RAM, cgroup hierarchy/limits, Compose layers and resolved
worker counts alongside the results. The sampler records revision, Docker
version, cgroup limit, per-container anonymous/file memory, RSS, CPU and OOM
deltas, and the sampler's own cgroup separately. Its ``peak_file`` is a
lifetime cgroup high-water mark; use fresh containers per arm and sampled phase
peaks for comparisons. Start sampling before ``up`` if measuring dependency
startup; otherwise label the phase as test/database setup with warm dependencies.

Once the isolated dependencies are prepared, a full test arm is::

    python3 scripts/stack_memory_profile sample \
      --project "$COMPOSE_PROJECT_NAME" --phase django-1 \
      --interval 0.25 --proc-interval 1 --out /tmp/test-memory.jsonl \
      --during 'docker compose run --rm --no-deps -e MRMAP_TEST_WORKERS=1 django-tests > /tmp/django-1.log 2>&1'
    python3 scripts/stack_memory_profile report --in /tmp/test-memory.jsonl

Repeat with 2 and 4, and the unchanged default on the baseline revision.
Also profile the documented targeted Django module, full Behave service,
frontend ``npm run test -- --run`` and ``npm run test-coverage`` separately,
with default and preset modes. Run lint/type checking separately from the
memory arms. Use the browser workload/ownership recipe in
``frontend/e2e/README.md`` when validating Playwright; do not start a browser
for the API-only Behave suite.

The sampler exits zero after recording even when the workload fails: require
``during_rc == 0``, nonempty container samples, no lost containers, and the
actual test summary and coverage artifacts before accepting a row. Preserve
logs, JSONL and coverage reports per arm before a later run overwrites them.
Record executed/skipped/failed test counts and all coverage metrics; no extra
skips are permitted. Verify combined Django/Behave coverage against the existing
75% gate and all four frontend thresholds from ``vite.config.mjs``. A successful
shell/config probe is not evidence that application coverage stayed complete.

The sampler's per-process RSS is diagnostic and can double-count shared pages;
do not sum it as private memory. Its container command probe can sample PSS
for one process, not the whole Django process tree. For PostgreSQL/Python PSS,
collect readable ``/proc/<pid>/smaps_rollup`` in the Docker host's PID namespace,
and mark it unavailable if permissions prevent that. Capture ``memory.stat``
``shmem`` and ``slab_reclaimable`` at the same sample instants when examining
shared memory and reclaimability: file charge includes shmem, so it is not all
reclaimable page cache. Never add shmem to file charge again. Capture parent
``memory.events`` before/after, since OOM deltas inside a test container alone
do not prove that its ancestor avoided OOM. Container-local and parent peaks
answer different questions and belong in separate report columns.

Verification status (2026-11-23)
==============================

On commit ``5cb425edf``, a host with an Intel i7-7700K (8 logical CPUs), Linux
``7.0.0-44-generic`` and Docker 29.4.3 ran each arm once in a fresh isolated
Compose project. The backend used the prebuilt dependency image fingerprint
``a6db4c98151b``; frontend dependencies used fingerprint ``4d6d32f5a3c8``.
Dependencies were running before sampling. Times include container startup and
test setup; frontend dependency installation was completed before sampling.
The stack peak is the highest sampled sum of container cgroup charges, in MiB;
it is not an independent measurement of private RAM or an ancestor peak.

====================  ============  ==============  =============
Workload              Workers       Stack peak MiB  Elapsed seconds
====================  ============  ==============  =============
Django with coverage  4 (default)              5113           1285
Django with coverage  1                       2361           2859
Vitest with coverage  automatic               2802            153
Vitest with coverage  1                        930            485
Behave with coverage  serial                   723            176
====================  ============  ==============  =============

Both Django arms passed 3245 tests with the same 3 skips; each reported 92.28%
line and 81.25% branch coverage. Both Vitest arms passed 1794 tests in 217 files;
each reported 85.18% lines, 83.68% statements, 80.29% functions and 75.31%
branches. Behave passed 715 scenarios and 4779 steps; combined Django and
Behave coverage passed the 75% gate at 90%. The clean backend pre-submit check,
frontend lint and type checking also passed. Docker projects were removed after
their arms. A first Django run against the developer checkout passed its tests
but failed XML generation on stale coverage data; it is excluded from the table.

These are single runs, not repeated cold and warm comparisons. They show a
lower sampled container charge and longer elapsed time on this host; they do
not establish a general performance claim. The default and preset use the same
revision and normal defaults, rather than a separate baseline checkout.
The targeted Django module was not profiled separately.
The first Playwright setup raced fixture seeding with backend migrations and
failed when ``created_at`` already existed; a later attempt also exposed an
API-readiness race. After waiting for backend startup and confirming its session
endpoint before opening the SPA, all 28 Playwright acceptance tests passed in
1.5 minutes. This is functional browser verification, not a Playwright memory
profile. The owned Compose project was removed. Repeated arms, a Playwright
memory profile, PSS and a separate parent OOM audit remain unmeasured.

``python3 scripts/test_test_memory_mode.py`` checks all eight combinations of
prebuilt-backend/prebuilt-frontend/lightweight layers, and exercises the shipped
Django shell command with a recording stub (default/1/2/4 workers, test failures
and XML failures). ``frontend/vite.config.spec.mjs`` pins the worker policy.
``scripts/test_coverage_parallel_data.py`` separately checks real forked-worker
coverage. These checks do not replace the blocked workload comparisons.
