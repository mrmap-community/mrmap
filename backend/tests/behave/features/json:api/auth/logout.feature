Feature: Logout Endpoint
    As an API client,
    I want to logout the current user,
    so that I close the session by my self.

    Background: create user and prepare request
        Given I am logged in as User1 with password User1
        Given I use the endpoint http://localhost:8000/api/auth/logout

    Scenario: Logout the current user
        Given I use token based authentication for user "User1"
        When I send the request with POST method
        Then I expect the response status is 204
