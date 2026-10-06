# MrMap frontend

Paths are relative to frontend/src/ unless stated otherwise”

The frontend uses:

- React
- TypeScript
- React-Admin
- Material UI (MUI)

When working on frontend code:

- Prefer React-Admin abstractions and hooks over custom implementations.
- Prefer MUI components and styling APIs over custom HTML/CSS.
- Keep TypeScript types strict; avoid `any` unless there is a strong reason.
- Reuse existing project components, hooks, utilities, and patterns.
- Follow existing routing and resource conventions.
- Preserve existing API contracts and JSON:API behavior.

## Architecture: schema-driven React-Admin

The frontend uses React-Admin with schema-driven resource behavior.
components/Resource/Definition.tsx explicitly registers resources and
their UI customizations. components/MrMapFrontend.tsx enriches these
registrations using the backend's OpenAPI schema.

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


## Verification

Run commands from frontend/.

- Type checking: npm run type-check
- Targeted tests: npm run test -- --run `<test-file>`
- Production build when relevant: npm run build

npm run lint and npm run format modify files across src/.
Keep formatting changes scoped to the task.


## Commands

Run frontend commands from `frontend/`.

Install dependencies:

```bash
npm install
```

Run the development server:

```bash
npm run dev
```

Use the scripts defined in `frontend/package.json` for linting, type checking, testing, and building. Do not assume a script exists without checking `package.json`.

For cross-stack changes, verify both backend and frontend. Prefer targeted tests during development; run broader suites when the scope or risk warrants it.



## Function style

Use anonymous arrow functions for all new functions. Assign reusable functions to `const` bindings (for example, `const formatName = (name: string) => ...`) and use arrow functions for callbacks. Do not use `function` declarations or named function expressions.
Put default exports on a separate line after the declaration (for example, `export default Component;`).