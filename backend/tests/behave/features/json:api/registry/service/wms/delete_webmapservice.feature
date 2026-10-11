@fixtures:test_wms.json @fixtures:test_keywords.json
Feature: WebMapService detele Endpoint
    As an API client,
    I want to search for web map services,
    so that I can find relevant map content.

    Background: Setup baseurl, content-type and payload
        Given I use the endpoint http://localhost:8000/api/registry/wms/1b195589-dcfa-403f-9e66-e7e1c0a67024

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
