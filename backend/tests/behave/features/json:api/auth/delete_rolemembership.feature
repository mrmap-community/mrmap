@no_fixtures
Feature: RoleMembership Delete Endpoint
    As an organization administrator,
    I want to revoke a role from a member again,
    so that revoking is the mirror of granting: same scope, same guard rails,
    and a stranger is refused with a reason instead of silence (#736's AC1).

    Background: Content type
        Given I set the content type of the request to application/vnd.api+json

    Scenario: Admin revokes a role from a member
        Given an organization "Revoke Org" with an administrator "rv-admin" and a member "rv-member"
        Given the user "rv-member" holds the role "resource_editor" of the organization "Revoke Org"
        Given I target the membership of the user "rv-member" in the role "resource_editor" of the organization "Revoke Org"
        Given I am logged in as rv-admin with password rv-admin
        When I send the request with DELETE method
        Then I expect the response status is 204
        Then the user "rv-member" does not hold the role "resource_editor" of the organization "Revoke Org"

    Scenario: Stranger cannot revoke a role of another organization
        # a detail lookup of /memberships is not narrowed to a 404 on purpose:
        # the outsider learns the refusal and its reason, not a guessing game
        Given an organization "Keep Org" with an administrator "kv-admin" and a member "kv-member"
        Given the user "kv-member" holds the role "resource_editor" of the organization "Keep Org"
        Given a user "kv-outsider" without any service permissions exists
        Given I target the membership of the user "kv-member" in the role "resource_editor" of the organization "Keep Org"
        Given I am logged in as kv-outsider with password kv-outsider
        When I send the request with DELETE method
        Then I expect the response status is 403
        Then I expect that response json has an attribute "errors.[0].code" with value "permission_denied"
        Then the user "kv-member" holds the role "resource_editor" of the organization "Keep Org"
