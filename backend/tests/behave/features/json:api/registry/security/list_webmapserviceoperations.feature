@fixtures:test_wms.json @fixtures:test_keywords.json
Feature: WebMapServiceOperation List Endpoint
    As an API client,
    I want to add new allowed operation configurations,
    so that I can secure services.

    Background: Setup base url
        Given I use the endpoint http://localhost:8000/api/registry/security/wms-operations

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

    # The resource id of an operation is annotated from its value
    # (`WebMapServiceOperationViewSetMixin.queryset`), so this asserts the order and not only that
    # the request was answered. Counting the rows would pass for every sort parameter, valid or not.
    Scenario Outline: Can sort operations by their JSON API id
        Given I set a queryparam "sort" with value "<ordering>"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "data.[0].id" with value "<first>"
        Then I expect that response json has an attribute "data.[1].id" with value "<last>"

        Examples:
            | ordering | first | last |
            | id       | 20    | 21   |
            | -id      | 21    | 20   |

    Scenario: Can't sort by a field the resource does not have
        Given I set a queryparam "sort" with value "not_a_field"
        When I send the request with GET method
        Then I expect the response status is 400
        Then I expect that response json has an attribute "errors.[0].code" with value "invalid"
