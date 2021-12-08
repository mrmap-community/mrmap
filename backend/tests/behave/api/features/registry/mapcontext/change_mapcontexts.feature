Feature: MapContext Change Endpoint
    As an API client,
    I want to change mapcontexts,
    so that I can modify existing map applications.

    Background: Setup base url, content type and payload
        Given I use the endpoint http://localhost:8000/api/v1/registry/mapcontexts/1/
        Given I set the content type of the request to application/vnd.api+json
        Given I set the request payload to:
            """
            {
                "data": {
                    "type": "MapContext",
                    "attributes": {
                        "title": "nice title",
                        "abstract": "short abstract"
                    }
                }
            }
            """

    Scenario: Can change as authenticated user with permissions
        Given I am logged in as User1 with password User1
        When I send the request with PATCH method
        Then I expect the response status is 201

    Scenario: Can't change as authenticated user without permissions
        Given I am logged in as User2 with password User2
        When I send the request with PATCH method
        Then I expect the response status is 403

    Scenario: Can't change as anonymous user
        When I send the request with PATCH method
        Then I expect the response status is 403
