# OWS Context exchange

`GET /mrmap-proxy/ows/<id>` exports the [OWS Context GeoJSON profile](https://docs.ogc.org/is/14-055r2/14-055r2.html).
Resources carry `properties.offerings`, using
`http://www.opengis.net/spec/owc-geojson/1.0/req/wms`. GetMap and GetFeatureInfo
share an offering but retain independent operation `active` flags, layer URLs and
selection settings. The configured rendering style appears in both `STYLES` and
the offering's `styles` list. Scale limits use `minscaledenominator` and
`maxscaledenominator`, including zero when configured.

The context uses `lang` and `subtitle`. Context and resource IDs are absolute
URLs at the endpoint; model exports without a request use `urn:mrmap:` IDs.
Modification times come from each object's latest history record. Objects with
no history use the export time as an estimate. An `authors` list is included
when that history record identifies a user; no author is invented otherwise.

Resources are exported in MPTT preorder with numbered folder paths (`/0`,
`/0/0`, `/0/1`). This retains sibling order and nesting at arbitrary depth without
requiring nested GeoJSON features. IDs remain stable when a resource moves.

## Existing documents

No database migration is needed. Re-exporting a stored MapContext produces the
corrected document. The viewer's import validation normalizes legacy `language`,
`subtilte`, camelCase scale fields and top-level resource `offerings`. It accepts
both previous WMS offering identifiers (`owc` and `owc-atom`) and emits
`owc-geojson` for newly created offerings. Plain split legacy WMS offerings are
combined so both operations remain available. Normalization preserves operation
activation and reports recoveries as warnings without modifying the input.

Legacy documents with empty timestamps or duplicate folder paths remain invalid:
those documents do not contain enough information to reconstruct modification
times or the original hierarchy. Re-export them from the stored MapContext.
Unknown extension fields and offerings remain intact.

The backend regression tests cover the endpoint and model serialization. The
frontend's `backend-context.json` fixture exercises the export shape, nested
resources, styles, scales, separate operation endpoints and independent operation
activation through validation, viewer consumption and JSON round trips.
