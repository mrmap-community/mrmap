Feature: WebMapService manual updates
    Users can queue a one-off update without changing the automatic schedule.

    Background:
        Given I use the endpoint http://localhost:8000/api/registry/update/webmapservice-update-jobs
        And I set the content type of the request to application/vnd.api+json
        And I set the request payload to:
            """
            {"data":{"type":"WebMapServiceUpdateJob","relationships":{"service":{"data":{"type":"WebMapService","id":"cd16cc1f-3abb-4625-bb96-fbe80dbe23e3"}}}}}
            """

    Scenario: Queue an update without automatic settings
        Given User1 can manually update the WMS
        And the WMS has no automatic update settings
        And I am logged in as User1 with password User1
        When I send the request with POST method
        Then I expect the response status is 201
        And the WMS automatic update settings are unchanged

    Scenario: Queue an update while automatic updates are disabled
        Given User1 can manually update the WMS
        And the WMS has a disabled automatic update setting
        And I am logged in as User1 with password User1
        When I send the request with POST method
        Then I expect the response status is 201
        And the WMS automatic update settings are unchanged

    Scenario: Reject another update while review is required
        Given User1 can manually update the WMS
        And the WMS has an update awaiting review
        And I am logged in as User1 with password User1
        When I send the request with POST method
        Then I expect the response status is 400

    Scenario: Anonymous users cannot queue updates
        When I send the request with POST method
        Then I expect the response status is 403
