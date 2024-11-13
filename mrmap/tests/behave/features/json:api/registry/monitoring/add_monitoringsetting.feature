Feature: WebMapServiceMonitoringSetting Add Endpoint
    As an API client,
    I want to add catalogue services,
    so that I can manage them with Mr.Map.

    Background: Setup baseurl, content-type and payload
        Given I use the endpoint http://localhost:8000/api/registry/monitoring/wms-monitoring-settings
        Given I set the content type of the request to application/vnd.api+json

    Scenario: Can add as authenticated user
        Given I am logged in as User1 with password User1
        Given I set the request payload to:
            """
            {
                "data": {
                    "type": "WebMapServiceMonitoringSetting",
                    "attributes": {
                        "name": "some new setting"
                    },
                    "relationships": {
                        "service": {
                            "data": {
                                "id": "cd16cc1f-3abb-4625-bb96-fbe80dbe23e3",
                                "type": "WebMapService"
                            }
                        },
                        "crontab": {
                            "data": {
                                "id": "1",
                                "type": "CrontabSchedule"
                            }
                        }
                    }
                }
            }
            """
        When I send the request with POST method
        Then I expect the response status is 201

    Scenario: Can't add as anonymous user
        Given I set the request payload to:
            """
            {
                "data": {
                    "type": "WebMapServiceMonitoringSetting",
                    "attributes": {
                        "name": "some new setting"
                    },
                    "relationships": {
                        "service": {
                            "data": {
                                "id": "cd16cc1f-3abb-4625-bb96-fbe80dbe23e3",
                                "type": "WebMapService"
                            }
                        },
                        "crontab": {
                            "data": {
                                "id": "1",
                                "type": "CrontabSchedule"
                            }
                        }
                    }
                }
            }
            """
        When I send the request with POST method
        Then I expect the response status is 403

