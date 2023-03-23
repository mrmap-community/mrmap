Feature: MapContextLayer Update Endpoint
    As an API client,
    I want to add mapcontextlayers,
    so that I can configure map applications.

    Background: Setup baseurl, content-type and payload
        Given I use the endpoint http://localhost:8000/api/v1/registry/mapcontextlayers/8/
        Given I set the content type of the request to application/vnd.api+json

    Scenario: Can update as authenticated user
        Given I set the request payload to:
            """
            {
                "data": {
                    "type": "MapContextLayer",
                    "id": "8",
                    "attributes": {
                        "title": "mc2_node1.2 bla"
                    }
                }
            }
            """
        Given I am logged in as User2 with password User2
        When I send the request with PATCH method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "data.attributes.title" with value "mc2_node1.2 bla"

    Scenario: Can't update as anonymous user
        Given I set the request payload to:
            """
            {
                "data": {
                    "type": "MapContextLayer",
                    "id": "8",
                    "attributes": {
                        "title": "mc2_node1.2 bla"
                    }
                }
            }
            """
        When I send the request with PATCH method
        Then I expect the response status is 403
