# jsonapi layer

The schema-driven foundation of the frontend: it parses the backend's OpenAPI schema and exposes it
to React-Admin as hooks and reusable components. Resource specific code does not belong here; it
lives in `../components/Resource/<Resource>/`.

Paths in this file are relative to `frontend/src/jsonapi/`. Frontend-wide rules and commands stay in
`frontend/AGENTS.md`.

## Layout

- `openapi/parser.ts` — turns the OpenAPI document into the internal schema model. Extend the parser
  when the backend exposes metadata the frontend needs; never re-read the raw document elsewhere.
- `types/jsonapi.tsx` — types of the schema model and of JSON:API payloads.
- `hooks/` — schema access as React hooks, e.g. `useResourceSchema`, `useFieldsForOperation`,
  `useFieldForOperation`, `useSparseFieldsForOperation`, `useOperation`,
  `useGetRelatedOperationSchemas`, `useFilterInputForOperation`, `useSchemaRecordRepresentation`,
  `useJsonApiQuery`.
- `components/` — schema-driven UI: guessers (`ListGuesser`, `CreateGuesser`, `EditGuesser`),
  `SchemaFormFields`, `SchemaAutocompleteInput`, reference fields and inputs, `ListWithDialogs`,
  `PaginatedSingleFieldList`.
- `components/Realtime/` — WebSocket driven list and show updates (`RealtimeBus`, `RealtimeListBase`,
  `RealtimeList`, `RealtimeShowContextProvider`, `SnackbarObserver`).
- `utils.tsx` — shared helpers of this layer.

## Rules

- The parsed schema is the single source of truth. Derive fields, relationships, validation
  constraints and supported operations from it; do not mirror backend models in TypeScript.
- Add new behaviour by extending or composing an existing hook or component. If a required piece of
  metadata is missing, report the schema limitation instead of hardcoding a workaround.
- Keep generic API/schema logic in this folder and presentation decisions in `components/Resource/`.
- Resource-backed screens and exploration tools build on these components and on React-Admin lists
  and filters before any custom selector or manual fetching is introduced.
- Tests are Vitest specs colocated with the code (`*.spec.ts`, `*.spec.tsx`), including integration
  specs such as `SchemaAutocompleteInput.integration.spec.tsx`. Run them targeted:
  `npm run test -- --run src/jsonapi/openapi/parser.spec.ts` (from `frontend/`).
