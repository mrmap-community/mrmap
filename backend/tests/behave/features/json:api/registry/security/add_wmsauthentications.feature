@no_fixtures
Feature: WebMapServiceAuthentication Add Endpoint
    As an API client,
    I want to add authentication credentials for a remote WMS,
    so that MrMap can request a secured service.

    Background: Setup baseurl, content-type and payload
        Given I use the endpoint http://localhost:8000/api/registry/security/wms-authentication
        Given I set the content type of the request to application/vnd.api+json
        Given I set the request payload to:
            """
            {
                "data": {
                    "type": "WebMapServiceAuthentication",
                    "attributes": {
                        "username": "remote-user",
                        "password": "remote-password",
                        "authType": "http_basic"
                    }
                }
            }
            """

    # Writing credentials is not open to the anonymous caller either: before
    # #1446 any caller could store credentials the registry would later send
    # to a remote service.
    Scenario: Can't add as anonymous user
        Given I am an anonymous user
        When I send the request with POST method
        Then I expect the response status is 403
        Then I expect that response json has an attribute "errors.[0].code" with value "not_authenticated"
