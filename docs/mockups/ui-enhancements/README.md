# REST API / UI enhancement mockups

Eight editable design proposals for issues #595–#602. These artifacts support review of the existing MrMap UI; they are not application code or API implementations.

Open **[index.html](index.html)** directly in a browser. No server, build, dependencies, credentials or network connection is needed. The GitHub links require a connection. The left navigation switches proposals; the Theme button toggles light/dark mode. All records, counts, dates, diagnostics and map shapes are fictional.

## Review by issue

| Issue | Interactive screen | Static preview | What to try |
| --- | --- | --- | --- |
| [#595](https://github.com/mrmap-community/mrmap/issues/595) | [Summary tiles](index.html#595) | [Desktop](previews/595.png) | Select No alerts or Needs attention, search sample rows, then open the explicitly global updates tile. |
| [#596](https://github.com/mrmap-community/mrmap/issues/596) | [Actionable attention](index.html#596) | [Desktop](previews/596.png) | Open failed-run diagnostics, proposed update changes and overdue schedule context. |
| [#597](https://github.com/mrmap-community/mrmap/issues/597) | [Selected-service sidebar](index.html#597) | [Desktop](previews/597.png) | Select different service titles; identity, attention and outcomes update before the scoped history. |
| [#598](https://github.com/mrmap-community/mrmap/issues/598) | [History inspection](index.html#598) | [Desktop](previews/598.png) · [Expanded difference](previews/598-history-detail.png) | Inspect text and geometry changes, search summaries, and browse the second sample page. |
| [#599](https://github.com/mrmap-community/mrmap/issues/599) | [Layer / feature-type inspector](index.html#599) | [Desktop](previews/599.png) | Switch WMS/WFS and select content to inspect coverage, formats and capabilities before editing. |
| [#600](https://github.com/mrmap-community/mrmap/issues/600) | [Metadata discovery](index.html#600) | [Desktop](previews/600.png) | Filter three sample records by quality and licence; open their detail summaries. |
| [#601](https://github.com/mrmap-community/mrmap/issues/601) | [Operational dashboard](index.html#601) | [Desktop](previews/601.png) | Open diagnostic/review actions and the chart's accessible daily figures. |
| [#602](https://github.com/mrmap-community/mrmap/issues/602) | [Configured access summary](index.html#602) | [Desktop](previews/602.png) · [Dark](previews/602-dark.png) · [Mobile](previews/602-mobile.png) | Select a rule to see content and spatial constraints, then switch protocol terminology. |

## Design boundaries

- Use the existing React-Admin/MUI visual vocabulary: blue app bar, neutral surfaces, compact tables, outlined cards and semantic status chips. The prototype uses plain HTML/CSS to stay independently reviewable; production should reuse existing components and schema-driven fields.
- “No alerts” does not mean recent successful monitoring. Missing configuration and overdue dispatch remain distinct from failure.
- The running-updates tile is explicitly global. Do not copy service-list filters to unrelated background-process resources.
- Schedule timestamps describe dispatch; monitoring-run timestamps describe execution. Neither establishes outage onset.
- Metadata quality, metadata date and service availability are separate signals. Absence of quality flags is not certification.
- Access tables summarize configured rules. They do not evaluate user-specific effective permissions or resolve overlapping rules.
- Maps are schematic SVG illustrations, not geographic data or live previews. Map zoom controls are visual placeholders. Production preview actions should reuse the authorized live-preview implementation.
- Filters and pagination operate only on the sample data. Production counts/facets must operate on the complete authorized result set. Registry-wide schedule-state aggregation and some metadata filters require backend support.
- Buttons open small concept dialogs or related mockup screens. They do not register services, publish updates, edit rules or call APIs. The inspector's edit button illustrates placement; production visibility depends on permissions.

## Files and validation

- `index.html`: standalone shell, issue navigation and accessible details dialog.
- `styles.css`: shared responsive layout and light/dark tokens.
- `mockups.js`: sample records, eight screens and local interactions.
- `previews/`: browser-rendered PNGs for issue review, captured from this prototype.

Validation: `node --check docs/mockups/ui-enhancements/mockups.js`; Chromium checks for all eight routes at desktop (1440 × 1100) and mobile (390 × 844) widths, including document overflow checks. Exercised tile filtering, attention dialogs, service selection, history differences/pagination, WFS inspection, metadata filtering, rule selection/protocol switching and theme toggling. No browser runtime exceptions were recorded.

The application test suites were not run because this change only adds independent documentation artifacts. These checks do not substitute for permission, API or production-component tests when the issues are implemented.
