Feature: Login Endpoint
    As an API client,
    I want to login a user,
    so that I can use secured endpoints.

    Background: create user and prepare request
        Given I use the endpoint http://localhost:8000/api/v1/accounts/login/
        Given I set the content type of the request to application/vnd.api+json

    Scenario: Login with correct credentials.
        Given I set the request payload to:
            """
            {
                "data": {
                    "type": "LoginRequest",
                    "attributes": {
                        "username": "User1",
                        "password": "User1"
                    }
                }
            }
            """
        When I send the request with POST method
        Then I expect the response status is 200

    Scenario: Login with wrong credentials.
        Given I set the request payload to:
            """
            {
                "data": {
                    "type": "LoginRequest",
                    "attributes": {
                        "username": "User1",
                        "password": "mrmap2"
                    }
                }
            }
            """
        When I send the request with POST method
        Then I expect the response status is 403
