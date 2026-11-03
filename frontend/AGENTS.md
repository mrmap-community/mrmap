# MrMap frontend

React, TypeScript, React-Admin and Material UI (MUI), tested with Vitest and bundled by Vite.

Paths in this file are relative to `frontend/src/` unless stated otherwise; commands run from
`frontend/`. The schema layer is described in more detail in `jsonapi/AGENTS.md`.

When working on frontend code:

- Prefer React-Admin abstractions and hooks over custom implementations.
- Prefer MUI components and styling APIs over custom HTML/CSS.
- Keep TypeScript types strict; avoid `any` unless there is a strong reason.
- Reuse existing project components, hooks, utilities, and patterns. Before creating a new component,
  work through the order of resort below; `src/components/AGENTS.md` inventories what already exists.
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

## Order of resort

For new UI code, stop at the first level that can carry the requirement; only go one level deeper when
the level above genuinely cannot:

1. A React-Admin component or hook — `List`, `Datagrid`, `Show`, `SimpleShowLayout`, fields, inputs,
   buttons and their context hooks.
2. A schema-driven hook or component in `jsonapi/` — guessers, `SchemaFormFields`, reference fields,
   realtime bases.
3. A composite under `components/Resource/Generic/` — service and record cards, the shared list and show
   screens, history components. Make it fit by providing its context (`RecordContext`,
   `ResourceContext`, `ListContext`), never by copying it into a resource folder.
4. A wrapper under `components/{MUI,Lists,Field,Input,Dialog,Drawer,Tab}/` — `SimpleCard`, `Empty`,
   `EmptyWithFilter`, `CustomListActions`, dialogs, drawers and tabs.
5. A new component, placed in the folder that matches its reuse potential, with the alternatives that
   were considered named in the commit message.

`src/components/AGENTS.md` inventories levels 3 and 4 and shows the discovery commands.

## Placement principles

- Extend the nearest existing implementation before creating a new abstraction.
- Copying a shared component into a feature folder is a fork, not a placement decision: it drops the
  spec of the original and its later fixes. Extend it with an optional prop, or wrap it in the context
  it reads, and keep the wrapper thin.
- A new component file names its evidence: which existing component was considered and why it did not
  fit.
- Keep components, hooks, helpers, and tests near the feature using them.
- Move code into shared folders when there is a concrete reuse need.
- Follow the naming and nesting of neighboring files.
- Avoid reorganizing folders as part of unrelated changes.


## Verification and commands

Run commands from `frontend/`. Scripts are defined in `package.json`; do not assume a script exists
without checking it. If `node`/`npm` are not installed on the host, use the `frontend-tests` service
from the repository root; it keeps its dependencies in a named volume, so only the first run pays
for `npm ci` (~20 s):

Follow the Docker ownership and cleanup rules in `../AGENTS.md`. Use `--no-deps` for frontend checks;
they do not need backend services. Retain the shared `frontend-node-modules` cache. Avoid running
`npm ci` or changing dependencies in a shared volume while another job is using it.

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml run --rm --no-deps frontend-tests
docker compose -f docker-compose.yml -f docker-compose.dev.yml \
  run --rm --no-deps frontend-tests npx vitest --run src/components/Resource/HarvestingJob
docker compose -f docker-compose.yml -f docker-compose.dev.yml \
  run --rm --no-deps frontend-tests npm run type-check
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
- `npm run lint` is read-only and is required in CI. `npm run lint:fix` applies autofixes;
  `npm run format` rewrites formatting. Keep formatting changes scoped to the task.
- ESLint, the strict TypeScript check and the complete frontend test suite must all pass.
  Run `npm run test-coverage` for the coverage gate and HTML/LCOV reports in `coverage/`.
- For cross-stack changes, verify both backend and frontend. Prefer targeted tests during
  development; run broader suites when the scope or risk warrants it.
- Backend changes are verified separately; see `../backend/AGENTS.md`.

## Quality gates

The frontend CI job requires `npm run lint`, `npm run type-check`, and `npm run test-coverage`.
Do not use the historical failing-test or type-error counts as an allowance for new failures.
Coverage includes untested source files, excludes specs, fixtures and declarations, and is published
as a CI artifact. See `../docs/source/development/code-quality.rst` for the reporting workflow.
