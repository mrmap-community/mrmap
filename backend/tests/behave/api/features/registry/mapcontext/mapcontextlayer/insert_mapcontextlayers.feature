Feature: MapContextLayer Insert Endpoint
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
                        "target": 8,
                        "position": "left",
                        "title": "new mc2_node1.2"
                    },
                    "relationships": {
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

    Scenario: Can insert as authenticated user with permissions for the target object and add permissions
        Given I am logged in as User2 with password User2
        When I send the request with POST method
        Then I expect the response status is 201

    Scenario: Can't insert as authenticated user without permissions for the target object and add permissions
        Given I am logged in as User1 with password User1
        When I send the request with POST method
        Then I expect the response status is 403

    Scenario: Can't insert as anonymous user
        When I send the request with POST method
        Then I expect the response status is 401
