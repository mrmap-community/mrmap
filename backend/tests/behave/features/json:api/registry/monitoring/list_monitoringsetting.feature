@fixtures:test_wms.json @fixtures:test_keywords.json @fixtures:test_monitoring.json
Feature: WebMapServiceMonitoringSetting List Endpoint
    As an API client,
    I want to search for monitoring settings,
    so that I can find relevant features.

    Background: Setup baseurl, content-type and payload
        Given I use the endpoint http://localhost:8000/api/registry/monitoring/wms-monitoring-settings

    Scenario: Can retrieve list as anonymous user
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "meta.pagination.count" with value "1"

    # The saved setting shows its recurrence risk without opening the edit form
    # (#1332). The fixture's setting was last decided against 2013, so its next
    # run is long past - the overdue warning leads and the single finished run
    # of the fixture is named as too little evidence to judge the interval.
    Scenario: The settings answer their schedule warnings
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "data.[0].attributes.scheduleWarnings.[0].code" with value "schedule_overdue"
        Then I expect that response json has an attribute "data.[0].attributes.scheduleWarnings.[0].severity" with value "warning"
        Then I expect that response json has an attribute "data.[0].attributes.scheduleWarnings.[1].code" with value "insufficient_evidence"
        Then I expect that response json has an attribute "data.[0].attributes.scheduleWarnings.[1].unknownReason" with value "too_few_samples"
