Feature: MapContext Add Endpoint
    As an API client,
    I want to add mapcontexts,
    so that I can configure map applications.

    Scenario: Can add as authenticated user
        Given there are set of Users in Database
            | username | password |
            | mrmap    | mrmap    |
        Given the user mrmap has registry.add_mapcontext permission
        Given I am logged in as mrmap with password mrmap
        Given I use the endpoint http://localhost:8000/api/v1/registry/mapcontexts/
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
        When I send the request with POST method
        Then I expect the response status is 201

    Scenario: Can't add as anonymous user
        Given I use the endpoint http://localhost:8000/api/v1/registry/mapcontexts/
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
        When I send the request with POST method
        Then I expect the response status is 403
