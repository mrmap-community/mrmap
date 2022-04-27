Feature: MapContext Delete Endpoint
    As an API client,
    I want to delete mapcontexts,
    so that I can remove them from the registry.

    Background: Setup base url, content type and payload
        Given I use the endpoint http://localhost:8000/api/v1/registry/mapcontexts/1/
        Given I set the content type of the request to application/vnd.api+json

    Scenario: Can delete as authenticated user with permissions
        Given I am logged in as User1 with password User1
        When I send the request with DELETE method
        Then I expect the response status is 204

    Scenario: Can't delete as authenticated user without permissions
        Given I am logged in as User2 with password User2
        When I send the request with DELETE method
        Then I expect the response status is 403

    Scenario: Can't delete as anonymous user
        When I send the request with DELETE method
        Then I expect the response status is 403
