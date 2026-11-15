@fixtures:test_wms.json @fixtures:test_keywords.json @fixtures:test_crs.json
Feature: Scheduling Draft Preview Endpoint
    As an API client,
    I want to preview a proposed schedule before saving it,
    so that I can see its consequences without creating jobs or schedules.

    Background: Setup baseurl and content-type
        Given I use the endpoint http://localhost:8000/api/registry/scheduling/preview
        Given I set the content type of the request to application/vnd.api+json

    Scenario: Can't preview as anonymous user
        Given I set the request payload to:
            """
            {
                "data": {
                    "type": "SchedulingPreview",
                    "attributes": {
                        "operation": "monitoring",
                        "serviceKind": "WebMapService",
                        "serviceId": "cd16cc1f-3abb-4625-bb96-fbe80dbe23e3",
                        "scheduling": "*/5 * * * *",
                        "enabled": true
                    }
                }
            }
            """
        Given I am an anonymous user
        When I send the request with POST method
        Then I expect the response status is 403
        And I expect that response json has an attribute "errors.[0].code" with value "not_authenticated"

    Scenario: A draft schedule is answered without anything being saved
        Given I am logged in as mrmap with password mrmap
        And I set the request payload to:
            """
            {
                "data": {
                    "type": "SchedulingPreview",
                    "attributes": {
                        "operation": "monitoring",
                        "serviceKind": "WebMapService",
                        "serviceId": "cd16cc1f-3abb-4625-bb96-fbe80dbe23e3",
                        "scheduling": "*/5 * * * *",
                        "timezone": "UTC",
                        "enabled": true
                    }
                }
            }
            """
        When I send the request with POST method
        Then I expect the response status is 200
        And I expect that response json has an attribute "data.attributes.scheduling" with value "*/5 * * * * UTC"
        And I expect that response json has an attribute "data.attributes.nextOccurrences"
        And I expect that response json has an attribute "data.attributes.capacityReason"

    Scenario: An unparsable crontab answers the field error of the save path
        Given I am logged in as User1 with password User1
        And I set the request payload to:
            """
            {
                "data": {
                    "type": "SchedulingPreview",
                    "attributes": {
                        "operation": "monitoring",
                        "serviceKind": "WebMapService",
                        "serviceId": "cd16cc1f-3abb-4625-bb96-fbe80dbe23e3",
                        "scheduling": "every five minutes",
                        "enabled": true
                    }
                }
            }
            """
        When I send the request with POST method
        Then I expect the response status is 400
        And I expect that response json has an attribute "errors.[0].code" with value "invalid"

    Scenario: A periodic draft without verified capacity is refused by name
        Given I am logged in as mrmap with password mrmap
        And I set the request payload to:
            """
            {
                "data": {
                    "type": "SchedulingPreview",
                    "attributes": {
                        "operation": "monitoring",
                        "serviceKind": "WebMapService",
                        "serviceId": "cd16cc1f-3abb-4625-bb96-fbe80dbe23e3",
                        "scheduling": "*/5 * * * *",
                        "timezone": "UTC",
                        "enabled": true
                    }
                }
            }
            """
        When I send the request with POST method
        Then I expect the response status is 200
        And I expect that response json has an attribute "data.attributes.suggestions" with value "[]"
        And I expect that response json has an attribute "data.attributes.suggestionsReasonCode" with value "capacity_unverified"
        And I expect that response json has an attribute "data.attributes.suggestionsReason"
        And I expect that response json has an attribute "data.attributes.suggestionsHorizonDays" with value "7"

    Scenario: A one-off draft is answered as no cadence to preserve
        Given I am logged in as mrmap with password mrmap
        And I set the request payload to:
            """
            {
                "data": {
                    "type": "SchedulingPreview",
                    "attributes": {
                        "operation": "monitoring",
                        "serviceKind": "WebMapService",
                        "serviceId": "cd16cc1f-3abb-4625-bb96-fbe80dbe23e3",
                        "scheduling": "37 14 * * *",
                        "timezone": "UTC",
                        "enabled": true,
                        "oneOff": true
                    }
                }
            }
            """
        When I send the request with POST method
        Then I expect the response status is 200
        And I expect that response json has an attribute "data.attributes.suggestions" with value "[]"
        And I expect that response json has an attribute "data.attributes.suggestionsReasonCode" with value "not_periodic"

    Scenario: A caller without the add permission is answered the refusal
        Given I am logged in as User1 with password User1
        And I set the request payload to:
            """
            {
                "data": {
                    "type": "SchedulingPreview",
                    "attributes": {
                        "operation": "monitoring",
                        "serviceKind": "WebMapService",
                        "serviceId": "cd16cc1f-3abb-4625-bb96-fbe80dbe23e3",
                        "scheduling": "*/5 * * * *",
                        "timezone": "UTC",
                        "enabled": true
                    }
                }
            }
            """
        When I send the request with POST method
        Then I expect the response status is 403
        And I expect that response json has an attribute "errors.[0].code" with value "permission_denied"
