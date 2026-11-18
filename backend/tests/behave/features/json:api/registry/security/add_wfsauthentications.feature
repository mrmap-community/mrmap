@no_fixtures
Feature: WebFeatureServiceAuthentication Add Endpoint
    As an API client,
    I want to add authentication credentials for a remote WFS,
    so that MrMap can request a secured service.

    Background: Setup baseurl, content-type and payload
        Given I use the endpoint http://localhost:8000/api/registry/security/wfs-authentication
        Given I set the content type of the request to application/vnd.api+json
        Given I set the request payload to:
            """
            {
                "data": {
                    "type": "WebFeatureServiceAuthentication",
                    "attributes": {
                        "username": "remote-user",
                        "password": "remote-password",
                        "authType": "http_basic"
                    }
                }
            }
            """

    # See the WMS sibling: no anonymous write of service credentials (#1446).
    Scenario: Can't add as anonymous user
        Given I am an anonymous user
        When I send the request with POST method
        Then I expect the response status is 403
        Then I expect that response json has an attribute "errors.[0].code" with value "not_authenticated"
