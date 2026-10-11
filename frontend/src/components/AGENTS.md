# Components

React-Admin screens and feature areas. Commands and the current red baselines are in
`../../../AGENTS.md`; the schema layer is described in `../../jsonapi/AGENTS.md`.

This is the hottest area of the repository: most changes touch `Resource/`, and neither
`npm run type-check` nor the specs are clean on `main`, so compare against the documented baseline
instead of assuming a green run.

## Resource screens

`Resource/Definition.tsx` is the single registration point. It exports an array of react-admin
`ResourceProps` that `components/MrMapFrontend.tsx` enriches with the backend OpenAPI schema. A new
resource-backed screen means adding an entry here, not wiring a route somewhere else:

```tsx
{
  name: "WebMapService",              // must equal the JSON:API type
  icon: MapIcon,
  show: WmsShow,
  list: ListWebMapService,            // omit to get the generic list
  options: {
    menu: { group: "WMS", order: 10 },
    list: {
      perPage: 25,
      sort: { field: "title", order: "ASC" },
      defaultSelectedColumns: ["id", "title", "abstract"],
      sparseFieldsets: [{ type: "WebMapService", fields: ["isSecured"] }],
      additionalActions: WmsViewerButtons,
    },
  },
}
```

Folder convention inside `Resource/<JsonApiTypeName>/`:

- `List<Resource>.tsx`, `Show<Resource>.tsx` (or `Show/<Resource>Show.tsx` for larger screens).
- `Show/Tabs/` for tab contents, `Show/Overview/` for the dashboard cards; each card keeps its own
  folder when it grows, e.g. `Show/Overview/MonitoringRuns/`.
- Helpers that serve exactly one resource stay in that resource's folder. Shared screens belong to
  `Resource/Generic/` — check there before writing a resource-specific variant.

## Data and schema

Read through the JSON:API layer and react-admin context hooks; never hand-roll fetchers or mirror
backend fields:

- `useListContext()`, `useRecordContext()`, `useGetList()` for data already scoped by the screen.
- `jsonapi/` hooks and components for schema-driven fields, relationships and inputs. Field sets,
  validation and available operations come from the OpenAPI schema.
- Explicit field names are fine for presentation decisions (columns, order, widgets), not for
  re-declaring API structure.

## Translations

Screens translate through `useTranslate()` with keys namespaced per resource, usually through a
small helper:

```tsx
const translate = useTranslate();
const message = (key: string) => translate(`resources.${resource}.${key}`);
```

Every new key goes into `i18n/en.ts` **and** `i18n/de.ts` in the same change.

## Specs

- Specs sit next to the implementation and are named `<Name>.spec.tsx` / `<Name>.spec.ts`. Vitest
  collects `*.spec.*` below `src/`, so a dotfile named `.spec.ts` is collected too but fails to load
  cleanly; never name a spec file that way, and never import `node:test` in one.
- Environment is jsdom with `frontend/tests/setup.js` (testing-library cleanup and jest-dom
  matchers). Specs mock the react-admin surface they use, which keeps them fast:

```tsx
vi.mock("react-admin", () => ({
  useListContext: vi.fn(),
  useGetList: vi.fn(),
  useTranslate: () => (key: string) => key.split(".").pop(),
}));
```

  With that mock, assertions read the last segment of the translation key, so keys must stay
  meaningful per segment.
- Run a single area while iterating (see `../../../AGENTS.md` for the Docker wrapper):
  `npx vitest --run src/components/Resource/HarvestingJob`.
- `npm run lint` and `npm run format` rewrite all of `src/`; keep formatting changes out of a
  targeted change.