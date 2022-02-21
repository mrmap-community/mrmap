Feature: Permissions List Endpoint
    As an API client,
    I want to search permissions,
    so that I can use for any autocomplete search in select fields.

    Scenario: Access denied as anonymous user
        Given I use the endpoint http://localhost:8000/api/v1/accounts/permissions/
        When I send the request with GET method
        Then I expect the response status is 401

    Scenario: Access allowed as authenticated user
        Given I am logged in as User1 with password User1
        Given I use the endpoint http://localhost:8000/api/v1/accounts/permissions/
        When I send the request with GET method
        Then I expect the response status is 200

# TODO: check filter params
