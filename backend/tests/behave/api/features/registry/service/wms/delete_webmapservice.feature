Feature: WebMapService detele Endpoint
    As an API client,
    I want to search for web map services,
    so that I can find relevant map content.

    Background: Setup baseurl, content-type and payload
        Given I use the endpoint http://localhost:8000/api/v1/registry/wms/1b195589-dcfa-403f-9e66-e7e1c0a67024/

    Scenario: Can't delete as anonymous user
        When I send the request with DELETE method
        Then I expect the response status is 403

    Scenario: Can't delete as user without permissions
        Given I am logged in as User1 with password User1
        When I send the request with DELETE method
        Then I expect the response status is 403

    Scenario: Can delete as user with permissions
        Given I am logged in as mrmap with password mrmap
        When I send the request with DELETE method
        Then I expect the response status is 204
