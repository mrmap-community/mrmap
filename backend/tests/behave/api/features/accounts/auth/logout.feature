Feature: Logout Endpoint
    As an API client,
    I want to logout the current user,
    so that I close the session by my self.

    Background: create user and prepare request
        Given I am logged in as User1 with password User1P
        Given I use the endpoint http://localhost:8000/api/v1/accounts/logout/
        Given I set the content type of the request to application/vnd.api+json

    Scenario: Logout the current user
        Given I set the request payload to:
            """
            {
            "data": {
            "type": "Logout",
            }
            }
            """
        When I send the request with POST method
        Then I expect the response status is 200