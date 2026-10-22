@fixtures:test_keywords.json @fixtures:test_wms.json
Feature: Cross-service attention
    Administrators can find problems without opening each service.
    Alert counts and records reveal only services the caller may view.

    Background:
        Given I use the endpoint http://localhost:8000/api/registry/service-alerts
        And two map services have failed updates and User2 may view only one

    Scenario: Scoped paginated alerts expose the problem and its workflow
        Given I am logged in as User2 with password User2
        And I set a queryparam "page[size]" with value "1"
        And I set a queryparam "filter[severity]" with value "error"
        And I set a queryparam "sort" with value "-occurred_at"
        When I send the request with GET method
        Then I expect the response status is 200
        And I expect that response json has an attribute "meta.pagination.count" with value "1"
        And I expect that response json has an attribute "data.[0].type" with value "ServiceAlert"
        And I expect that response json has an attribute "data.[0].attributes.category" with value "update_failed"
        And I expect that response json has an attribute "data.[0].attributes.serviceTitle"
        And I expect that response json has an attribute "data.[0].attributes.targetPath"

    Scenario: Filtering does not return a different severity
        Given I am logged in as User2 with password User2
        And I set a queryparam "filter[severity]" with value "warning"
        When I send the request with GET method
        Then I expect the response status is 200
        And I expect that response json has an attribute "meta.pagination.count" with value "0"

    Scenario: Unknown filters are rejected
        Given I am logged in as User2 with password User2
        And I set a queryparam "filter[unknown]" with value "true"
        When I send the request with GET method
        Then I expect the response status is 400
        And I expect that response json has an attribute "errors.[0].code" with value "invalid"

    Scenario: Anonymous callers cannot read attention
        Given I am an anonymous user
        When I send the request with GET method
        Then I expect the response status is 403
        And I expect that response json has an attribute "errors.[0].code" with value "not_authenticated"
