@no_fixtures
Feature: RoleMembership Add Endpoint
    As an organization administrator,
    I want to give one of my organization's roles to one of its members,
    so that the delegated scope of #727's Q7 is the only authority the
    assignment needs (#736's AC2: the target must be a member, and only a
    platform act reaches over that).

    Background: Content type and the vocabulary of the payloads
        Given I set the content type of the request to application/vnd.api+json

    Scenario: Admin assigns a role to a member of their organization
        Given an organization "Assign Member Org" with an administrator "am-admin" and a member "am-member"
        Given I target the memberships of the role "resource_editor" of the organization "Assign Member Org"
        Given I set the payload to assign the user "am-member" to the role "resource_editor" of the organization "Assign Member Org"
        Given I am logged in as am-admin with password am-admin
        When I send the request with POST method
        Then I expect the response status is 201
        Then the user "am-member" holds the role "resource_editor" of the organization "Assign Member Org"

    Scenario: Assigning an organization role to a stranger of the organization fails
        # the caller administers the organization just fine; what fails is the
        # row itself, and the 400 names the field a client can fix
        Given an organization "Outsider Target Org" with an administrator "ot-admin" and a member "ot-member"
        Given a user "ot-stranger" without any service permissions exists
        Given I target the memberships of the role "resource_editor" of the organization "Outsider Target Org"
        Given I set the payload to assign the user "ot-stranger" to the role "resource_editor" of the organization "Outsider Target Org"
        Given I am logged in as ot-admin with password ot-admin
        When I send the request with POST method
        Then I expect the response status is 400
        Then I expect that response json has an attribute "errors.[0].code" with value "invalid"
        Then the user "ot-stranger" does not hold the role "resource_editor" of the organization "Outsider Target Org"

    Scenario: Stranger of the organization cannot assign its roles
        # not a member, not an administrator: a 403 with a reason, and no
        # disclosure of what a legal payload would have been
        Given an organization "Stranger Actor Org" with an administrator "sa-admin" and a member "sa-member"
        Given a user "sa-outsider" without any service permissions exists
        Given I target the memberships of the role "resource_editor" of the organization "Stranger Actor Org"
        Given I set the payload to assign the user "sa-member" to the role "resource_editor" of the organization "Stranger Actor Org"
        Given I am logged in as sa-outsider with password sa-outsider
        When I send the request with POST method
        Then I expect the response status is 403
        Then I expect that response json has an attribute "errors.[0].code" with value "permission_denied"
        Then the user "sa-member" does not hold the role "resource_editor" of the organization "Stranger Actor Org"

    Scenario: Retired role takes no new member
        # an inactive role is #741's work list, not a switch an operator
        # flips: its group is waiting to be deleted
        Given an organization "Retired Role Org" with an administrator "rr-admin" and a member "rr-member"
        Given the role "resource_editor" of the organization "Retired Role Org" is retired
        Given I target the memberships of the role "resource_editor" of the organization "Retired Role Org"
        Given I set the payload to assign the user "rr-member" to the role "resource_editor" of the organization "Retired Role Org"
        Given I am logged in as rr-admin with password rr-admin
        When I send the request with POST method
        Then I expect the response status is 400
        Then I expect that response json has an attribute "errors.[0].code" with value "invalid"
        Then the user "rr-member" does not hold the role "resource_editor" of the organization "Retired Role Org"
