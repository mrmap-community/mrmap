@fixtures:test_keywords.json @fixtures:test_wms.json @fixtures:test_wfs.json
Feature: WebMapService Share Endpoint

    Registry shares (#740): guardian object grants written onto the GROUP OF
    A ROLE over one service, with the decision recorded in the row. These are
    not the OGC proxy's access rules (`Allowed*Operation` under the
    `allowed-*-operations` routes); the naming apart is what an editor sees
    in the UI as well. The share dialog itself is #737; these scenarios
    specify the endpoint and the acceptance half of the same issue.

    The fixtures are loaded once for the feature and not restored, so every
    scenario states which service it acts on: a scenario that shares acts on
    its own fresh service and cannot be misled by a sibling's grants.

    Background:
        Given the organization "Share Org" owns a web map service "Share Target WMS"
        And the user "User2" holds the role "resource_publisher" of the organization "Share Org"

    Scenario: The bootstrap grants of the owning organization are not shares
        Given the organization "Share Org" owns a web map service "Pristine WMS"
        And I am logged in as User2 with password User2
        When I list the shares of the web map service "Pristine WMS"
        Then I expect the response status is 200
        Then the grant list answers no actions

    Scenario: Publisher shares the service with the editors of the own organization
        Given the user "User1" holds the role "resource_editor" of the organization "Share Org"
        And I am logged in as User2 with password User2
        When I share the web map service "Share Target WMS" with the role "resource_editor" of the organization "Share Org" for the actions "view, change"
        Then I expect the response status is 201
        Then the role "resource_editor" of the organization "Share Org" holds "view_webmapservice" over the web map service "Share Target WMS"
        Then the role "resource_editor" of the organization "Share Org" holds "change_webmapservice" over the web map service "Share Target WMS"

    Scenario: An editor may change the service and still may not share it
        Given the user "User1" holds the role "resource_editor" of the organization "Share Org"
        And I am logged in as User1 with password User1
        When I share the web map service "Share Target WMS" with the role "resource_editor" of the organization "Share Org" for the actions "view"
        Then I expect the response status is 403
        Then I expect that response json has an attribute "errors.[0].code" with value "permission_denied"

    Scenario: Anonymous users cannot list the shares of a service
        Given I am an anonymous user
        When I list the shares of the web map service "Share Target WMS"
        Then I expect the response status is 403
        Then I expect that response json has an attribute "errors.[0].code" with value "not_authenticated"

    Scenario: A web feature service has no publish action to share
        Given the organization "Share Org" owns a web feature service "Share Target WFS"
        And I am logged in as User2 with password User2
        When I share the web feature service "Share Target WFS" with the role "resource_editor" of the organization "Share Org" for the actions "publish"
        Then I expect the response status is 400
        Then I expect that response json has an attribute "errors.[0].code" with value "invalid"

    Scenario: Revoking removes exactly the answered grant
        Given the user "User1" holds the role "resource_editor" of the organization "Share Org"
        And I am logged in as User2 with password User2
        When I share the web map service "Share Target WMS" with the role "resource_editor" of the organization "Share Org" for the actions "view, change"
        Then I expect the response status is 201
        When I revoke the share of action "change" of the web map service "Share Target WMS"
        Then I expect the response status is 204
        Then the role "resource_editor" of the organization "Share Org" does not hold "change_webmapservice" over the web map service "Share Target WMS"
        Then the role "resource_editor" of the organization "Share Org" holds "view_webmapservice" over the web map service "Share Target WMS"
        When I list the shares of the web map service "Share Target WMS"
        Then the grant list answers the actions "view"

    Scenario: The publishers of another organization read the service after the share
        Given the organization "Share Org" owns a web map service "Foreign Fetch WMS"
        And the organization "Foreign Org" exists
        And the user "User1" holds the role "resource_publisher" of the organization "Foreign Org"
        And I am logged in as User2 with password User2
        When I share the web map service "Foreign Fetch WMS" with the role "resource_publisher" of the organization "Foreign Org" for the actions "view, change"
        Then I expect the response status is 201
        When I am logged in as User1 with password User1
        And I fetch the web map service "Foreign Fetch WMS"
        Then I expect the response status is 200
        Then I expect that response json has an attribute "data.type" with value "WebMapService"

    Scenario: A member of no organization does not see the service
        Given the organization "Share Org" owns a web map service "Stranger Blind WMS"
        And the user "Share Stranger" exists
        And I am logged in as Share Stranger with password Share Stranger
        When I fetch the web map service "Stranger Blind WMS"
        Then I expect the response status is 404
        Then I expect that response json has an attribute "errors.[0].code" with value "not_found"

    Scenario: Accepting lets the requesting publisher role publish for the requested organization
        Given the organization "Publishing Org" exists
        And the organization "Requested Org" owns a web map service "Published For WMS"
        When the publish request from "Publishing Org" to "Requested Org" is accepted
        Then the organization "Requested Org" answers "Publishing Org" among its publishers
        Then the organization "Publishing Org" does not answer "Requested Org" among its publishers
        And the organization "Publishing Org" holds the publish grant over "Requested Org" through its "resource_publisher" role
        Then the role "resource_publisher" of the organization "Publishing Org" holds "view_webmapservice" over the web map service "Published For WMS"
        Then the role "resource_publisher" of the organization "Publishing Org" holds "publish_resource" over the web map service "Published For WMS"
        Then the publish request from "Publishing Org" to "Requested Org" is gone
