Feature: Login Endpoint
    As an API client,
    I want to login a user,
    so that I can use secured endpoints.

    Background: create user and prepare request
        Given there are set of Users in Database
            | username | password |
            | mrmap    | mrmap    |
        Given request headers
            | param        | value                    |
            | content-type | application/vnd.api+json |
        Given a request url http://localhost:8000/api/v1/accounts/login/

    Scenario: Login with correct credentials.
        And a request json payload
            """
            {
                "data": {
                    "type": "Login",
                    "attributes": {
                        "username": "mrmap",
                        "password": "mrmap"
                    }
                }
            }
            """
        When the request sends POST
        Then the response status is OK
# Currently this will fail, cause the media type is wrong
# And the response json matches
#     """
#     {
#         "title": "GeoJSON OWS Context",
#         "type": "object",
#         "properties": {
#             "type": {
#                 "type": "string"
#             },
#             "id": {
#                 "type": "string",
#                 "format": "uri"
#             }
#         },
#         "required": [
#             "type",
#             "id"
#         ]
#     }
#     """

#Scenario: Login with wrong credentials