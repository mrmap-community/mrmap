@fixtures:test_background.json
Feature: BackgroundProcess List Endpoint
    As an API client,
    I want to get backgroundprocesses,
    so that I can show progress information of a process.

    Background: Setup base url
        Given I use the endpoint http://localhost:8000/api/notify/background-processes


    Scenario: Can get list of current background processes
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "meta.pagination.count" with value "4"

        Then I expect that response json has an attribute "data.[1].attributes.progress" with value "0.0"

        Then I expect that response json has an attribute "data.[2].attributes.progress" with value "0.0"
        Then I expect that response json has an attribute "data.[3].attributes.progress" with value "0.0"

    Scenario Outline: Can filter by <field>
        Given I set a queryparam "filter[<field>.icontains]" with value "<value>"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "meta.pagination.count" with value "1"

        Examples:
            | field       | value         |
            | processType | process 2     |
            | description | description 2 |

    Scenario: Can filter by phase
        Given I set a queryparam "filter[phase.icontains]" with value "failed"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "meta.pagination.count" with value "1"

        Then I expect that response json has an attribute "data.[0].attributes.status" with value "failed"
        Then I expect that response json has an attribute "data.[0].attributes.progress" with value "0.0"

    # The filterset of this endpoint is generated from the fields of the model: exact and the
    # membership lookup are offered next to the icontains lookups above, and `contains` is case
    # sensitive while `icontains` is not.
    Scenario Outline: Can <action>
        Given I set a queryparam "<param>" with value "<value>"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "meta.pagination.count" with value "<count>"

        Examples:
            | action                 | param                        | value       | count |
            | filter by id           | filter[id]                   | 1           | 1     |
            | filter by id in        | filter[id.in]                | 1           | 1     |
            | filter by id in        | filter[id.in]                | 1,2         | 2     |
            | filter by process type | filter[processType.contains] | process     | 4     |
            | filter by process type | filter[processType.contains] | Process     | 0     |

    # The process type has choices on the model, so the generated filter is a choice filter and
    # refuses a value that is not one of them, while the membership lookup was never configured.
    Scenario Outline: Can't filter by <param> with an unusable value
        Given I set a queryparam "<param>" with value "<value>"
        When I send the request with GET method
        Then I expect the response status is 400
        Then I expect that response json has an attribute "errors.[0].code" with value "<code>"

        Examples:
            | param                  | value      | code           |
            | filter[processType]    | process 2  | invalid_choice |
            | filter[processType.in] | process 1  | invalid        |

    # The activity panel of the frontend shows the newest process first.
    Scenario Outline: Can sort processes by their id
        Given I set a queryparam "sort" with value "<ordering>"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "data.[0].id" with value "<first>"

        Examples:
            | ordering | first |
            | id       | 1     |
            | -id      | 4     |
