Feature: Keyword Add Endpoint
    As an administrator,
    I want to add new keywords,
    so that I link them to resources.

    Background: Setup baseurl, content-type and payload
        Given I use the endpoint http://localhost:8000/api/v1/registry/keywords/
        Given I set the content type of the request to application/vnd.api+json

    Scenario: Can add as authenticated user
        Given I am logged in as User1 with password User1
        Given I set the request payload to:
            """
            {
                "data": {
                    "type": "Keyword",
                    "attributes": {
                        "keyword": "newkeyword"
                    }
                }
            }
            """
        When I send the request with POST method
        Then I expect the response status is 201

