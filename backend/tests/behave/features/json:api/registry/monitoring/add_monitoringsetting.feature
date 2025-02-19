Feature: WebMapServiceMonitoringSetting Add Endpoint
    As an API client,
    I want to add monitoring setting,
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
                    "name": "some new setting",
                    "getCapabilitiesProbes": {
                        "data": [
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
                        ]
                    },
                    "getMapProbes": {
                        "data": [
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
                    }
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
        When I send the request with POST method
        Then I expect the response status is 201

    Scenario: Can't add as anonymous user
        Given I set the request payload to:
            """
            {
                "data": {
                    "type": "WebMapServiceMonitoringSetting",
                    "attributes": {
                        "name": "some new setting",
                        
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
        When I send the request with POST method
        Then I expect the response status is 403

