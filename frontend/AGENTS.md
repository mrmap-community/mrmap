# MrMap frontend

React, TypeScript, React-Admin and Material UI (MUI), tested with Vitest and bundled by Vite.

Paths in this file are relative to `frontend/src/` unless stated otherwise; commands run from
`frontend/`. The schema layer is described in more detail in `jsonapi/AGENTS.md`.

When working on frontend code:

- Prefer React-Admin abstractions and hooks over custom implementations.
- Prefer MUI components and styling APIs over custom HTML/CSS.
- Keep TypeScript types strict; avoid `any` unless there is a strong reason.
- Reuse existing project components, hooks, utilities, and patterns.
- Follow existing routing and resource conventions.
- Preserve existing API contracts and JSON:API behavior.
- Use anonymous arrow functions for all new functions. Assign reusable functions to `const` bindings
  (for example, `const formatName = (name: string) => ...`) and use arrow functions for callbacks.
  Do not use `function` declarations or named function expressions.
- Put default exports on a separate line after the declaration (for example,
  `export default Component;`).

## Architecture: schema-driven React-Admin

`components/Resource/Definition.tsx` explicitly registers resources and their UI customizations.
`components/MrMapFrontend.tsx` enriches these registrations using the backend's OpenAPI schema.

Resource fields and API metadata are interpreted at runtime through
jsonapi/ hooks and components, avoiding separately maintained copies
of backend model definitions.

The OpenAPI schema is the source of truth for resource structure and
supported API operations. The jsonapi/ layer interprets this schema
and provides reusable hooks and components for schema-driven UI.
Resource-specific components customize presentation and workflows
on top of that foundation.

When implementing frontend changes:

- Inspect existing schema hooks and components in jsonapi/ first.
- For resource-backed exploration and testing tools, reuse schema-driven
  React-Admin lists and filters. Before adding custom selectors or fetching
  option lists, establish why existing list/filter abstractions cannot support
  the workflow.
- Derive resource metadata from the schema using existing abstractions.
- Avoid duplicating schema-defined fields, relationships, validation
  constraints, or supported operations in hardcoded frontend definitions.
- Use React-Admin abstractions through the existing JSON:API integration.
- Keep resource-specific presentation and workflow logic in
  components/Resource/`<Resource>`/.
- If required metadata is unavailable, identify the schema limitation
  instead of silently introducing a separate frontend model.
- Keep TypeScript types for UI state and integration contracts; avoid
  manually mirroring backend models when schema-derived types or
  existing generic types can express the requirement.
- Explicit field names are appropriate for presentation choices such
  as column selection, ordering, and custom widgets. Reuse schema-derived
  field definitions and existing override mechanisms instead of
  redeclaring their API structure or constraints.


## Folder responsibilities

- components/Resource/`<Resource>`/
  Resource-specific screens, actions, hooks, and presentation.
  Keep code used by only one resource within that resource's folder.

- components/Resource/Generic/
  Shared resource UI, including generic list, show, and history components.
  Check these implementations before adding resource-specific equivalents.

- components/
  UI components and feature areas.
  Reuse existing Field/, Input/, Dialog/, Layout/, and MUI/ components.
  Keep feature-specific components within their existing feature folder.

- jsonapi/
  JSON:API and OpenAPI integration: schema parsing, types, hooks,
  and schema-driven UI components.
  Put reusable API/schema behavior here; keep resource-specific
  presentation in components/Resource/.

- providers/
  Application providers for data access, authentication,
  translations, and system time.
  Reuse existing data-access paths when adding API interactions.

- context/
  Shared application contexts.
  Keep feature-specific contexts beside their feature.

- ows-lib/
  OWS domain types, parsing, and context logic.
  Keep domain logic independent of React presentation.

- react-ows-lib/
  React integration for OWS functionality.

- i18n/
  English and German translations.
  Update both languages when introducing translation keys.

## Placement principles

- Extend the nearest existing implementation before creating a new abstraction.
- Keep components, hooks, helpers, and tests near the feature using them.
- Move code into shared folders when there is a concrete reuse need.
- Follow the naming and nesting of neighboring files.
- Avoid reorganizing folders as part of unrelated changes.


## Verification and commands

Run commands from `frontend/`. Scripts are defined in `package.json`; do not assume a script exists
without checking it. If `node`/`npm` are not installed on the host, use the `frontend-tests` service
from the repository root; it keeps its dependencies in a named volume, so only the first run pays
for `npm ci` (~20 s):

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml run --rm frontend-tests
docker compose -f docker-compose.yml -f docker-compose.dev.yml \
  run --rm frontend-tests npx vitest --run src/components/Resource/HarvestingJob
docker compose -f docker-compose.yml -f docker-compose.dev.yml \
  run --rm frontend-tests npm run type-check
```

```bash
npm install                                          # install dependencies, once
npm run dev                                          # development server
npm run type-check                                   # tsc --noEmit, ~1 min
npm run test -- --run src/jsonapi/utils.spec.tsx     # targeted tests
npm run test -- --run                                # all specs, ~80 s
npm run test-coverage                                # all tests with coverage
npm run build                                        # production build, when relevant
```

- Tests are Vitest specs colocated with the code they test and named `*.spec.ts` or `*.spec.tsx`.
  `frontend/tests/` only holds the Vitest setup. Name new tests the same way. Vitest's default
  collection pattern also matches hidden files, so a spec literally named `.spec.ts` is collected
  but is excluded from `tsconfig.json`; both problems disappeared once the two dotfile specs in
  `ows-lib` were renamed — do not reintroduce one.
- `npm run lint` and `npm run format` modify files across `src/`. Keep formatting changes scoped to
  the task.
- For cross-stack changes, verify both backend and frontend. Prefer targeted tests during
  development; run broader suites when the scope or risk warrants it.
- Backend changes are verified separately; see `../backend/AGENTS.md`.

## Known red baselines

No CI job gated on these checks before 2026-10; the `frontend-tests` job in
`.github/workflows/quality-assurance.yml` now runs them with `continue-on-error: true`. Neither is
clean on `main`, so treat both as baselines to compare against instead of expecting green:

- `npm run type-check`: 114 errors, spread over `components/` (largest clusters in
  `MapViewer/OwsContextGuiActions/EditAuthenticationsDialog.tsx`, `Resource/HarvestingJob/HarvestingJobTimingCharts.tsx`),
  `jsonapi/`, `providers/`, `i18n/de.ts` and `ows-lib` test fixtures.
- `npm run test -- --run`: 52 to 56 failing of 268 tests, in 12 to 14 of 47 files; the exact count
  moves between runs because several specs are timing sensitive, so treat the range as the
  baseline. Clusters:
  `Resource/WebMapService/Show/Overview/MonitoringRuns` and `.../UpdateJobs` (empty-state and
  error-state cards), `LayerTree`, `Resource/Generic/ServiceShow`,
  `Resource/WebMapServiceUpdateJob`, and `ows-lib/OwsContext/tests/OwsContext.spec.ts` (16 tests
  asserting folder semantics the current `ows-lib` move/insert code does not implement; that file
  collected zero tests until 2026-10, because it imported `describe` from `node:test`).

Removing failures is welcome; the goal of this section is to make a failing run interpretable. When
the CI job stops being informational, these are the numbers to clear first.