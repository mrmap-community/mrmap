# Architecture

## Services

OGC services are represented by:

- WebMapService
- WebFeatureService
- CatalogueService

Core models:
backend/registry/models/service.py

## Spatial discovery

The Service Explorer provides WMS, WFS and CSW tabs with a shared list/map view.
Searching the map viewport filters the entire collection; rectangles represent
only the current result page. Services without a recorded extent remain visible.
CSW rectangles describe the coverage of harvested metadata records.

DatasetMetadataRecord and ServiceMetadataRecord use the same explorer components
and support viewport searches over their bounding geometry. Service metadata
imports read geographic extents from ISO service identification elements.

Service list clients request `extent`, `element_count` and `can_edit` through
JSON:API sparse fieldsets. Extents and counts are derived in the page query, with
no geometry columns or migrations added. Clients that omit these fields retain
their existing response shape and do not run the coverage aggregate.

## Map contexts

MapContext exports exchange configured layer trees with the standalone viewer.
See [OWS Context exchange](ows-context.md) for the GeoJSON contract, independent
rendering/selection activation and legacy document normalization.

## Updating services

Update jobs:

- WebMapServiceUpdateJob
- WebFeatureServiceUpdateJob
- CatalogueServiceUpdateJob

Implementation:
backend/registry/models/update.py

Update jobs compare newly retrieved service metadata against the
currently persisted service.

Updates may create mappings requiring user confirmation:

- LayerMapping
- FeatureTypeMapping

WMS and WFS updates automatically apply additions of named layers or feature
types when every existing element is matched by identifier. Matched elements
keep their UUIDs and user configuration; additions use the existing inactive
and unsearchable defaults and record their promotion in history.

Removal-only updates also run automatically, subject to existing database
protection of referenced layers. Updates with both additions and removals
require review because an identifier change may represent a rename. Unnamed
WMS grouping additions require review as well; ambiguous groups are not matched
by their missing identifier. Confirming the mappings resumes the same update
job and preserves the identity of manually matched elements.

## Monitoring

Monitoring models are located in:

backend/registry/models/monitoring.py

Important concepts:

- WebMapServiceMonitoringRun
- GetCapabilitiesProbeResult
- GetMapProbeResult

## Security Proxy

Security Proxy models are located in:

backend/registry/models/security.py

Security rules to restrict the access to a registered service spartial or general:

- AllowedWebMapServiceOperation
- AllowedWebFeatureServiceOperation

If a service is securited, the service will be proxied by Mr.Map:

- WebMapServiceProxySetting
- WebFeatureServiceProxySetting

There is also a logging feature to count the responsed entities such as megapixels and feature types:

- WebMapServiceAnalyzedResponseLog
- WebFeatureServiceAnalyzedResponseLog

## Attention

Which states of a registered service need the attention of an administrator is
not persisted but derived from the runs and jobs of the service:

- the last monitoring run of a service did not pass
- an update of a service waits for a review or the last one came back broken
- the last harvesting run of a catalogue was aborted or left records behind

The derivation lives in `backend/registry/querys/alerts.py` and is annotated to
the services themselves, which answers it as attributes of a service resource:
`hasAlert`, `monitoringFailed`, `monitoringFailedAt`, `updateReviewRequired`,
`updateReviewRequiredAt`, `updateFailed` and `updateFailedAt` and, for a
catalogue, `harvestAborted`, `harvestIncomplete` and `harvestFailedAt`. Because
these are annotations of the services, a client filters, sorts and counts its
services by them like by any other attribute; the endpoints annotate them only
to a query which asks for them, because each is answered by a subquery. An alert
disappears as soon as the state behind it is fixed, which means that no model
and no migration backs it, and it is answered to exactly those users which may
see the service it tells about.

The schedules a service did not keep are not answered this way, because the time
a crontab promised a run at is calculated in python and not by the database: the
monitoring and update settings of a service answer their `runOverdue` instead
(see `backend/extras/scheduling.py`).

### Cross-service overview

`GET /api/registry/service-alerts` exposes the current problems of published
WMS, WFS and CSW services as a computed JSON:API `ServiceAlert` collection.
It reuses `registry/querys/alerts.py` annotations and `extras/scheduling.py`:
latest monitoring and update failures, pending update reviews (including dangling
candidates), harvesting failures/import errors, and enabled overdue schedules.
Candidates and their update jobs produce one review alert for the original service.

The endpoint requires authentication and scopes services with guardian view
permissions, including group and global permissions, before counting or filtering.
It supports `filter[severity]`, `filter[category]`, `filter[serviceType]`,
`filter[service]`, `sort=severity,-occurredAt` (also `occurred_at`) and ordinary
JSON:API pagination. `meta.pagination.count` counts problems, so one service can
contribute several alerts. IDs remain stable while a problem remains open.
`targetPath` opens the existing service workflow or update review; no state or
schema migration is introduced.

The app bar, dashboard and schema-driven attention list share this collection.
Monitoring completion, update job saves and harvesting transitions publish a
payload-free `resource/ServiceAlert` invalidation after commit. Clients refetch
their own scoped data, with a 20-second polling fallback that also detects
schedules becoming overdue. The indicator and dashboard card disappear at zero
and do not display cached counts on request errors. Collection and schedule
projection currently happen in memory before pagination; a deployment with many
services may need database-side aggregation in a later performance change.
