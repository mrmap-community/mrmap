#!/bin/bash
for i in {1..100}
do
   curl -X 'POST' \
  'http://localhost:8001/api/v1/registry/jobs/register-ogc-service/' \
  -H 'accept: application/vnd.api+json' \
  -H 'Content-Type: application/vnd.api+json' \
  -H 'X-CSRFToken: oQUAbBplFItD3reRVQmV6cHEdeiir3dYF6s90GSKU0Uz1eu7HPzxqMwQlmTxlY51' \
  -d '{
  "data": {
    "type": "RegisterOgcServiceJob",
    "attributes": {
      "get_capabilities_url": "https://maps.dwd.de/geoserver/wms?SERVICE=WMS&VERSION=1.3.0&REQUEST=GetCapabilities",
      "collect_linked_metadata": true
    },
    "relationships": {
      "registering_for_organization": {
        "data": { "type": "Organization", "id": "2c5fcad7-6542-4861-ab13-d476ba8cd132" }
      }
    }
  }
}'
done