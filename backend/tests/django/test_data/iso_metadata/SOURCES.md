# Sources of the ISO metadata test documents

`dataset.xml` / `service.xml` are the dataset/service records the ISO mapper tests
were written against (`de.dwd.geoserver.fach.RBSN_FF` of the DWD and a Bavarian
service record).

The ten `*.xml` records below are real `hierarchyLevel=application` `MD_Metadata`
records, harvested 2026-11-03 (UTC) as raw element bytes from four live CSWs with
the exact request shape of `CatalogueServiceClient.get_records_request()`
(`typeNames=gmd:MD_Metadata`, FILTER constraint `type = 'application'`). They are
the spike samples of issue #825 and drive the `("ISO", "application")` mapping
tests in `tests/django/registry/mappers/tests_iso_application_mapping.py`.

| File | Catalogue (implementation) | fileIdentifier | Why it is here |
|---|---|---|---|
| `gdi-bw-01.xml` | GDI-BW (GeoNetwork) | 270C4127-5EE3-477D-A3E4-2834649CD57C | ELWIS; machine-JSON licence inside `otherConstraints` |
| `gdi-bw-02.xml` | GDI-BW (GeoNetwork) | 5E243836-9359-40AD-B887-E0A526F3979E | PEGELONLINE; two bounding boxes, update frequency `daily` |
| `gdi-bw-04.xml` | GDI-BW (GeoNetwork) | 78538593-0e19-a5b7-c64a-756898eac073 | **reference fixture** (Geoportal Schwäbisch Hall): populates title, abstract, 33 keywords, both contacts, 7 topicCategories, bbox and citation identifier in one record |
| `gdi-de-01.xml` | gdi.de GDK (GeoNetwork) | 17517355-a52a-4823-add7-1d5c99536eeb | Kreis Herford; reference system `EPSG:25832` |
| `gdi-de-03.xml` | gdi.de GDK (GeoNetwork) | 18923033-6CCD-11D3-98D2-0060086FDABA | five bounding boxes; open-ended TimePeriod (empty `endPosition`) |
| `gdi-de-04.xml` | gdi.de GDK (GeoNetwork) | 19c44805-c445-4f4a-8420-e71797bf4088 | seven *empty* `gmd:resourceConstraints` elements |
| `gdi-de-05.xml` | gdi.de GDK (GeoNetwork) | 12f10205-53c7-459c-bf6e-40e67ccd0c00 | Unfallatlas; two pointOfContacts, `useConstraints` code `license`, open-ended TimePeriod |
| `hessen-01.xml` | Geoportal Hessen (pycsw) | 0a7cb996-69d1-69bd-9e64-da089a3bb1e4 | equivalentScale denominator, closed TimePeriod, statement-less LI_Lineage, keyword-registry UUID as first keyword |
| `hessen-03.xml` | Geoportal Hessen (pycsw) | 1a83899e-8bad-5be4-1ec3-7486a9ec3d35 | invalid topicCategory text `no category defined till now!` |
| `geocat-01.xml` | geocat.ch (GeoNetwork, CH profile) | 804bc4fd-a3d9-4b04-817b-c36bcf172617 | documented edge case: `CHE_MD_Metadata` roots, no keywords, no contacts at all — rejected by the mapper's `MD_Metadata` detection (follow-up of #825; must stay a clean error, not a crash) |

Endpoints and full per-record XPath evidence (titles, extents, constraints per
sample): `#825` spike notes on
<https://github.com/mrmap-community/mrmap/issues/825> and the decision note on
<https://github.com/mrmap-community/mrmap/issues/826>.
