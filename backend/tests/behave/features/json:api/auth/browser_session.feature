@no_fixtures
Feature: Browser Session Endpoint
    As the single page application,
    I want to open, probe and close a browser session,
    so that the browser never holds a copy of the credential (#835, decision Q8=B).

    Background: point at the session endpoint with the rules of a browser
        Given I use a client which enforces CSRF checks
        Given I use the endpoint http://localhost:8000/api/auth/session
        # the session view answers plain JSON, not json:api
        Given I set the header "HTTP_ACCEPT" with value "application/json"

    Scenario: The probe answers that an anonymous browser has no session
        When I send the request with GET method
        Then I expect the response status is 200
        And I expect that response json has an attribute "authenticated" with value "false"

    Scenario: Login turns basic credentials into a session, not into an answer to keep
        # User1:User1
        Given I set the header "HTTP_AUTHORIZATION" with value "VXNlcjE6VXNlcjE="
        When I send the request with POST method
        Then I expect the response status is 200
        And I expect that response json has an attribute "authenticated" with value "true"
        # the whole point of Q8=B: nothing in the answer is a credential
        And I expect that response json does not have an attribute "token"
        And I expect that response json does not have an attribute "key"

    Scenario: The probe of that same client answers that it now has a session
        # User1:User1
        Given I set the header "HTTP_AUTHORIZATION" with value "VXNlcjE6VXNlcjE="
        When I send the request with POST method
        When I send the request with GET method
        Then I expect that response json has an attribute "authenticated" with value "true"

    Scenario: Login with wrong credentials opens nothing
        Given I set the header "HTTP_AUTHORIZATION" with value "VXNlcjE6V3Jvbmc="
        When I send the request with POST method
        Then I expect the response status is 403
        And I expect that response json has an attribute "errors.[0].code" with value "not_authenticated"

    Scenario: A session-authenticated write without the CSRF header is refused, not the caller
        Given I am logged in as User1 with password User1
        When I send the request with DELETE method
        Then I expect the response status is 403
        # the contract of docs/source/administration/authentication.md: a
        # missing CSRF token refuses the request while the session stays valid
        And I expect that response json has an attribute "errors.[0].code" with value "permission_denied"
        When I send the request with GET method
        Then I expect that response json has an attribute "authenticated" with value "true"

    Scenario: The same write with the CSRF cookie repeated in the header closes the session
        Given I am logged in as User1 with password User1
        # the probe is where a client learns its CSRF cookie
        When I send the request with GET method
        Given I repeat the CSRF cookie in the header
        When I send the request with DELETE method
        Then I expect the response status is 204
        When I send the request with GET method
        Then I expect the response status is 200
        And I expect that response json has an attribute "authenticated" with value "false"

    Scenario: Closing an absent session is answered like a closed one
        When I send the request with DELETE method
        Then I expect the response status is 204

    Scenario: The machine token path is untouched beside the session (#835)
        Given I use the endpoint http://localhost:8000/api/auth/login
        # User1:User1
        Given I set the header "HTTP_AUTHORIZATION" with value "VXNlcjE6VXNlcjE="
        When I send the request with POST method
        Then I expect the response status is 200
        And I expect that response json has an attribute "token"
