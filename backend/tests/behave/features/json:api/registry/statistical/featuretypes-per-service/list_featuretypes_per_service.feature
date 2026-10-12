@fixtures:test_keywords.json @fixtures:test_crs.json @fixtures:test_wfs.json
Feature: Statistical FeatureType Per Service List Endpoint
    As an API client,
    I want daily feature type changes for one WFS,
    so that its overview chart counts the correct service elements.

    Background:
        Given I use the endpoint http://localhost:8000/api/registry/statistical/featuretypes-per-service

    Scenario Outline: Count feature type changes for one service
        Given the WFS history contains service-specific feature type changes
        And I set a queryparam "filter[service]" with value "<service>"
        And I set a queryparam "sort" with value "id"
        When I send the request with GET method
        Then I expect the response status is 200
        And I expect that response json has an attribute "meta.pagination.count" with value "<days>"
        And I expect that response json has an attribute "data.[0].type" with value "StatisticalFeatureTypePerService"
        And I expect that response json has an attribute "data.[0].attributes.service" with value "<service>"
        And I expect that response json has an attribute "data.[0].attributes.new" with value "<new>"

        Examples:
            | service                              | days | new |
            | 9cc4889d-0cd4-4c3b-8975-58de6d30db41 | 2    | 2   |
            | 72bda0a1-a808-48ba-ab1d-bf03081263df | 1    | 1   |

    Scenario: Count additions, updates and deletions on their respective days
        Given the WFS history contains service-specific feature type changes
        And I set a queryparam "filter[service]" with value "9cc4889d-0cd4-4c3b-8975-58de6d30db41"
        And I set a queryparam "sort" with value "id"
        When I send the request with GET method
        Then I expect the response status is 200
        And I expect that response json has an attribute "data.[0].id" with value "2022-02-01"
        And I expect that response json has an attribute "data.[0].attributes.new" with value "2"
        And I expect that response json has an attribute "data.[0].attributes.updated" with value "0"
        And I expect that response json has an attribute "data.[0].attributes.deleted" with value "0"
        And I expect that response json has an attribute "data.[1].id" with value "2022-03-01"
        And I expect that response json has an attribute "data.[1].attributes.new" with value "0"
        And I expect that response json has an attribute "data.[1].attributes.updated" with value "1"
        And I expect that response json has an attribute "data.[1].attributes.deleted" with value "1"

    Scenario Outline: Sort the daily changes chronologically
        Given the WFS history contains service-specific feature type changes
        And I set a queryparam "filter[service]" with value "9cc4889d-0cd4-4c3b-8975-58de6d30db41"
        And I set a queryparam "sort" with value "<ordering>"
        When I send the request with GET method
        Then I expect the response status is 200
        And I expect that response json has an attribute "data.[0].id" with value "<first>"

        Examples:
            | ordering | first      |
            | id       | 2022-02-01 |
            | -id      | 2022-03-01 |

    Scenario Outline: Reject <reason>
        Given I set a queryparam "<param>" with value "<value>"
        When I send the request with GET method
        Then I expect the response status is 400
        And I expect that response json has an attribute "errors.[0].code" with value "invalid"

        Examples:
            | reason                   | param               | value       |
            | an unknown filter        | filter[not_a_field] | 1           |
            | an invalid service UUID  | filter[service]     | not-a-uuid  |
