Feature: Login Endpoint
    As an API client,
    I want to login a user,
    so that I can use secured endpoints.

    Scenario: Login with correct credentials.
        Given a request url http://localhost:8000/api/v1/accounts/login/
        When the request sends GET
        Then the response status is OK
        And the response json matches
            """
            {
                "title": "GeoJSON OWS Context",
                "type": "object",
                "properties": {
                    "type": {
                        "type": "string"
                    },
                    "id": {
                        "type": "string",
                        "format": "uri"
                    }
                },
                "required": [
                    "type",
                    "id"
                ]
            }
            """

    Scenario: Login with wrong credentials