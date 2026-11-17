@no_fixtures
Feature: RoleDefinition List Endpoint
    As an authenticated API client,
    I want to read the catalogue of role definitions,
    so that the member picker of #737 can name the assignable roles from any
    account, while changing what a role means stays a platform act (#736).

    Background: Endpoint and content type
        Given I use the endpoint http://localhost:8000/api/accounts/roledefinitions
        Given I set the content type of the request to application/vnd.api+json

    Scenario: Authenticated user lists the catalogue
        # the seeded catalogue of #731/#732 orders by slug; the whole table is
        # readable, its rows are not a secret of any organization
        Given I am logged in as User1 with password User1
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "data.[0].attributes.slug" with value "harvester"

    Scenario: Anonymous cannot read the catalogue
        Given I am an anonymous user
        When I send the request with GET method
        Then I expect the response status is 403
        Then I expect that response json has an attribute "errors.[0].code" with value "not_authenticated"

    Scenario: Plain user cannot add a definition
        # adding a definition changes what a role IS, not what it pays out;
        # the 403 answers before the payload is even read
        Given I am logged in as User1 with password User1
        Given I set the request payload to:
            """
            {"data": {"type": "RoleDefinition", "attributes": {"slug": "behavior_custom", "label": "Custom"}}}
            """
        When I send the request with POST method
        Then I expect the response status is 403
        Then I expect that response json has an attribute "errors.[0].code" with value "permission_denied"
