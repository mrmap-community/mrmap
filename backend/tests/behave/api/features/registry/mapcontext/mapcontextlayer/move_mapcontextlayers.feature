Feature: MapContextLayer Move Endpoint
    As an API client,
    I want to add mapcontextlayers,
    so that I can configure map applications.

    Background: Setup baseurl, content-type and payload
        Given I use the endpoint http://localhost:8000/api/v1/registry/mapcontextlayers/8/
        Given I set the content type of the request to application/vnd.api+json
        Given I set the request payload to:
            """
            {
                "data": {
                    "type": "MapContextLayer",
                    "attributes": {
                        "target": 7,
                        "position": "first-child"
                    }
                }
            }
            """

    Scenario: Can move as authenticated user
        Given I am logged in as User2 with password User2
        When I send the request with PATCH method
        Then I expect the response status is 200

    Scenario: Can't move as authenticated user without permissions
        Given I am logged in as User1 with password User1
        When I send the request with PATCH method
        Then I expect the response status is 403

    Scenario: Can't move as anonymous user
        When I send the request with PATCH method
        Then I expect the response status is 401
