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