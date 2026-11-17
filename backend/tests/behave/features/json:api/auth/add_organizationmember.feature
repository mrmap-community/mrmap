@no_fixtures
Feature: OrganizationMember Add Endpoint
    As an organization administrator,
    I want to add an existing user to my organization,
    so that "add a member" of #736's AC1 is one guarded write, and giving
    that member a role stays the separate, separately guarded step against
    /roles.

    Background: Content type
        Given I set the content type of the request to application/vnd.api+json

    Scenario: Admin adds an existing user to the organization
        Given an organization "Members Org" with an administrator "mo-admin" and a member "mo-member"
        Given a user "mo-newcomer" without any service permissions exists
        Given I target the members of the organization "Members Org"
        Given I set the payload to add the user "mo-newcomer"
        Given I am logged in as mo-admin with password mo-admin
        When I send the request with POST method
        Then I expect the response status is 201
        Then the user "mo-newcomer" is a member of the organization "Members Org"
        # adding a member grants no role - that is the POST to /roles
        Then the user "mo-newcomer" does not hold the role "viewer" of the organization "Members Org"

    Scenario: Stranger cannot add a member to another organization
        Given an organization "Members Guard Org" with an administrator "mg-admin" and a member "mg-member"
        Given a user "mg-stranger" without any service permissions exists
        Given I target the members of the organization "Members Guard Org"
        Given I set the payload to add the user "mg-stranger"
        Given I am logged in as mg-stranger with password mg-stranger
        When I send the request with POST method
        Then I expect the response status is 403
        Then I expect that response json has an attribute "errors.[0].code" with value "permission_denied"
        Then the user "mg-stranger" is not a member of the organization "Members Guard Org"
