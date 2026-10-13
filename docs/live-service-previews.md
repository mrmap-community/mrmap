# Live service previews

WMS, WFS and CSW overview pages have an expandable **Live preview** card. Expansion
activates it; collapsing or leaving the page cancels pending browser requests.
Stored service information remains visible. Each preview has its own context;
only explicitly opening the standalone viewer transfers a WMS selection and view.
Existing viewer layers are retained.

Select a registered layer or feature type, then pan, zoom, refresh or use **Zoom to
selection**. Missing or invalid extents leave the default viewport usable. The
first increment uses WGS84 (EPSG:4326), PNG/JPEG for WMS and advertised GeoJSON for
WFS. Other formats/CRS have an explicit unsupported state. GML conversion is a
follow-up. WFS responses are always labelled as a bounded preview whose
completeness is not established. Attributes and identify results are rendered as
text. Queryable WMS layers provide a GetFeatureInfo result link and a keyboard
accessible identify-at-centre action, as well as a map context-menu action.

CSW pages show fresh ISO dataset/service records rather than the harvested
Records tab. Their mapped rectangles are **metadata coverage, current page
only**, not features or the catalogue's coverage. Records without coverage are
still readable. Data-preview links require the same file identifier in a record
harvested through this registered CSW and an existing registry metadata relation
to an active, accessible layer or feature type. Distribution URLs are never
registered or requested automatically.

## Read-only API

The additive actions are `GET /api/registry/wms/{id}/preview`,
`GET /api/registry/wfs/{id}/preview` and `GET /api/registry/csw/{id}/preview`.
They are exposed in OpenAPI as `preview_WebMapService`,
`preview_WebFeatureService` and `preview_CatalogueService`. They use ordinary
MrMap authentication and require the service's object `view` permission.
Successful and preview-error responses are ordinary JSON, with `Cache-Control:
no-store`; they are not new JSON:API resources. They never run persistence,
harvesting, update jobs or general proxy response logging. No migration is needed.

WMS/WFS parameters:

| Parameter | Meaning |
| --- | --- |
| `selection` | Exact registered named-layer/feature-type identifier |
| `bbox` | WGS84 `west,south,east,north`, independent of upstream axis order |
| `width`, `height` | WMS dimensions, defaults 800 × 400; each at most 2048 |
| `identify` | `true` for WMS GetFeatureInfo |
| `x`, `y` | Identify pixel coordinates in the same viewport |

Omitting `bbox` returns `configuration: {extent, queryable}` and
`discovery: "stored"`, without requesting capabilities upstream. This is
explicitly labelled stored discovery. With `bbox`, responses add `source` and
`fetchedAt` (last successful fetch), and either a base64 `image` data URL,
GeoJSON `features` with `limit: 500, limited: true`, or identify text `info`.
Requests use version-correct WMS axis ordering and WFS type/count/BBOX parameters.
Each WFS request contains one type and a viewport filter. Older spatially
restricted WFS versions are rejected rather than forwarded unrestricted.

CSW accepts a one-based `start` position (default 1, at most 1,000,000).
GetRecords requests use ISO 19139 full results and at most 25 records.
Responses contain `records: [{identifier, title, abstract, extent, previews}]`,
`start`, `next` (0 at the end), `matched`, `pageSize`, `source`, and `fetchedAt`.
Verified links are `{protocol, serviceId, selection, title}`. The browser keeps
previous positions for navigation; the map shows only the current page.
Unsupported response schemas, invalid pagination and excess records are rejected.
ISO mapping is reused only for field parsing, without the persistence handler.

Preview errors contain `{"error": "code"}`. Codes include `denied`, `disabled`,
`unavailable`, `ogc`, `malformed`, `format`, `crs`, `schema`, `extent`, `limit`,
`stale`, `discovery`, `operation`, `identify`, and `spatialVersion`. Authentication
and object-permission failures also use DRF's ordinary error responses. Invalid
request parameters return 400, unsupported responses 422, disabled services 423,
upstream failures/limits 502, and denied access 403. Both languages explain these
states and offer retry where appropriate.

## Request bounds and access

Preview-specific upstream reads limit decoded responses to 8 MiB, use 3-second
connect/read timeouts and a 15-second elapsed download budget (checked between
reads). Redirects are refused. Browser requests debounce by 250 ms; query keys
isolate service, selection, page and viewport, and obsolete requests receive an
abort signal. Server work already sent upstream can finish within its limits
after browser cancellation.

Registered operation-specific endpoints and stored upstream credentials are
used. Caller MrMap tokens and browser cookies are not copied upstream. Preview
requests reuse proxy authorization and WMS spatial masks. WFS spatial filters
combine the viewport with **only the caller's** allowed areas. Unsupported
versions/geometry definitions fail closed. Spatially restricted WMS identify
requires an entirely authorized viewport in this increment; partial-viewport
identify fails closed. General-purpose proxy limits remain unchanged.

The shared proxy dispatch now selects the requested operation/method, and OWS
clients prepare requests through their sessions so stored authentication applies.
WFS XML query namespaces, count, output format and combined spatial filters are
retained. Coordinates at zero are valid ISO extent boundaries; invalid or
reversed extents are omitted. GeoJSON CRS and geometries are checked before
rendering. These shared corrections are covered by backend regressions.

Protocol references: [OGC WMS](https://www.ogc.org/standards/wms/),
[WFS request parameters](https://docs.geoserver.org/main/en/user/services/wfs/reference/).
