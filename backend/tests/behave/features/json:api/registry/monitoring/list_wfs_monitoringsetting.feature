@fixtures:test_wfs.json @fixtures:test_keywords.json
Feature: WebFeatureServiceMonitoringSetting List Endpoint
    As an API client,
    I want to list monitoring settings,
    so that I can see how a web feature service is monitored.

    Background: Setup baseurl, content-type and payload
        Given I use the endpoint http://localhost:8000/api/registry/monitoring/wfs-monitoring-settings

    Scenario: Can retrieve list as anonymous user
        When I send the request with GET method
        Then I expect the response status is 200
        And I expect that response json has an attribute "meta.pagination.count" with value "0"

    Scenario: Lists the setting created for a service
        Given I am logged in as User1 with password User1
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
        When I send the request with POST method
        Then I expect the response status is 201
        When I send the request with GET method
        Then I expect the response status is 200
        And I expect that response json has an attribute "meta.pagination.count" with value "1"