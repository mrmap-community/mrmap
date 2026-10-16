@fixtures:test_wms.json @fixtures:test_keywords.json
Feature: Read-only live service previews
    Registry users can inspect current service data without starting registry updates.

    Background:
        Given I use the endpoint http://localhost:8000/api/registry/wms/cd16cc1f-3abb-4625-bb96-fbe80dbe23e3/preview
        And I set the header "HTTP_ACCEPT" with value "application/json"
        And I set a queryparam "selection" with value "node1.1"

    Scenario: Stored discovery does not request upstream
        Given User1 can preview the registered WMS
        And I am logged in as User1 with password User1
        When I send the request with GET method
        Then I expect the response status is 200
        And I expect that response json has an attribute "discovery" with value "stored"
        And the live preview has not contacted upstream
        And the live preview creates no update or harvesting jobs

    Scenario: Live imagery remains available without stored extents
        Given User1 can preview the registered WMS
        And I am logged in as User1 with password User1
        And I set a queryparam "bbox" with value "0,0,4,8"
        When I send the request with GET method
        Then I expect the response status is 200
        And I expect that response json has an attribute "image"
        And I expect that response json has an attribute "fetchedAt"
        And the live preview creates no update or harvesting jobs

    Scenario: Anonymous users without object permission cannot preview
        Given I am an anonymous user
        And I set a queryparam "bbox" with value "0,0,4,8"
        When I send the request with GET method
        Then I expect the response status is 403
