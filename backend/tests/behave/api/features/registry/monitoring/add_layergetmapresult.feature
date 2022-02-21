Feature: LayerGetMapResult Add Endpoint
    As an administrator,
    I want to tigger checking of GetMap operation,
    so that I see new monitoing result.

    Background: Setup baseurl, content-type and payload
        Given I use the endpoint http://localhost:8000/api/v1/registry/monitoring/layer-get-map-result/
        Given I set the content type of the request to application/vnd.api+json
        Given I mock the function "delay" of the module "registry.tasks.monitoring.check_get_map_operation" with return value as object
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
                    "type": "LayerGetMapResult",
                    "relationships": {
                        "layer": {
                            "data": {
                                "id": "16b93d90-6e2e-497a-b26d-cadbe60ab76e",
                                "type": "Layer"
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
                    "type": "LayerGetMapResult",
                    "relationships": {
                        "layer": {
                            "data": {
                                "id": "16b93d90-6e2e-497a-b26d-cadbe60ab76e",
                                "type": "Layer"
                            }
                        }
                    }
                }
            }
            """
        When I send the request with POST method
        Then I expect the response status is 401




