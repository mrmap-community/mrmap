# Components

React-Admin screens and feature areas. Commands and the current red baselines are in
`../../../AGENTS.md`; the schema layer is described in `../../jsonapi/AGENTS.md`.

Most changes touch `Resource/`. Lint, strict type checking and the frontend specs are required CI
checks; run targeted specs while iterating and the full coverage suite before finishing broad work.

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

## Reuse before writing a component

Roughly 90 shared components live in `Resource/Generic/` (45), `jsonapi/components/` (24) and
`MUI/`, `Lists/`, `Field/`, `Input/`, `Dialog/`, `Drawer/` (the rest). Most of them are already
**composites** — a card that carries title, fields, chips, actions and its own empty state. New screens
almost always need exactly one of those, so the interesting question is never "which helper do I need"
but "which card, list, field or button already renders this".

Hard gate before creating a new `.tsx`: run the search below and name the considered components in the
commit message ("reuses `ServiceDetailsCard`, which already renders X; `Y` did not fit because Z"). A
duplicated card is worse than no card: it loses the spec of the original, silently diverges from it and
both copies then drift apart.

```bash
# from frontend/src — inventory the composites, they are the ones worth reusing
ls components/Resource/Generic/*/ components/MUI components/Lists components/Field \
   components/Input components/Dialog components/Drawer jsonapi/components
# search by capability and by the words the UI shows, never by the name of your new screen
grep -rli --include=*.tsx 'details\|summary\|history\|count\|preview\|empty' \
     components/Resource/Generic components/MUI components/Lists jsonapi/components
# user-visible wording that is already translated belongs to an existing screen
grep -n 'details\|summary\|history' i18n/en.ts | head -30
# screen-independent components read their data from context
grep -rl useRecordContext --include=*.tsx components/Resource/Generic | grep -v spec
```

### Context, not props

A shared component does not know which screen renders it: 30 of the 45 components below
`Resource/Generic/` read `useRecordContext()`, `useResourceContext()` or `useListContext()`. Rendering
one somewhere new means providing the context, not passing the record or copying the JSX:

```tsx
<RecordContext value={service}>
  <ServiceDetailsCard protocol="WMS" />
</RecordContext>
```

Those three lines replaced a 274-line `ServiceDetailsPanel.tsx` in `Resource/WebMapService/List/`, which
had re-implemented the details card, the preview image, the alert chips, the metadata fields, the action
buttons and the recent update runs of a service the list already had in hand. Reuse does not constrain
the layout: `SimpleCard` takes `title`, `footer`, `cardProps`, `contentProps` and `headerProps`.

### If the shared component really does not fit

- it lacks a variant or a prop → add an optional prop to the generic component;
- it should read a different record → add a thin context wrapper
  (`ServiceShow/SelectedServiceDetailsCard.tsx` is 21 lines around `ServiceDetailsCard`);
- it needs fields the current screen does not answer → ask the screen for them (see *Reuse costs data*
  below) instead of rendering a lighter copy;
- genuinely nothing fits → say so in the commit message, and file the new component where its reuse
  potential is: `Resource/Generic/<Area>/` when another protocol can use it, `Resource/<TypeName>/`
  only when exactly one resource does.

Move a component into `Generic/` when a second user appears, not before.

### Reuse costs data

Reusing a card also buys its data requirements. `ServiceDetailsCard` renders `preview_url`, so the
service list had to answer it: the field lives on `WebMapServiceListSerializer` in
`backend/registry/serializers/service.py` and the list field set names it. Asking the backend for the
field — and letting JSON:API sparse fieldsets keep it off the screens that do not ask for it — is the
cheap and correct option; shrinking or copying the card to avoid the field is the duplicate.

### Where to look first

| Folder | Holds | Do not write |
| --- | --- | --- |
| `Resource/Generic/ServiceShow/` | per-service cards and actions: `ServiceDetailsCard`, `SelectedServiceDetailsCard`, `ServiceOverview`, `ServicePreviewImage`, `ServiceAlertChips`, `ServiceUpdateJobsCard`, `ServiceHistoryCard`, `ServiceAttentionTab`, `ActivateServiceButton`, `RunServiceUpdateButton` | a card with one service's metadata, alerts, preview, update runs or history |
| `Resource/Generic/ServiceList/` | the shared WMS/WFS/CSW list: `ServiceList`, `ServiceListExplorer`, `ServiceListAside`, `ServiceSummaryTiles`, `ServiceElementCount`, `alertFacets`, `serviceListProps`, `config` | a second service list layout, facet or summary tile |
| `Resource/Generic/RecordShow/` | `RecordShow`, `RecordHeader`, `RecordFields`, `RecordContacts`, `RecordRelations`, `RecordOverview`, `RecordSpatial`, `RecordHistory` | a label/value stack for record attributes |
| `Resource/Generic/History/` | `HistoryList`, `HistoryListBase`, `ServiceHistoryList`, `HistoryTimeline`, `HistoryChart`, `historySources` | a timeline, changelog or event list |
| `Resource/Generic/{List,Show,Update,Explorer}/` | `SimpleList`, `ShowResource`, the update setting screens and their field definitions, the coverage explorer | another wrapper around `ListGuesser`, another update settings form |
| `MUI/` | `SimpleCard`, `SimpleTabs`, `CircularProgressWithLabel`, `GradientChartsContainer` | a `Card` with its own header, footer or padding |
| `Lists/` | `CustomListActions`, `Empty`, `EmptyWithFilter` | a list action bar or an empty state |
| `Field/`, `Input/` | `TruncatedTextField`, `ProgressField`, `GeoJsonField`, `RelatedResourceField`, `MouseOverPopover`, `CronInput`, `TreeSelectInput`, `GeoJsonInput` | a one-off field or input renderer |
| `Dialog/`, `Drawer/`, `Tab/` | `Dialog`, `DialogContextBase`, `CreateDialogButton`, `EditDialogButton`, `RightDrawer`, `ResizeableDrawer`, `BottomDrawer`, `Tabs`, `TabListContext` | MUI dialog, drawer or tab scaffolding |
| `jsonapi/components/` | guessers, `SchemaFormFields`, `SchemaAutocompleteInput`, `Reference*Field`, `Count`, `ListWithDialogs`, `PaginatedSingleFieldList`, `Realtime/*`, `SelectedRecordContext` | manual fetching, counts or a hardcoded copy of schema fields |

Every entry keeps its `<Name>.spec.tsx` next to it, which documents its contract and its empty states —
read that before deciding a component does not fit.

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
- `npm run lint` is read-only. `npm run lint:fix` and `npm run format` rewrite files; keep those
  changes scoped to the task.
