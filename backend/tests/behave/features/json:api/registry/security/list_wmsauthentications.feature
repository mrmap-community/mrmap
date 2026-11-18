@no_fixtures
Feature: WebMapServiceAuthentication List Endpoint
    As an API client,
    I want to list the authentication records of remote WMS,
    so that I can manage how secured services are requested.

    Background: Setup base url
        Given I use the endpoint http://localhost:8000/api/registry/security/wms-authentication

    # The record carries the credentials MrMap sends to a remote service. The
    # list answered them to anyone — the username and the Fernet ciphertext of
    # the password — before #1446 refused the anonymous caller.
    Scenario: Can't list as anonymous user
        Given I am an anonymous user
        When I send the request with GET method
        Then I expect the response status is 403
        Then I expect that response json has an attribute "errors.[0].code" with value "not_authenticated"
