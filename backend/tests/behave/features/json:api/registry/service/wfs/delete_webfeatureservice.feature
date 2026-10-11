Feature: WebFeatureService detele Endpoint
    As an API client,
    I want to search for web feature services,
    so that I can find relevant map content.

    Background: Setup baseurl, content-type and payload
        Given I use the endpoint http://localhost:8000/api/registry/wfs/9cc4889d-0cd4-4c3b-8975-58de6d30db41

    Scenario: Can't delete as anonymous user
        Given I am an anonymous user
        When I send the request with DELETE method
        Then I expect the response status is 403
        Then I expect that response json has an attribute "errors.[0].code" with value "not_authenticated"

    Scenario: Can't delete as user without permissions
        Given I am logged in as User1 with password User1
        When I send the request with DELETE method
        Then I expect the response status is 403
        Then I expect that response json has an attribute "errors.[0].code" with value "permission_denied"

    Scenario: Can delete as user with permissions
        Given I am logged in as mrmap with password mrmap
        When I send the request with DELETE method
        Then I expect the response status is 204
        When I send the request with GET method
        Then I expect the response status is 404
        Then I expect that response json has an attribute "errors.[0].code" with value "not_found"
