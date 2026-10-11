@no_fixtures
Feature: Filter historical layers by change type
    As an API client,
    I want to filter completed update-job changes by category.

    Background: Setup base url
        Given I use the endpoint http://localhost:8000/api/registry/historical-layers

    Scenario Outline: Change categories preserve the update-job scope
        Given I set a queryparam "filter[historyChangeReason]" with value "updatejob_id: -1"
        Given I set a queryparam "filter[changeType]" with value "<category>"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "meta.pagination.count" with value "0"

        Examples:
            | category  |
            | modified  |
            | unchanged |
            | removed   |
            | added     |

    Scenario: Unknown categories are rejected
        Given I set a queryparam "filter[historyChangeReason]" with value "updatejob_id: -1"
        Given I set a queryparam "filter[changeType]" with value "invalid"
        When I send the request with GET method
        Then I expect the response status is 400
