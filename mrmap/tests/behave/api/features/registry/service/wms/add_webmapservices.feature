Feature: WebMapService Add Endpoint
    As an API client,
    I want to add web map services,
    so that I can manage them with Mr.Map.

    Background: Setup baseurl, content-type and payload
        Given I use the endpoint http://localhost:8000/api/v1/registry/wms/
        Given I set the content type of the request to application/vnd.api+json
        Given I mock the function "delay" of the module "registry.tasks.service.build_ogc_service" with return value as object
            """
            {
                "id": "62832ac8-692d-4a8b-b8d1-22cd22f7386c"
            }
            """

    Scenario: Can add as authenticated user
        Given I am logged in as User1 with password User1
        Given I set the request payload to:
            """
            {
                "data": {
                    "type": "WebMapService",
                    "attributes": {
                        "get_capabilities_url": "http://some-service.de?REQUEST=GetCapabilities&SERVICE=WMS&VERSION=1.3.0",
                        "collect_metadata_records": "true"
                    },
                    "relationships": {
                        "owner": {
                            "data": {
                                "id": "4",
                                "type": "Organization"
                            }
                        }
                    }
                }
            }
            """
        When I send the request with POST method
        Then I expect the response status is 202

    Scenario: Can't add as anonymous user
        Given I set the request payload to:
            """
            {
                "data": {
                    "type": "WebMapService",
                    "attributes": {
                        "get_capabilities_url": "http://some-service.de?REQUEST=GetCapabilities&SERVICE=WMS&VERSION=1.3.0",
                        "collect_metadata_records": "true"
                    },
                    "relationships": {
                        "owner": {
                            "data": {
                                "id": "4",
                                "type": "Organization"
                            }
                        }
                    }
                }
            }
            """
        When I send the request with POST method
        Then I expect the response status is 403

    Scenario: Wrong capabilities url
        Given I am logged in as User1 with password User1
        Given I set the request payload to:
            """
            {
                "data": {
                    "type": "WebMapService",
                    "attributes": {
                        "get_capabilities_url": "http://some-service.de?SERVICE=WMS&VERSION=1.3.0",
                        "collect_metadata_records": "true"
                    },
                    "relationships": {
                        "owner": {
                            "data": {
                                "id": "4",
                                "type": "Organization"
                            }
                        }
                    }
                }
            }
            """
        When I send the request with POST method
        Then I expect the response status is 400


