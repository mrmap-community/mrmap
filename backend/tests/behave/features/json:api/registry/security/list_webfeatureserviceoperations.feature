@fixtures:test_crs.json @fixtures:test_wfs.json @fixtures:test_keywords.json
Feature: WebFeatureServiceOperation List Endpoint
    As an API client,
    I want to add new allowed operation configurations,
    so that I can secure services.

    Background: Setup baseurl, content-type and payload
        Given I use the endpoint http://localhost:8000/api/registry/security/wfs-operations

    Scenario: Can retrieve list as anonymous user
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "meta.pagination.count" with value "2"

    Scenario: Can search for operation 'GetFeature'
        Given I set a queryparam "filter[search]" with value "30"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "meta.pagination.count" with value "1"

    Scenario: Can search for operation 'Trans'
        Given I set a queryparam "filter[search]" with value "31"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "meta.pagination.count" with value "1"

    Scenario: Can sort the operations by their identifier
        Given I set a queryparam "sort" with value "id"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "data.[0].id" with value "30"

    Scenario: Can sort the operations by their identifier in reverse order
        Given I set a queryparam "sort" with value "-id"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "data.[0].id" with value "31"

    Scenario: Rejects a sort the operations do not have
        Given I set a queryparam "sort" with value "created_at"
        When I send the request with GET method
        Then I expect the response status is 400
        Then I expect that response json has an attribute "errors.[0].code" with value "invalid"
