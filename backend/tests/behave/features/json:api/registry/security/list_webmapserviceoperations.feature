Feature: WebMapServiceOperation List Endpoint
    As an API client,
    I want to add new allowed operation configurations,
    so that I can secure services.

    Background: Setup baseurl, content-type and payload
        Given I use the endpoint http://localhost:8000/api/registry/security/wms-operations
        Given I set the header "HTTP_ACCEPT" with value "application/vnd.api+json"

    Scenario: Can retrieve list as anonymous user
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "meta.pagination.count" with value "2"

    Scenario: Can search for operation 'GetFeature'
        Given I set a queryparam "filter[search]" with value "21"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "meta.pagination.count" with value "1"

    Scenario: Can search for operation 'GetMap'
        Given I set a queryparam "filter[search]" with value "20"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "meta.pagination.count" with value "1"

    Scenario Outline: Can sort operations by their JSON API id
        Given I set a queryparam "sort" with value "<ordering>"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "meta.pagination.count" with value "2"

        Examples:
            | ordering |
            | id       |
            | -id      |
