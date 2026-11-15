@fixtures:test_organizations.json
Feature: Resource ownership at registration
    As an API client,
    I want a registered service to be owned by a named organization,
    so that the question "which organization owns this?" has one answer (#733).

    Background: Setup baseurl, content-type and a registration payload
        Given I use the endpoint http://localhost:8000/api/registry/wms
        Given I set the content type of the request to application/vnd.api+json
        Given the registration task runs directly and serves its capabilities from the test data
        Given I am logged in as User1 with password User1

    Scenario: The named owner organization owns the registered service
        Given User1 is member of the organization "Fixture Organization"
        Given I set the request payload to:
            """
            {
                "data": {
                    "type": "WebMapService",
                    "attributes": {
                        "get_capabilities_url": "http://some-service.de?REQUEST=GetCapabilities&SERVICE=WMS&VERSION=1.3.0",
                        "collect_metadata_records": "false"
                    },
                    "relationships": {
                        "owner": {
                            "data": {
                                "id": "901",
                                "type": "Organization"
                            }
                        }
                    }
                }
            }
            """
        When I send the request with POST method
        Then I expect the response status is 202
        Then the WMS which this run registered is owned by the organization "Fixture Organization"

    Scenario: The only membership decides when the payload names no owner
        Given User1 is member of the organization "Fixture Organization"
        Given I set the request payload to:
            """
            {
                "data": {
                    "type": "WebMapService",
                    "attributes": {
                        "get_capabilities_url": "http://some-service.de?REQUEST=GetCapabilities&SERVICE=WMS&VERSION=1.3.0",
                        "collect_metadata_records": "false"
                    }
                }
            }
            """
        When I send the request with POST method
        Then I expect the response status is 202
        Then the WMS which this run registered is owned by the organization "Fixture Organization"

    Scenario: An ambiguous membership is refused instead of guessed
        Given User1 is member of the organization "Fixture Organization"
        Given User1 is also member of a second organization "Second Fixture Amt"
        Given I set the request payload to:
            """
            {
                "data": {
                    "type": "WebMapService",
                    "attributes": {
                        "get_capabilities_url": "http://some-service.de?REQUEST=GetCapabilities&SERVICE=WMS&VERSION=1.3.0",
                        "collect_metadata_records": "false"
                    }
                }
            }
            """
        When I send the request with POST method
        Then I expect the response status is 400
        Then I expect that response json has an attribute "errors.[0].code" with value "invalid"
        Then no service was registered

    Scenario: An organization the user does not belong to is refused as owner
        Given I set the request payload to:
            """
            {
                "data": {
                    "type": "WebMapService",
                    "attributes": {
                        "get_capabilities_url": "http://some-service.de?REQUEST=GetCapabilities&SERVICE=WMS&VERSION=1.3.0",
                        "collect_metadata_records": "false"
                    },
                    "relationships": {
                        "owner": {
                            "data": {
                                "id": "901",
                                "type": "Organization"
                            }
                        }
                    }
                }
            }
            """
        When I send the request with POST method
        Then I expect the response status is 400
        Then I expect that response json has an attribute "errors.[0].code" with value "invalid"
        Then no service was registered
