@fixtures:test_wfs.json @fixtures:test_keywords.json
Feature: WebFeatureServiceMonitoringSetting Add Endpoint
    As an API client,
    I want to add monitoring setting,
    so that I can monitor a web feature service.

    Background: Setup baseurl, content-type and payload
        Given I use the endpoint http://localhost:8000/api/registry/monitoring/wfs-monitoring-settings
        Given I set the content type of the request to application/vnd.api+json
        Given I set the request payload to:
            """
            {
                "data": {
                    "type": "WebFeatureServiceMonitoringSetting",
                    "attributes": {
                        "scheduleInterval": "*/5 * * * *"
                    },
                    "relationships": {
                        "service": {
                            "data": {
                                "id": "9cc4889d-0cd4-4c3b-8975-58de6d30db41",
                                "type": "WebFeatureService"
                            }
                        }
                    }
                }
            }
            """

    Scenario: Can add as authenticated user
        Given I am logged in as User1 with password User1
        When I send the request with POST method
        Then I expect the response status is 201
        And I expect that response json has an attribute "data.attributes.scheduleInterval" with value "*/5 * * * *"

    Scenario: Can't add as anonymous user
        Given I am an anonymous user
        When I send the request with POST method
        Then I expect the response status is 403
        And I expect that response json has an attribute "errors.[0].code" with value "not_authenticated"