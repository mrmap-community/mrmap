@no_fixtures
Feature: WebFeatureServiceAuthentication List Endpoint
    As an API client,
    I want to list the authentication records of remote WFS,
    so that I can manage how secured services are requested.

    Background: Setup base url
        Given I use the endpoint http://localhost:8000/api/registry/security/wfs-authentication

    # See the WMS sibling: the credentials of a remote service are no answer
    # for the anonymous caller (#1446).
    Scenario: Can't list as anonymous user
        Given I am an anonymous user
        When I send the request with GET method
        Then I expect the response status is 403
        Then I expect that response json has an attribute "errors.[0].code" with value "not_authenticated"
