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
