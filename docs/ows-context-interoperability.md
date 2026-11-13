# OWS Context interoperability and external resources

**Status:** Proposed documentation clarification for issues #1284 and #1280, following the already accepted maintainer policy #1314 and merged PR #1317 (D3). This document defines the implementation acceptance contract; it does not assert that all features are implemented or that a pending PR is approved.

**Standards:** [OGC OWS Context conceptual model 12-080r2](https://www.ogc.org/standards/owc/), [OGC OWS Context GeoJSON 14-055r2](https://docs.ogc.org/is/14-055r2/14-055r2.html).

## Scope and ownership

MrMap's **MapContext/OWS Context** is a standards-open container for configured resources, including valid public external offerings regardless of service registration. **Discovery** (#669) may first resolve WMS/WFS metadata references, but must not narrow the generic context's representation or interchange to these two protocols.

- **v1 (#1280/#1283–#1285):** generic context entries, OWS Context **GeoJSON** import/persist/export and viewer state; preserve any valid core/extension offering, regardless of renderer support. Do not implement Atom serialization implicitly. A later Atom encoding adapter may reuse the generic model but needs its own explicit scope and tests.
- **v2 (#1291):** revisions and managed synchronization; preserve these generic context entries and their identities.
- **Registry (#669/#1256):** a managed MrMap WMS/WFS/CSW service has its own PK and permissions; a context entry does not require one. Merely adding an external offering does not register a service or create an ISO `MetadataRelation`.
- **No second parser/serializer, duplicate permission store or GenericForeignKey**. Use existing `ows-lib`, `react-ows-lib`, `mptt2`, typed FKs and history.

## Separate identities

| Identity | Meaning | Rule |
| --- | --- | --- |
| MapContext `identifier` | MrMap context UUID and stable latest URI | Persistent and immutable across edits (#1282) |
| GeoJSON `Feature.id` | Context **resource** IRI/identifier | Preserve a valid imported ID; generate stable IDs for newly authored entries; no registration prerequisite |
| `offerings[].code` | OWS Context offering/profile type URI | Preserve exact valid code and profile-specific data |
| Registered service/Layer/FeatureType PK | Managed MrMap registry object | Optional for external offerings |
| ISO metadata `fileIdentifier` | Metadata **document** identity | Not the dataset or OWC Feature ID |
| ISO dataset `(code, code_space)` | Verified dataset resource identity | Optional provenance for context entries, never fabricated |

Preserve distinct resources and offerings, even if they share a URL, a dataset identifier or a metadata document. Invalid or duplicate imported IDs require an explicit deterministic validation/recovery policy; do not silently collapse them or rewrite them as registered service PKs.

## Exchange and profile coverage

The GeoJSON encoding defines the core and recognized offering classes:
**WMS, WFS, WCS, WPS, WMTS, CSW, GML, KML, GeoTIFF, GMLJP2 and GMLCOV**. Valid extension/unknown offering codes and namespaced fields permitted by the standard also remain representable.

A context resource may have multiple `offerings`; each offering may hold `operations`, `contents` (inline or referenced), `styles`, type/profile-specific fields and permitted extensions. Preserve valid GeoJSON resource metadata links, including `features[i].properties.links.via`, source URIs and original external IDs. **Do not delete a standard-compliant imported metadata link**. v1 does *not* automatically author new ISO metadata relations in exported contexts; this authoring restriction does not override lossless import/export.

WMS GetMap/GetFeatureInfo and WFS GetFeature remain independent. For unsupported live protocols, the viewer shows an explicit unsupported rendering/execution state while retaining the imported entry and its payload. A valid context entry is not the same thing as a verified operational dataset or a working browser fetch.

**Semantic round trip**, not arbitrary byte identity, is required for import → save → reopen → export. Preserve external URI/IRI identifiers, meaningful array order, offering codes, operation parameters, content, styles, links, valid extensions, typed values and source provenance. JSON object ordering and whitespace are not significant. Byte stability only applies to **explicit canonical fixtures** where such a contract is defined. An intentional security redaction is a **degraded export**, not a falsely claimed complete authenticated round trip.

## External resource admission and security (#1281)

- Public, safe external resources may be added without registration, even if not renderable. A user may still access context metadata even where a live operation is unsupported.
- Effective context sharing and export permissions inherit restrictions from **registered managed resources and private/authenticated/credential-bearing external offerings**. An external URL is not automatically safe/public simply because it can be stored as text; unknown disclosure status must not silently grant public sharing. Re-evaluate on entry or source/security changes.
- Never expose authorization headers, session credentials, signed URL tokens, URL userinfo or private addresses in unauthorized/public export, logs or a cross-user proxy URL. Security redaction must explicitly preserve a degraded/credential-required entry rather than removing it.
- Browser fetches may fail due to CORS; this must not trigger an unbounded server-side fallback proxy. For any backend resolution/federation fetch, constrain schemes/hosts, DNS and redirects (SSRF prevention), request time/size/number, response processing, authorization and remote headers. Authenticated resources must not leak credentials to unrelated origins.
- If an offering is safe to store/export but cannot be retrieved for display, report the reason accurately (unsupported renderer, missing credentials, denied authorization, CORS/transport error, invalid operation, etc.).

**Federated CSW search (#1310)** is a separate execution capability: configured/authorized source catalogues are searched with bounded requests; permission to add external resources to an OWS Context is **not** carte blanche for the backend to crawl user-supplied URLs. User-provided ad-hoc CSW sources can be considered separately with an explicit security policy.

## Acceptance tests

1. Public external-only context and mixed registered/external context do not implicitly create a registry service or ISO relation; save/reopen/export works.
2. Generic fixtures for **all 11 named GeoJSON profile codes**, an unknown permitted extension, source metadata `links.via`, multiple offerings, styles, inline and referenced content and independent WMS/WFS operations remain semantically equal after round trip.
3. Imported valid resource IDs remain stable; invalid/duplicate IDs have documented deterministic failure/recovery behavior.
4. Unsupported renderer is reported but non-renderable offerings are still retained and exported.
5. Public and private/authenticated external entries, signed URLs, authorization flips, and unauthorized readers yield correct inherited security, explicitly degraded entries and no secret exfiltration.
6. Safe remote request handling validates SSRF/redirect/DNS boundaries, budgets, authenticated origin isolation and CORS limitations.
7. Legacy WMS/WFS `backend-context.json` fixtures remain interoperable. Atom support is *not* falsely claimed in v1.
