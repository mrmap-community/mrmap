@fixtures:test_keywords.json @fixtures:test_mapcontext.json @fixtures:test_wms.json
Feature: MapContext Delete Endpoint
    As an API client,
    I want to delete mapcontexts,
    so that I can remove them from the registry.

    Background: Setup base url
        Given I use the endpoint http://localhost:8000/api/registry/mapcontexts/1

    Scenario: Can delete as authenticated user with permissions
        Given I am logged in as User1 with password User1
        When I send the request with DELETE method
        Then I expect the response status is 204
        When I send the request with GET method
        Then I expect the response status is 404
        Then I expect that response json has an attribute "errors.[0].code" with value "not_found"

    Scenario: Can't delete as authenticated user without permissions
        Given I am logged in as User2 with password User2
        When I send the request with DELETE method
        Then I expect the response status is 403
        Then I expect that response json has an attribute "errors.[0].code" with value "permission_denied"

    Scenario: Can't delete as anonymous user
        Given I am an anonymous user
        When I send the request with DELETE method
        Then I expect the response status is 403
        Then I expect that response json has an attribute "errors.[0].code" with value "not_authenticated"
