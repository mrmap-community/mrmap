Feature: Login Endpoint
    As an API client,
    I want to login a user,
    so that I can use secured endpoints.

    Background: create user and prepare request
        Given I use the endpoint http://localhost:8000/api/auth/login

    Scenario: Login with correct credentials.
        # User1:User1
        Given I set the header "HTTP_AUTHORIZATION" with value "Basic bXJtYXA6bXJtYXA="
        When I send the request with POST method
        Then I expect the response status is 200
    # TODO: check token response

    Scenario: Login with wrong credentials.
        Given I set the header "HTTP_AUTHORIZATION" with value "Basic bla="
        When I send the request with POST method
        Then I expect the response status is 403
