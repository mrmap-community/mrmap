Feature: WebFeatureService detele Endpoint
    As an API client,
    I want to search for web feature services,
    so that I can find relevant map content.

    Background: Setup baseurl, content-type and payload
        Given I use the endpoint http://localhost:8000/api/v1/registry/wfs/9cc4889d-0cd4-4c3b-8975-58de6d30db41/

    Scenario: Can't delete as anonymous user
        When I send the request with DELETE method
        Then I expect the response status is 401

    Scenario: Can't delete as user without permissions
        Given I am logged in as User1 with password User1
        When I send the request with DELETE method
        Then I expect the response status is 403

    Scenario: Can delete as user with permissions
        Given I am logged in as mrmap with password mrmap
        When I send the request with DELETE method
        Then I expect the response status is 204
