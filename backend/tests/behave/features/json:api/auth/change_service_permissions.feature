@fixtures:test_wms.json @fixtures:test_keywords.json
Feature: WebMapService Change Permissions
    As an API client,
    I want to know which grant lets me change a registered service,
    so that the role work of the #727 epic changes this knowingly and not by accident.

    Background: Setup endpoint, content type and the change payload
        Given I use the endpoint http://localhost:8000/api/registry/wms/cd16cc1f-3abb-4625-bb96-fbe80dbe23e3
        Given I set the content type of the request to application/vnd.api+json
        Given I set the request payload to:
            """
            {"data": {"type": "WebMapService", "id": "cd16cc1f-3abb-4625-bb96-fbe80dbe23e3", "attributes": {"title": "Pinned Title"}}}
            """

    Scenario: May not change a service without any permission
        Given a user "pin-no-perm" without any service permissions exists
        Given I am logged in as pin-no-perm with password pin-no-perm
        When I send the request with PATCH method
        Then I expect the response status is 403
        Then I expect that response json has an attribute "errors.[0].code" with value "permission_denied"
        Then the WMS title in the database is "WMS1"

    Scenario: May not change a service granted to the user's group only
        # guardian's object grant does not open the endpoint by itself: DRF's
        # DjangoObjectPermissions first demands the *global* change permission
        # in has_permission, before the object is read at all. The grant the
        # accounts bootstrap hands out is therefore not sufficient today for
        # anything but superusers - #734 replaces these two gates with one
        # resolution rule and this matrix is what it must treat knowingly.
        Given a user "pin-object-only" without any service permissions exists
        Given the user "pin-object-only" is member of a group granted the WMS
        Given I am logged in as pin-object-only with password pin-object-only
        When I send the request with PATCH method
        Then I expect the response status is 403
        Then I expect that response json has an attribute "errors.[0].code" with value "permission_denied"
        Then the WMS title in the database is "WMS1"

    Scenario: May not change a service with the global permission alone
        # the other half: Django's ModelBackend answers object-level has_perm
        # with the empty set (guardian owns those reads), so the global change
        # permission of Default-Permissions edits nothing on its own - today's
        # endpoint asks for global AND object grant, one of the split answers
        # the #727 motivation lists against the API's can_edit hint.
        Given a user "pin-global-only" without any service permissions exists
        Given the user "pin-global-only" holds the global permission to change services
        Given I am logged in as pin-global-only with password pin-global-only
        When I send the request with PATCH method
        Then I expect the response status is 403
        Then I expect that response json has an attribute "errors.[0].code" with value "permission_denied"
        Then the WMS title in the database is "WMS1"

    Scenario: May change a service with the global and the group object permission
        # the pair is what works: global grant passes has_permission, guardian's
        # group-object grant on this service passes has_object_permission -
        # editing a service its user's group was granted by assign_perm, the
        # same row shape accounts/signals.py writes for an owning organization.
        Given a user "pin-both" without any service permissions exists
        Given the user "pin-both" holds the global permission to change services
        Given the user "pin-both" is member of a group granted the WMS
        Given I am logged in as pin-both with password pin-both
        When I send the request with PATCH method
        Then I expect the response status is 200
        Then the WMS title in the database is "Pinned Title"
        Then the WMS title change is reverted
