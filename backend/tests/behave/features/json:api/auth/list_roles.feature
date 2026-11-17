@no_fixtures
Feature: Role List Endpoint
    As an authenticated API client,
    I want to read which roles exist and which of them one user or one
    organization carries,
    so that the management screens of #737 can render roles without
    disclosing who holds them (#727's Q3).

    Background: Endpoint and content type
        Given I use the endpoint http://localhost:8000/api/accounts/roles
        Given I set the content type of the request to application/vnd.api+json

    Scenario: Authenticated user lists the roles
        # a Role row names a definition and an organization and discloses no
        # membership, so reading it is open to every account
        Given I am logged in as User1 with password User1
        When I send the request with GET method
        Then I expect the response status is 200

    Scenario: Anonymous cannot list the roles
        Given I am an anonymous user
        When I send the request with GET method
        Then I expect the response status is 403
        Then I expect that response json has an attribute "errors.[0].code" with value "not_authenticated"

    Scenario: Member reads the roles of their organization
        # the bootstrap of #732 writes exactly the five ORGANIZATION scoped
        # definitions for every new organization
        Given an organization "Nested Roles Org" with an administrator "nr-admin" and a member "nr-member"
        Given I target the roles of the organization "Nested Roles Org"
        Given I am logged in as nr-member with password nr-member
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "meta.pagination.count" with value "5"

    Scenario: Administrator reads their own roles from who-am-i
        # one request answers the caller's own authority: the roles relation
        # of the User resource carries the organization_admin role the setup
        # handed out
        Given an organization "WhoAmI Roles Org" with an administrator "wai-admin" and a member "wai-member"
        Given I use the endpoint http://localhost:8000/api/accounts/who-am-i/
        Given I am logged in as wai-admin with password wai-admin
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "data.relationships.roles.data.[0].type" with value "Role"
