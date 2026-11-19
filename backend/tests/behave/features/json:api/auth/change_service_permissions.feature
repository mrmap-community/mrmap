@fixtures:test_wms.json @fixtures:test_keywords.json
Feature: WebMapService Change Permissions
    As an API client,
    I want to know which grant lets me change a registered service,
    so that the role work of the #727 epic changes this knowingly and not by accident.

    Rule: one resolution rule decides a write (issue #734)
        The facade ``extras/permissions.allowed`` answers every write: the
        break-glass superuser, a permission of a platform-scoped role, an
        explicit object grant over this very service, or a currently valid
        organization role inside the organization owning the service. The
        retired global permission is not one of them; the scenarios below
        say which grant suffices and which answers nothing.

    Background: Setup endpoint, content type and the change payload
        Given I use the endpoint http://localhost:8000/api/registry/wms/cd16cc1f-3abb-4625-bb96-fbe80dbe23e3
        Given I set the content type of the request to application/vnd.api+json
        Given I set the request payload to:
            """
            {"data": {"type": "WebMapService", "id": "cd16cc1f-3abb-4625-bb96-fbe80dbe23e3", "attributes": {"title": "Pinned Title"}}}
            """

    Scenario: May not change a service without any permission
        # authentication alone opens the endpoint (has_permission), but the
        # facade on the object answers its four axes for this user: none of
        # them holds, so the write is refused on the object - the same
        # status the pin of #729 recorded, only reached one gate later.
        Given a user "pin-no-perm" without any service permissions exists
        Given I am logged in as pin-no-perm with password pin-no-perm
        When I send the request with PATCH method
        Then I expect the response status is 403
        Then I expect that response json has an attribute "errors.[0].code" with value "permission_denied"
        Then the WMS title in the database is "WMS1"

    Scenario: May change a service granted to the user's group only
        # the grant flips with #734, which is what the comment of this
        # scenario in the pin of #729 announced: "the accounts bootstrap
        # hands out is therefore not sufficient today ... #734 replaces
        # these two gates with one resolution rule". The group object grant
        # is exactly the row shape accounts/signals.py writes for an owning
        # organization, and the object-grant axis of the facade answers it
        # without any global permission - the endpoint and the allowedActions
        # hint now say the same thing (issue #727: the split was the bug).
        Given a user "pin-object-only" without any service permissions exists
        Given the user "pin-object-only" is member of a group granted the WMS
        Given I am logged in as pin-object-only with password pin-object-only
        When I send the request with PATCH method
        Then I expect the response status is 200
        Then the WMS title in the database is "Pinned Title"
        Then the WMS title change is reverted

    Scenario: May not change a service with the global permission alone
        # the other half of what #734 retires: the unrestricted global
        # permission (decision Q5=B) is no ask of the facade, so the Default
        # Permissions shape of the pre-role deployments edits no object by
        # itself. Mapping those grants onto role definitions is the
        # migration work of #732 and #741; until a user's grant sits on the
        # object or a role reaches this organization, the write stays 403.
        Given a user "pin-global-only" without any service permissions exists
        Given the user "pin-global-only" holds the global permission to change services
        Given I am logged in as pin-global-only with password pin-global-only
        When I send the request with PATCH method
        Then I expect the response status is 403
        Then I expect that response json has an attribute "errors.[0].code" with value "permission_denied"
        Then the WMS title in the database is "WMS1"

    Scenario: May change a service with the global and the group object permission
        # unchanged from the pin - but for one fewer reason: it is the
        # group-object grant alone which passes the facade now, the global
        # half of the pair is not asked anymore. Keeping the pair here pins
        # that a legacy user which still carries both is not punished while
        # the migration of #741 retires the global side row by row.
        Given a user "pin-both" without any service permissions exists
        Given the user "pin-both" holds the global permission to change services
        Given the user "pin-both" is member of a group granted the WMS
        Given I am logged in as pin-both with password pin-both
        When I send the request with PATCH method
        Then I expect the response status is 200
        Then the WMS title in the database is "Pinned Title"
        Then the WMS title change is reverted
