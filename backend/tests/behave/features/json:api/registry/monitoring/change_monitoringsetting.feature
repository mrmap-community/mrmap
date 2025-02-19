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
                        "name": "some new setting",
                        "getCapabilitiesProbes": [
                            {
                                "type": "GetCapabilitiesProbe",
                                "attributes": {
                                    "timeout": 30,
                                    "checkResponseIsValidXml": true,
                                    "checkResponseDoesContain": [
                                        "title>",
                                        "abstract>"
                                    ]
                                }
                            }
                        ],
                        "getMapProbes": [
                            {
                                "type": "GetMapProbe",
                                "attributes": {
                                    "timeout": 30,
                                    "height": 256,
                                    "width": 256,
                                    "checkResponseIsImage": true
                                },
                                "relationships": {
                                    "layers": {
                                        "data": [
                                            {
                                                "id": "16b93d90-6e2e-497a-b26d-cadbe60ab76e",
                                                "type": "Layer"
                                            }
                                        ]
                                    }
                                }
                            }
                        ]
                    },
                    "relationships": {
                        "crontab": {
                            "data": {
                                "id": 1,
                                "type": "CrontabSchedule"
                            }
                        },
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

    Scenario: Can't change as authenticated user without permissions
        Given I am logged in as User2 with password User2
        When I send the request with PATCH method
        Then I expect the response status is 403

    Scenario: Can't change as anonymous user
        When I send the request with PATCH method
        Then I expect the response status is 403
