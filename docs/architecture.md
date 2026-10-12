# Architecture

## Services

OGC services are represented by:

- WebMapService
- WebFeatureService
- CatalogueService

Core models:
backend/registry/models/service.py

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
- the last update job of a service waits for a review or failed
- the monitoring or update schedule of a service did not run at the expected
  time (see `backend/extras/scheduling.py`)
- the last harvesting run of a catalogue was aborted or left records behind

The derivation lives in `backend/registry/querys/alerts.py` and is answered per
service by the read only endpoints `api/registry/wms/<id>/alerts`,
`api/registry/wfs/<id>/alerts` and `api/registry/csw/<id>/alerts`, which name the
service they report about in their path. An alert disappears as soon as the state
behind it is fixed, which means that no model and no migration backs it. Because
every alert tells about the service it belongs to, the alerts of a service are
only answered to a user which may see that service.
