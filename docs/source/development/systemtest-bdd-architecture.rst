.. _systemtest-bdd-architecture:

=====================================================
System testing architecture: the BDD contract (#1688)
=====================================================

.. sidebar:: Issue #1688

   Foundation issue of epic #1687 (Gherkin-based full-stack E2E system
   tests). This page is the RFC/ADR its sub-issues #1689 - #1702 build
   against: the boundaries of the four test classes, the layout of the
   browser BDD harness, its generic step grammar, scenario-state
   lifetimes, resource adapters, fixtures, tags, artifact redaction, CI
   tiers and anti-duplication. Where a later sub-issue needs to change
   this contract, its PR edits this page in the same change - not the
   other way round.

The page audits what already exists and fixes the contract around it. It
delivers no runner code; #1689 (the Playwright-BDD runner) is the first
consumer. Every count in "The existing baseline" was measured with the
command named next to it, at the base SHA of the PR that adds this page.

The four test classes and their boundaries
==========================================

Four kinds of automated checking exist or are planned. Each user-visible
promise has exactly one class that *asserts* it; the others may only
*exercise* it.

.. list-table::
   :header-rows: 1
   :widths: 20 27 30 23

   * - Class
     - Substrate
     - Binding question
     - Owner of the assertion
   * - API contract
     - ``backend/tests/behave`` - behave-django, in-process Django test
       client: no browser, no live server, no Celery worker
     - status codes, JSON:API shapes, filter/sort facets, OGC documents,
       database state after a request
     - Behave feature files (the authoritative spec per
       ``backend/AGENTS.md``)
   * - Browser BDD (this epic)
     - Playwright-BDD over the **built SPA behind nginx** - the same
       image the production compose files build, never the Vite dev
       server
     - what a user sees and can do end to end, including background jobs
       that finish out-of-process
     - Gherkin features under ``frontend/e2e/features`` (#1689)
   * - Performance / platform plain Playwright
     - plain ``*.spec.ts`` under ``frontend/e2e/specs``
     - measured or platform facts: transferred vs decoded bytes (#946),
       asset caching, deep-link boot, asset 404s
     - the existing specs (#948/#1034); they stay plain - a measured byte
       budget does not belong in a Gherkin step
   * - Exploratory live testing
     - the pinned Playwright MCP server (``opencode.json``,
       ``@playwright/mcp@0.0.85``); #1699 adds the recording workflow
       around it
     - "what happens when a human pokes this" - discovery, not assertion
     - recordings and notes; a finding becomes a *proposed* scenario
       (#1701), never an auto-merged test

Boundary rules that make the split real:

- A facet an API Behave scenario already pins (a ``filter[...]`` lookup,
  an error code) is not re-asserted per-row in the browser. The browser
  scenario asserts that the facet *renders, is selectable and its rows
  appear* - one scenario, not a matrix. The matrix stays Behave's job.
- Backend worker/OGC/Celery processing cannot run inside a Behave
  scenario (no worker, no network - ``backend/tests/behave/AGENTS.md``).
  Any promise ending "and then the background process finished" belongs
  to the browser class, where the worker really runs (#1696).
- Performance assertions never move into Gherkin. A step vocabulary that
  carries byte budgets stops being business-readable (#1687 invariant 1).
- Exploratory findings are inputs, never authority: an AI-generated step
  or assertion needs human review before merge (#1687 invariant 8).
- One behaviour, one owning scenario class. A PR that adds a browser
  scenario never deletes the Behave scenario behind it, and vice versa.

The existing baseline (audited, not estimated)
==============================================

Reproduce every row with its command from the repository root.

.. list-table::
   :header-rows: 1
   :widths: 24 46 30

   * - Surface
     - Measured state
     - Command shape
   * - Behave features
     - 97 ``.feature`` files, 439 scenario declarations, 94 of them
       ``Scenario Outline`` entries
     - count the feature files under ``backend/tests/behave/features``,
       then count the ``Scenario Outline:`` and ``Scenario:`` lines in
       them
   * - Behave step vocabulary
     - 116 step declarations across 18 modules; 21 of them the generic
       vocabulary of ``steps/steps.py`` (endpoint, payload, queryparam,
       header, cookie, one step per verb, status / JSON / XPath /
       query-count assertions, mocking)
     - ``grep -rc '@given' backend/tests/behave/steps`` and the same for
       ``@when`` and ``@then``
   * - Browser harness (#1034, epic #948)
     - 5 specs plus 1 auth setup project; 20 chromium test declarations,
       two of them loop-expanded (6 deep links, 3 geometry shapes);
       1 worker, 0 retries; trace and screenshot on failure, video off;
       JSON report and ``boot-metrics.json`` under ``.output/``
       (gitignored)
     - ``grep -rn '^  test(' frontend/e2e/specs/*.spec.ts``
   * - Seed
     - ``acceptance_seed.py`` flushes the disposable acceptance database
       and loads the behave fixtures (``test_users``, ``test_keywords``,
       ``test_crs``, ``test_csw``, ``test_wms``,
       ``test_datasetmetadata``) - the browser gate and the Behave suite
       speak about the same primary keys
     - ``head frontend/e2e/acceptance_seed.py``
   * - CI
     - no e2e job exists: the harness runs manually and its green
       baseline is not machine-enforced; the QA job covers unit tests,
       Behave and vitest, the release gates cover the contract diff
     - ``grep -n e2e .github/workflows/quality-assurance.yml`` (empty)
   * - Selectors
     - 29 semantic reads (``getByRole``, ``getByLabel``, ``getByText``)
       against 8 CSS locators, every one of them a third-party widget
       surface: the leaflet map container and its zoom controls (#947)
       and one ``table tbody tr`` row count
     - ``grep -rn 'page.locator(' frontend/e2e/specs``
   * - Fixed identifiers
     - ids and titles come from ``helpers/fixtures.ts`` (one source), yet
       a spec still hardcodes a ``BackgroundProcess/1`` path and the
       geometry specs repeat raw UUIDs
     - ``grep -rn '/1/show' frontend/e2e/specs``
   * - Waits
     - exactly one ``page.waitForTimeout(4000)`` survives
       (``map-geometry.spec.ts``); everything else is state-based
       ``expect`` or ``waitForResponse``
     - ``grep -rn waitForTimeout frontend/e2e/specs``
   * - Provenance
     - ``MRMAP_BUILD_REVISION`` (#1579) is already stamped into the
       bundle, so "which SHA did this browser run exercise" is answered
       by the artifact itself
     - ``grep -n MRMAP_BUILD_REVISION docker-compose.yml``
   * - MCP
     - one pinned Playwright MCP server in ``opencode.json`` (headless,
       isolated, network caps). No second playwright config and no
       competing MCP setup exists - keep it that way (#1687)
     - read the ``mcp.servers`` keys of ``opencode.json``

The gaps this contract exists to close: no Gherkin layer over the
browser, no CI tier for the harness at all, no tag vocabulary, no
redaction policy, and the drift the audit already shows - a hardcoded
path inside a spec, the surviving fixed sleep, raw UUIDs in a spec
instead of ``helpers/fixtures.ts``.

Directory layout (contract for #1689)
=====================================

Inside the existing harness, which stays deliberately outside the
application build (own pinned ``package.json``, outside the
``tsconfig.json`` include, outside the ESLint run and the Vite build):

.. code-block:: text

   frontend/e2e/
     features/     Gherkin .feature files, one per business journey
     steps/        step definitions grouped by the seven categories
     support/      shared plumbing: world and context, adapters, waiters,
                   redaction; no selector an adapter owns is duplicated here
     specs/        existing plain specs (performance and platform boot),
                   preserved per "Anti-duplication"
     helpers/      fixtures.ts (seeded ids and titles), session.ts
     acceptance_seed.py
     playwright.config.ts   gains the BDD project beside setup/chromium

Gherkin files carry no UUID, no CSS selector and no timeout. Those live
in ``helpers/fixtures.ts``, the adapters and the step layer - which is
what makes the surviving hardcoded values above debt for #1695: a
migrated scenario reads ``the record "WMS1"``, the adapter resolves the
id, the feature stays readable.

Generic step grammar (contract for #1691/#1692/#1693)
=====================================================

Seven categories, a closed set - the same discipline that keeps
``backend/tests/behave/steps/steps.py`` small: search before adding a
step, reuse beats invention.

.. list-table::
   :header-rows: 1
   :widths: 16 44 40

   * - Category
     - Shape (business-readable English)
     - Maps to
   * - Given-auth
     - ``Given I am signed in as "<role>"``;
       ``Given I am an anonymous visitor``
     - the storage states of ``support/session.ts``, one per role
   * - Given-state
     - ``Given the "<resource>" list``;
       ``Given the record "<name>" of "<resource>"``
     - a resource adapter; only ever the deterministic seeded state
   * - When-nav
     - ``When I open the "<menu entry>" screen``;
       ``When I search for "<term>"``
     - navigation by accessible name, never a raw URL with a fixed id
   * - When-form
     - ``When I fill in:`` (Data Table: label, value);
       ``When I press "<button>"``
     - ``getByLabel`` and ``getByRole`` over MUI and React-Admin
       accessible names
   * - Then-outcome
     - ``Then I see "<text>"``; ``Then I see <n> rows``;
       ``Then I see the fields:`` (Data Table);
       ``Then the row "<x>" shows "<value>"``
     - visible outcomes; row counts allowed, order only where a sort is
       the behaviour under test
   * - Then-async
     - ``Then the background process for "<action>" finishes``;
       ``Then the service "<x>" becomes running``
     - ``support/waiters.ts``: bounded state-based polling; interval and
       deadline live in code, the terminal state is the assertion
   * - Then-never
     - ``Then no error alert appears``
     - the existing ``expectNoForbiddenAlert`` over ``FORBIDDEN_ALERTS``
       in ``helpers/session.ts``

Three rules keep the grammar small:

- A step is **resource-neutral**. ``When I register a WMS`` is not a
  generic step - ``When I fill in:`` plus the press-button step compose
  it. A domain step needs a named reason the
  composition cannot express, exactly as ``steps/steps.py`` differs from
  ``steps/manual_updates.py`` in the Behave suite.
- Step text is English a reviewer who never saw the DOM can verify
  against a screenshot of the run. A sentence naming a widget class or a
  URL fragment sits in the wrong layer.
- Duplication guard (#1691): the step registry lists every defined step.
  A new step whose wording differs from an existing one by a synonym
  needs its commit message to name the considered step and why it does
  not fit - the gate ``frontend/src/components/AGENTS.md`` enforces for
  components, applied to steps.

Scenario-state lifetimes
========================

Three scopes, one owner and one reset each:

1. **Stack** - the disposable compose stack and its seeded database.
   One stack per run under a job-unique project name (root
   ``AGENTS.md``), seeded once by ``acceptance_seed.py``, destroyed by
   ``down -v`` at the end. Nothing reaches outside the stack; no
   production access (#1687 invariant 5).
2. **Database** - rows a scenario commits survive it, because the seed
   is loaded once per feature. A scenario that mutates a seeded row
   either reverts it in its own teardown step or creates a uniquely
   named record of its own. Scenarios never depend on execution order -
   the rule Behave states for its own fixtures applies unchanged here.
3. **Browser context** - one context per scenario. The storage states
   (anonymous, the acceptance user) are read-only seeds; a scenario that
   logs out or switches language gets a fresh context and cannot leak
   into the next one. This is the Playwright analogue of Behave's
   per-scenario context layer.

Resource adapters (contract for #1690)
======================================

One adapter per JSON:API resource family (service, metadata record,
harvesting run, background process, ...) under ``support/adapters/``.
An adapter is the only place that knows:

- how its resource is named in menus and screens, in both locales;
- which seeded rows represent it (imported from ``helpers/fixtures.ts``,
  the file whose primary keys the behave fixtures pin);
- how to open its list and show page **by name**, resolving the id there.

A scenario speaks resource nouns and record names; everything below the
noun belongs to the adapter. Adapters may read the OpenAPI and
React-Admin conventions for orientation, but assertions run against the
live UI: a schema that disagrees with the screen is precisely what this
class must catch (#1687 invariant 2).

Fixtures and cleanup (contract for #1694)
=========================================

- Seed keeps the ``acceptance_seed.py`` shape: flush the disposable
  database, load the behave fixtures, then create e2e-only rows.
  Deterministic, non-sensitive, never production data. A new fixture row
  gets its own reserved pk and uuid block - the
  ``test_harvesting_states.json`` pattern - so counts asserted elsewhere
  stay unchanged.
- OGC answers come from the compose services (mapserver is wired and
  ``acceptance_seed.py`` already points WMS1 at it), so the registration
  and update journeys exercise real GetMap and GetCapabilities. The two
  documented outbound dependencies of the bundle (the unpkg leaflet
  scripts, the OSM tiles) stay assertion-free; whether #1694 mocks or
  vendors them is its decision to record on this page.
- Credentials: the fixture-only local pair stays. No credential may
  appear in a feature, a step, a report title or an issue body.
- Cleanup follows the ``trap`` / ``finally`` discipline of the root
  ``AGENTS.md``: teardown runs on success, failure and interruption;
  shared images and volumes survive, this project's containers, networks
  and volumes do not.

Tag vocabulary (contract for #1698)
===================================

Tags are the CI routing, so the set is closed. Behave gets by with one
meaningful tag (``@skip``); this list is equally short:

- ``@smoke`` - runs in the PR tier; a handful of journeys, budget fixed
  by #1698.
- ``@journey`` - full business journeys including worker completion;
  nightly and pre-release tiers.
- ``@negative`` - failure paths: invalid capabilities, refused
  permissions, missing geometry.
- ``@exploratory`` - candidate scenarios recorded via #1699; excluded
  from CI until promoted through #1701.
- ``@wip`` - scenario of an open PR under review; CI excludes it.

A tag with no job and no documented meaning is drift. #1698's tier table
and this list change together, never alone.

Selector policy
===============

Preferred order: ``getByRole`` by accessible name, then ``getByLabel``,
then visible text. Forbidden in Gherkin: any CSS or XPath selector - the
step grammar gives a feature file no way to express one. Allowed in the
step layer as *documented* exceptions, matching what the audit found:
third-party widget surfaces without an accessible contract (the leaflet
map and its zoom controls), and one generic row-count selector *inside*
the ``Then I see <n> rows`` step rather than scattered across specs.
``data-testid`` is unused in production code today (all 236 hits are
inside unit-spec mocks); adopting a test-id contract is the last resort
of #1690 and needs a PR that amends this page at the same time.

Artifact redaction
==================

Traces, screenshots and video are retained on failure - and, in
exploratory sessions, on request - then redacted before the artifact
leaves the runner: strip the ``sessionid`` and ``csrftoken`` cookies and
the ``Authorization`` header from every request under a
session-authenticated path, and never ship a storage state together with
an artifact. Video stays off by default, as today; "retention on failure"
is the policy and "on request" belongs to the exploratory tier. Redaction
lives in ``support/`` so all tiers share one implementation.

CI tiers (contract for #1698)
=============================

- **PR smoke** - ``@smoke`` only, against the built stack. Must stay
  clearly cheaper than the QA suite; a docs-only or scripts-only PR never
  waits on it (#1687 invariant 7).
- **Nightly / pre-release** - the full ``@journey`` and ``@negative``
  set; redacted reports and the traces of failures downloadable from the
  run.
- **Interactive** - not a CI job: the exploratory workflow of #1699 on
  demand, against the same stack recipe.
- Stack class: full compose plus workers plus the built SPA is a heavy
  stack, so the admission question is the capacity gate with
  ``--need suite``; one stack per job, never beside another (root
  ``AGENTS.md``).
- Provenance: each run stamps ``MRMAP_BUILD_REVISION`` (#1579) and
  repeats the tested SHA in its report, so a report always names the
  commit it is evidence about.

Decision records: expected behaviour vs recorded clicks
=======================================================

Two kinds of Gherkin exist and they carry different authority:

- **Test-driven expectation** (the Behave tradition): written from the
  issue or a recorded decision, stating what *must* happen before the
  implementation is green. Only these become CI gates.
- **Recorded observation** (#1699 exploratory): mechanically recorded
  clicks and what the application did. These are proposals; #1701 turns
  a session into a draft scenario for human review. A recorded step may
  not assert a defect as if it were the promise - it becomes either a
  reviewed expectation or an issue.

Silent assertions are prohibited. A scenario without a ``Then`` naming an
outcome is not a scenario, and "the page did not error" only counts as an
assertion when it is the explicit ``Then no error alert appears`` over the
known ``FORBIDDEN_ALERTS`` list. An empty expectation list, or an
assertion whose failure no report can show, is a harness bug.

Anti-duplication
================

- **#1589 / #1602 (auto-docs)** own autonomous scenario discovery and the
  documentation screenshot pipeline with its capture manifest (source
  SHA, role, locale, step, digest). This epic consumes those primitives
  and never re-implements them: #1699's capture workflow builds on the
  same pinned Playwright MCP server and reuses #1602's naming and digest
  scheme. A PR in either epic that copies the other's capture helper is
  exactly the drift this rule forbids.
- **#948 / #1034 (frontend-walk)** own the harness and its specs. The
  boot and platform checks (deep-link boot, asset 404, transfer and
  caching #946) stay plain Playwright. Behavioural specs migrate to
  Gherkin only through #1695, one parity-checked scenario at a time: the
  old spec is deleted in the same PR that lands its green feature, never
  before.
- **Behave** keeps every API contract; a browser scenario is never a
  reason to delete a Behave scenario, and the QA suite does not shrink
  because the browser gate grew.

Known gaps and open decisions
=============================

- The harness has no CI job at all until #1698 adds the tiers; until
  then "green" means a documented manual run at a named SHA.
- ``map-geometry.spec.ts``'s ``waitForTimeout(4000)`` is the one
  time-based wait; #1695 replaces it with the state-based waiter.
- Fixed identifiers inside ``deep-links.spec.ts`` and
  ``lists-and-contracts.spec.ts`` are debt for #1695's adapters.
- Whether the bundle's two outbound CDN and tile dependencies get mocked
  or vendored is #1694's decision, recorded here.
- Whether the seeded row selector gains an accessible contract is #1690's
  decision; until then it stays the second documented exception.

When to touch this page
=======================

Any PR of #1689 - #1702 that moves a boundary: a new step category, a
new tag, a new locator exception, a tier's budget, the redaction scope,
or the four-class split. The contract changes with its implementation in
the same PR, so a reader of ``develop`` can always tell what the harness
guarantees.

