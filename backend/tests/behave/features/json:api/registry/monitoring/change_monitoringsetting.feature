Feature: WebMapServiceMonitoringSetting Change Endpoint
    As an API client,
    I want to change monitoring setting,
    so that I can modify existing map applications.

    Background: Setup baseurl, content-type and payload
        Given I use the endpoint http://localhost:8000/api/registry/monitoring/wms-monitoring-settings/1
        Given I set the content type of the request to application/vnd.api+json
        Given I set the request payload to:
            """
            {
                "data": {
                    "type": "WebMapServiceMonitoringSetting",
                    "id": 1,
                    "attributes": {
                        "scheduleInterval": "*/10 * * * *"
                    },
                    "relationships": {
                        "service": {
                            "data": {
                                "id": "cd16cc1f-3abb-4625-bb96-fbe80dbe23e3",
                                "type": "WebMapService"
                            }
                        }
                    }
                }
            }
            """

    Scenario: Can change as authenticated user with permissions
        Given I am logged in as User1 with password User1
        When I send the request with PATCH method
        Then I expect the response status is 200
        And I expect that response json has an attribute "data.attributes.scheduleInterval" with value "*/10 * * * *"

    Scenario: Can't change as authenticated user without permissions
        Given I am logged in as User2 with password User2
        When I send the request with PATCH method
        Then I expect the response status is 403

    Scenario: Can't change as anonymous user
        When I send the request with PATCH method
        Then I expect the response status is 403
