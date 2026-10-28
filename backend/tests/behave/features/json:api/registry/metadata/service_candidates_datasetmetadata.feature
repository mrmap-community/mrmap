@fixtures:test_keywords.json @fixtures:test_crs.json @fixtures:test_csw.json @fixtures:test_datasetmetadata.json
Feature: DatasetMetadataRecord Service Candidates Endpoint
    Curators learn which services can deliver a harvested record, before they register one.

    Background:
        Given I use the endpoint http://localhost:8000/api/registry/dataset-metadata/d8b50d33-2ad7-4a41-bd0d-2d518ea10fd4/service-candidates
        # the resolution answers plain JSON, like the live preview endpoints do
        Given I set the header "HTTP_ACCEPT" with value "application/json"
        Given no upstream answer is prepared

    Scenario: Discovery answers the endpoints the stored document advertises
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "status" with value "ok"
        Then I expect that response json has an attribute "file_identifier" with value "de.dwd.geoserver.fach.RBSN_RR"
        Then I expect that response json has an attribute "candidates.[0].url" with value "https://maps.dwd.de/geoserver/dwd/RBSN_RR/ows?service=wms&version=1.3.0&request=GetCapabilities"
        Then I expect that response json has an attribute "candidates.[0].state" with value "unvalidated"
        Then I expect that response json has an attribute "candidates.[0].preferred" with value "true"
        Then I expect that response json has an attribute "candidates.[1].derived" with value "true"
        Then I expect that response json has an attribute "candidates.[1].type_names.[0]" with value "RBSN_RR"
        Then the resolution has not contacted upstream

    Scenario: A record whose stored document is gone answers its state
        Given the stored document of the record is gone
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "status" with value "missing"
        Then I expect that response json has an attribute "candidates" with value "[]"
        Then the resolution has not contacted upstream

    Scenario: A url which the record never advertised is refused
        Given I use the endpoint http://localhost:8000/api/registry/dataset-metadata/d8b50d33-2ad7-4a41-bd0d-2d518ea10fd4/validate-service-candidate
        Given I set a queryparam "url" with value "https://example.org/an-endpoint-of-another-record"
        When I send the request with GET method
        Then I expect the response status is 422
        Then I expect that response json has an attribute "error" with value "not-advertised"
        Then the resolution has not contacted upstream

    Scenario: The validation of a derived endpoint confirms the hint of the record
        Given I use the endpoint http://localhost:8000/api/registry/dataset-metadata/d8b50d33-2ad7-4a41-bd0d-2d518ea10fd4/validate-service-candidate
        Given the endpoint "https://maps.dwd.de/geoserver/dwd/RBSN_RR/ows?service=wfs&version=2.0.0&request=GetCapabilities" answers these capabilities:
            """
            <WFS_Capabilities version="2.0.0" xmlns="http://www.opengis.net/wfs/2.0">
              <ServiceIdentification><ServiceType>WFS</ServiceType></ServiceIdentification>
              <FeatureTypeList>
                <FeatureType><Name>RBSN_RR</Name></FeatureType>
              </FeatureTypeList>
            </WFS_Capabilities>
            """
        Given I set a queryparam "url" with value "https://maps.dwd.de/geoserver/dwd/RBSN_RR/ows?service=wfs&version=2.0.0&request=GetCapabilities"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "state" with value "resolved"
        Then I expect that response json has an attribute "service_type" with value "WFS"
        Then I expect that response json has an attribute "matched_names.[0]" with value "RBSN_RR"
        Then only the endpoint the record advertised was asked

    Scenario: An unconfirmed hint stays a decision of the user
        Given I use the endpoint http://localhost:8000/api/registry/dataset-metadata/d8b50d33-2ad7-4a41-bd0d-2d518ea10fd4/validate-service-candidate
        Given the endpoint "https://maps.dwd.de/geoserver/dwd/RBSN_RR/ows?service=wfs&version=2.0.0&request=GetCapabilities" answers these capabilities:
            """
            <WFS_Capabilities version="2.0.0" xmlns="http://www.opengis.net/wfs/2.0">
              <ServiceIdentification><ServiceType>WFS</ServiceType></ServiceIdentification>
              <FeatureTypeList>
                <FeatureType><Name>ANOTHER_LAYER</Name></FeatureType>
              </FeatureTypeList>
            </WFS_Capabilities>
            """
        Given I set a queryparam "url" with value "https://maps.dwd.de/geoserver/dwd/RBSN_RR/ows?service=wfs&version=2.0.0&request=GetCapabilities"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "state" with value "ambiguous"
        Then I expect that response json has an attribute "unresolved_hints.[0]" with value "RBSN_RR"

    Scenario: An endpoint which answers an OGC exception reports its code
        Given I use the endpoint http://localhost:8000/api/registry/dataset-metadata/d8b50d33-2ad7-4a41-bd0d-2d518ea10fd4/validate-service-candidate
        Given the endpoint "https://maps.dwd.de/geoserver/dwd/RBSN_RR/ows?service=wfs&version=2.0.0&request=GetCapabilities" answers these capabilities:
            """
            <ows:ExceptionReport version="2.0.0" xmlns:ows="http://www.opengis.net/ows/1.1">
              <ows:Exception exceptionCode="OperationNotSupported">
                <ows:ExceptionText>nope</ows:ExceptionText>
              </ows:Exception>
            </ows:ExceptionReport>
            """
        Given I set a queryparam "url" with value "https://maps.dwd.de/geoserver/dwd/RBSN_RR/ows?service=wfs&version=2.0.0&request=GetCapabilities"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "state" with value "unavailable"
        Then I expect that response json has an attribute "detail" with value "exception-report:OperationNotSupported"
        Then the answer names no url to register

    Scenario: A delivering endpoint answers the url the registration asks for
        # the create serializer demands SERVICE, REQUEST and VERSION; the asked
        # url is handed over as a qualified request of what the document said,
        # which is what the registration form of the record is prefilled with
        Given I use the endpoint http://localhost:8000/api/registry/dataset-metadata/d8b50d33-2ad7-4a41-bd0d-2d518ea10fd4/validate-service-candidate
        Given the endpoint "https://maps.dwd.de/geoserver/dwd/RBSN_RR/ows?service=wfs&version=2.0.0&request=GetCapabilities" answers these capabilities:
            """
            <WFS_Capabilities version="2.0.0" xmlns="http://www.opengis.net/wfs/2.0">
              <ServiceIdentification><ServiceType>WFS</ServiceType></ServiceIdentification>
              <FeatureTypeList>
                <FeatureType><Name>RBSN_RR</Name></FeatureType>
              </FeatureTypeList>
            </WFS_Capabilities>
            """
        Given I set a queryparam "url" with value "https://maps.dwd.de/geoserver/dwd/RBSN_RR/ows?service=wfs&version=2.0.0&request=GetCapabilities"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "registration_url" with value "https://maps.dwd.de/geoserver/dwd/RBSN_RR/ows?service=WFS&version=2.0.0&request=GetCapabilities"

    Scenario: Reading the candidates grants no right to register a service
        Given a user which may read records but may not register services
        Given I am logged in as Reader1 with password Reader1
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "candidates.[0].url" with value "https://maps.dwd.de/geoserver/dwd/RBSN_RR/ows?service=wms&version=1.3.0&request=GetCapabilities"
        Given I use the endpoint http://localhost:8000/api/registry/wms
        # the resolution answers plain json, the registry answers json:api, so
        # the media type of the registration is named by the request which is
        # one, not by the background of the record
        Given I set the header "HTTP_ACCEPT" with value "application/vnd.api+json"
        Given I set the content type of the request to application/vnd.api+json
        Given I set the request payload to:
            """
            {
                "data": {
                    "type": "WebMapService",
                    "attributes": {
                        "get_capabilities_url": "https://maps.dwd.de/geoserver/dwd/RBSN_RR/ows?service=WMS&version=1.3.0&request=GetCapabilities",
                        "collect_metadata_records": "true"
                    },
                    "relationships": {
                        "owner": {
                            "data": {
                                "id": "1",
                                "type": "Organization"
                            }
                        }
                    }
                }
            }
            """
        When I send the request with POST method
        Then I expect the response status is 403
        Then I expect that response json has an attribute "errors.[0].code" with value "permission_denied"
