---
name: MrMap OGC Services
description: "Working on MrMap OGC handling — WMS/WFS/CSW capabilities parsing and persistence (registry/mappers, registry/ows_lib), the /csw endpoint, OGC requests/responses and exception reports, XML parsing of upstream documents, harvested ISO metadata, monitoring probes, or the OWS map-context layer in frontend ows-lib."
---

# MrMap OGC Services

Task skill for standards-facing code. The nearest `AGENTS.md` wins; layout and the "where behaviour
lives" rules are in `backend/registry/AGENTS.md`, domain overview in `docs/architecture.md` and
`docs/ows-context.md`.

## Activation

Load when the task touches `backend/registry/ows_lib/`, `backend/registry/mappers/`,
`backend/csw/`, `backend/registry/views_ows/`, capabilities documents, ISO 19115/OGC XML, WMS/WFS
requests, monitoring probes, or `frontend/src/ows-lib` / `react-ows-lib`.

## Mandatory project rules (sources named)

- `registry/ows_lib/` is pure domain code: **no DRF, no models** (`backend/registry/AGENTS.md`).
  Requests are analyzed through `ows_lib/request/ogc_request.py`
  (`OGCRequest.from_django_request`); refusals answer OWS Common `ExceptionReport` via the builders
  in `ows_lib/response/exceptions.py` — exactly one exception, with `exceptionCode`, `locator`,
  `ExceptionText`, built from the request it answers; never an empty skeleton
  (`backend/tests/behave/AGENTS.md`, "/csw refusals").
- Protocol versions are declarative: a new version means a new config file in
  `registry/mappers/configs/` keyed `("WMS","1.3.0")`-style — never branch on version in shared
  mapper code (`backend/registry/AGENTS.md`).
- Persistence modes are configuration: `"_create_mode": "bulk_with_history"` and
  `"get_or_create"` (lookup tables, ordered bulk + `ignore_conflicts`, #817) are handled in
  `registry/mappers/persistence/handler.py` — do not write parallel write paths.
- Capabilities of a secured service are served from the stored (camouflaged) document, not
  proxied live (`registry/proxy/mixins.py`); stored `xml_backup` is what `/csw` GetRecords and
  live previews read — a missing backup must not trigger an unbounded remote fetch
  (`registry/helper/preview.py`). Reducing duplicate OGC downloads is an open epic (#1408): do not
  add new download paths without checking it.
- External OGC HTTP goes through `registry/ows_lib/client/core.py` `OgcClient`: default timeout
  10 s, redirects followed manually at most `MAX_REDIRECTS` and refused when the chain leaves the
  origin host (#1100). New outbound requests set an explicit timeout and do not follow
  cross-host redirects (CodeQL runs `security-extended`; SonarCloud flags insecure-looking URLs —
  a normative OGC/ISO/INSPIRE identifier is suppressed with `NOSONAR` + reason on the reported
  line, never rewritten, root `AGENTS.md`).
- XML from upstream is untrusted: parse with hardened lxml settings where the pattern exists
  (`etree.XMLParser(resolve_entities=False, no_network=True)` in `registry/models/harvest.py`,
  `registry/helper/preview.py`, `registry/helper/resource_capabilities.py`). Extending that
  hardening to new parse sites is the house direction; changing normative identifier values is not.

## Recommended patterns (project code, mirror these)

- XPath mapping lives in `mappers/configs/*.py`; parsers/pre-save hooks in
  `mappers/parsers/` and `mappers/extensions/`; identifiers/uuid handling stays in
  `mappers/identifiers.py` so matched elements keep identity across updates (`docs/architecture.md`).
- CSW endpoint code: single class-based `csw/views.py:CswServiceView` dispatching on the analyzed
  request; KVP helpers (`parse_kvp_list`, `canonicalize_kvp_operation`) before version handling;
  unknown operations → `OperationNotSupportedException` (`backend/csw/views.py`).
- WMS/WFS securing math (masks, GML geometry) stays in `registry/proxy/` + `ows_lib/wms|wfs/gml`
  — coordinate axis order conversions are centralized (`adjust_axis_order`), don't hand-convert.
- Frontend OWS domain logic stays framework-free in `frontend/src/ows-lib`, React binding in
  `react-ows-lib` (`frontend/AGENTS.md`).

## Anti-patterns

- Fetching schemaLocation/XSI-referenced documents during parsing (namespaces are local
  constants — `XML_NAMESPACES` in settings carries `NOSONAR` for exactly this reason).
- String-matching or regex on XML; rebuilding whole capabilities documents in Python outside
  `ows_lib/xml/`.
- Asserting an entire XML document in behave — assert the elements that carry the behaviour
  (`xpath` steps, `XpathTestCase` in `tests/django/contrib.py`).
- Waiting for remote services in tests — there is no network; mock the client/module under test
  (`backend/tests/AGENTS.md`).

## Framework / standard references (recommendations, not project rules)

- OGC CSW 2.0.2, OWS Common exception rules (OGC 07-006r1 §10.3.7), WMS 1.1.1/1.3.0, WFS 2.0,
  ISO 19115/19139 — normative texts at https://www.ogc.org/standards/ and https://www.iso.org/
- lxml: https://lxml.org/ — GeoDjango GML/GEOS: https://docs.djangoproject.com/en/stable/ref/contrib/gis/

## MCP dependencies

None required. Live upstream services must not be called from an agent session; inspect stored
documents (`xml_backup` fields, `tests/django/test_data/`) instead. No MCP covers OGC standards —
`django-docs` (repo `opencode.json`) helps with the Django/XML plumbing around parsing, not with
the normative OGC/ISO text, which stays in the linked specifications above.

## Verification (commands in `backend/AGENTS.md`)

1. `../.venv/bin/flake8 <files>` from `backend/`.
2. Targeted unit tests mirroring the area: `tests/django/registry/mappers/`, `.../ows_lib/`,
   CSW suite under `tests/django/` — plus targeted behave: `features/csw/…` or
   `features/json:api/registry/service/<wms|wfs>/…` (quote paths; tiers in
   `backend/tests/behave/AGENTS.md`).
3. Mapping/persistence change: run the update/harvest candidate tests
   (`tests/django/registry/tests_update_candidates.py`) and check history of child objects.

## Security constraints

- Never let an OGC parameter select a host: operation URLs come from registered service records
  (`service.operation_urls`), never from the caller (proxy design, skill `mrmap-security`).
- Stored service credentials stay out of documents, exception texts and logs; refusals answer
  `ForbiddenException`/`DisabledException` without leaking why upstream failed.

## Explicit exceptions

- `mapbender_compatibility/` endpoints keep legacy shapes for compatibility — modernize only when
  an accepted issue asks.
- Skipped/missing behave coverage for parts of `/csw` and the proxy is known
  (`backend/tests/behave/AGENTS.md` "Where scenarios are missing"); adding a scenario there is
  welcome work, not a regression.
