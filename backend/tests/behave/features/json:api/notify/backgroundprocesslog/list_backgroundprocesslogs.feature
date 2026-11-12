@fixtures:test_background.json
Feature: BackgroundProcessLog List Endpoint
    As an API client,
    I want to get the log entries of background processes,
    so that I can inspect which errors a job of the history left behind.

    Background: Setup base url
        Given I use the endpoint http://localhost:8000/api/notify/background-processes-log

    # The fixture answers three log entries: two on the failed process 2 and one
    # on the running process 3, dated 2023-01-02T12:59, 2023-01-02T13:01 and
    # 2023-01-03T12:30.
    Scenario: Can get list of background process logs
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "meta.pagination.count" with value "3"

    # The history asks which errors one process left behind; the entry names its
    # process, so the facet is addressed by the process' id (#1208).
    Scenario Outline: Can <action>
        Given I set a queryparam "<param>" with value "<value>"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "meta.pagination.count" with value "<count>"

        Examples:
            | action                       | param                     | value | count |
            | filter by process            | filter[backgroundProcess]  | 2     | 2     |
            | filter by process            | filter[backgroundProcess]  | 3     | 1     |
            | filter by a set of processes | filter[backgroundProcess.in] | 1,2 | 2   |
            | filter by log type           | filter[logType]           | warning | 1   |

    # The job drawer reads the entries newest report first; the fixture dates
    # the entry of process 3 last and the one with id 1 first.
    Scenario Outline: Can sort logs by their moment
        Given I set a queryparam "sort" with value "<ordering>"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "data.[0].id" with value "<first>"

        Examples:
            | ordering | first |
            | date     | 1     |
            | -date    | 3     |

    # A rejected parameter belongs to the contract: a field the log does not
    # have stays answered with a bad request.
    Scenario: Can't sort by a field the log does not have
        Given I set a queryparam "sort" with value "not_a_field"
        When I send the request with GET method
        Then I expect the response status is 400
        Then I expect that response json has an attribute "errors.[0].code" with value "invalid"
