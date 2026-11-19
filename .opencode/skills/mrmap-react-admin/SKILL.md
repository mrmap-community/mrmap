---
name: MrMap React-Admin Frontend
description: "Working on the MrMap frontend — React 19 + TypeScript screens, React-Admin resources and hooks, the schema-driven jsonapi/ layer, MUI components, i18n keys, or Vitest specs under frontend/."
---

# MrMap React-Admin Frontend

Task skill for `frontend/`. The nearest `AGENTS.md` wins: `frontend/AGENTS.md` (conventions,
commands, order of resort), `frontend/src/components/AGENTS.md` (component inventory + reuse gate),
`frontend/src/jsonapi/AGENTS.md` (schema layer). This skill routes you into those files.

## Activation

Load when the task touches `frontend/src/` — components, hooks, `jsonapi/`, routing/resource
registration, `i18n/en.ts` / `i18n/de.ts`, or Vitest specs.

## Mandatory project rules (sources named)

- Schema-driven: OpenAPI is the source of truth; derive fields, relationships, validation and
  operations from `jsonapi/` hooks; never mirror backend models in TypeScript
  (`frontend/AGENTS.md`, `frontend/src/jsonapi/AGENTS.md`).
- Order of resort before any new UI code (levels 1–5 in `frontend/AGENTS.md`); the reuse gate in
  `frontend/src/components/AGENTS.md` is hard — run its discovery commands and name the considered
  components in the commit message. Shared components are reused by **providing their context**
  (`RecordContext`/`ResourceContext`/`ListContext`), never by copying.
- New resources register in `components/Resource/Definition.tsx` only.
- Style: anonymous arrow functions assigned to `const`, no `function` declarations; default export
  on its own line; strict TS, no `any` without strong reason (`frontend/AGENTS.md`).
- Every new translation key goes into `i18n/en.ts` **and** `i18n/de.ts` in the same change.
- A `sort`/`filter[...]` a screen sends is an API contract — the backend must declare it and a
  behave scenario must pin it before the screen asks (#1080, `frontend/AGENTS.md`).
- `npm run lint` is read-only; never run whole-tree `lint:fix`/`format` for a scoped change
  (`AGENTS.md` "Never do").

## Recommended patterns (project code, mirror these)

- Read the `<Name>.spec.tsx` of a shared component before deciding it does not fit; fit it by
  optional prop, thin context wrapper, or asking the backend for the missing field (sparse
  fieldsets keep the cost off other screens) — `frontend/src/components/AGENTS.md`.
- Data already scoped by a screen comes from `useListContext()` / `useRecordContext()`;
  schema-driven inputs from `jsonapi/` (`useResourceSchema`, `SchemaFormFields`,
  `SchemaAutocompleteInput`, reference fields, `Realtime/*`).
- Realtime: list/show updates arrive over the shared WebSocket invalidation bus — refetch, don't
  hand-roll subscriptions (see skill `mrmap-celery` for the producer side).
- New frontend route whose name starts with a proxied prefix: add it to the table in
  `scripts/nginx_routing_smoke.py` (root `AGENTS.md`).

## Anti-patterns

- Copying a composite from `Resource/Generic/` into a resource folder (it forks — see the
  `ServiceDetailsPanel.tsx` case in `frontend/src/components/AGENTS.md`).
- Custom fetchers/selectors where a schema-driven list, filter or `useGetList` exists.
- Hardcoded field/validation copies of schema information; new date or HTTP libraries (the stack is
  fixed: MUI v9, react-admin v5, `react-use-websocket`, `fast-xml-parser`).
- Specs named `.spec.ts` as dotfiles; `import "node:test"` in a spec (`frontend/AGENTS.md`).

## Framework references (recommendations, not project rules)

- React-Admin v5: https://marmelab.com/react-admin/ — MUI v9: https://mui.com/material-ui/
- MUI X (data grid/charts): https://mui.com/x/ — Vitest: https://vitest.dev/
- An `@mui/mcp` documentation server was tried on this host and removed (unreliable network);
  do not make any skill depend on it. Use the official docs sites above when needed.

## MCP dependencies

None required. Verification is lint/type-check/Vitest in the `frontend-tests` container.
**Optional** (repo `opencode.json`, see `docs/development/mcp-servers.md`): `react-admin-docs`,
`mui-docs` and `mui-x-docs` are GitMCP servers pinned to the exact versions this frontend builds
against — consult them instead of trusting training data for hook or component behaviour. A
`playwright` server plus an already-running dev stack may serve read-only visual checks of a
screen — never as the primary verification, and never start a stack just for browser testing.

## Verification (commands in `frontend/AGENTS.md`)

1. From the repository root, in the job's own stack: `frontend-tests npm run lint` and
   `npm run type-check`.
2. Targeted specs while iterating (`npx vitest --run src/components/Resource/<Area>`);
   `npm run test -- --run` (all) and `npm run test-coverage` for broad changes.
3. API-facing changes: verify the backend side too (skill `mrmap-drf-jsonapi`).

## Security constraints

- Never store tokens/credentials outside the existing auth provider flow; Knox tokens are handled
  by `providers/` auth code only. No secrets in `i18n/` or bundle-able files.
- Do not weaken content handling of upstream XML/HTML (render via existing OWS components;
  never `dangerouslySetInnerHTML` for remote content).

## Explicit exceptions

- Explicit field names are allowed for presentation decisions (column choice, order, widgets) —
  just not to re-declare API structure (`frontend/AGENTS.md`).
- `any` is tolerable only with a stated reason at the exact site; prefer schema-derived or generic
  existing types.
