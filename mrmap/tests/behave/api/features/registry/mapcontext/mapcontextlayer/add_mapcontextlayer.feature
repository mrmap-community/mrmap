Feature: MapContextLayer Add Endpoint
    As an API client,
    I want to add mapcontextlayers,
    so that I can configure map applications.

    Background: Setup baseurl, content-type and payload
        Given I use the endpoint http://localhost:8000/api/v1/registry/mapcontextlayers/
        Given I set the content type of the request to application/vnd.api+json
        Given I set the request payload to:
            """
            {
                "data": {
                    "type": "MapContextLayer",
                    "attributes": {
                        "title": "mc2_node1.2.1"
                    },
                    "relationships": {
                        "parent": {
                            "data": {
                                "type": "MapContextLayer",
                                "id": "8"
                            }
                        },
                        "mapContext": {
                            "data": {
                                "type": "MapContext",
                                "id": "2"
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

    Scenario: Can't add as anonymous user
        When I send the request with POST method
        Then I expect the response status is 403
