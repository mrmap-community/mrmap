@fixtures:test_background.json
Feature: BackgroundProcess List Endpoint
    As an API client,
    I want to get backgroundprocesses,
    so that I can show progress information of a process.

    Background: Setup base url
        Given I use the endpoint http://localhost:8000/api/notify/background-processes


    # The fixture answers the progress 0.0, 33.33, 50.0 and 10.0 of its four
    # processes and their date_created in ascending order, so the default page
    # - the newest process first - reads them in the order 4, 3, 2, 1.
    Scenario: Can get list of current background processes
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "meta.pagination.count" with value "4"

        Then I expect that response json has an attribute "data.[0].id" with value "4"
        Then I expect that response json has an attribute "data.[0].attributes.progress" with value "0.0"

        Then I expect that response json has an attribute "data.[1].attributes.progress" with value "33.33"
        Then I expect that response json has an attribute "data.[2].attributes.progress" with value "50.0"
        Then I expect that response json has an attribute "data.[3].attributes.progress" with value "10.0"

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
        Then I expect that response json has an attribute "data.[0].attributes.progress" with value "50.0"

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

    # The history screen of the frontend searches the past by its moments: the
    # fixture answers the four processes with a date_created on 2023-01-01, -02,
    # -03 and -04 and the failed one (id 2) with a done_at on 2023-01-02T13:00.
    Scenario Outline: Can filter processes by <field>
        Given I set a queryparam "<param>" with value "<value>"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "meta.pagination.count" with value "<count>"

        Examples:
            | field         | param                    | value                       | count |
            | created since | filter[dateCreated.gt]   | 2023-01-03T00:00:00+00:00   | 2     |
            | created until | filter[dateCreated.lt]   | 2023-01-03T00:00:00+00:00   | 2     |
            | created       | filter[dateCreated.range] | 2023-01-02T00:00:00+00:00,2023-01-03T23:59:59+00:00 | 2 |
            | decided since | filter[doneAt.gt]        | 2023-01-01T00:00:00+00:00   | 1     |

    # The history answers how long a decided process took, in seconds; the row
    # of the failed process is the third of the newest-first default page.
    Scenario: Can read the duration of a decided process
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "data.[2].id" with value "2"
        Then I expect that response json has an attribute "data.[2].attributes.duration" with value "3600.0"
        Then I expect that response json has an attribute "data.[0].attributes.duration" with value "None"

    # The list of the frontend pages its rows; the default page is the newest
    # first, so the second page of two holds the two older processes 2 and 1.
    Scenario Outline: Can page through the processes
        Given I set a queryparam "page[size]" with value "2"
        And I set a queryparam "page[number]" with value "<page>"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "meta.pagination.count" with value "4"
        Then I expect that response json has an attribute "data.[0].id" with value "<first>"

        Examples:
            | page | first |
            | 1    | 4     |
            | 2    | 2     |

    # The overview of the frontend orders its rows by the progress it renders.
    # The progress is no column but an annotation of the queryset - completed
    # processes at 100, processes without steps at 0 and the rest at the share
    # of their done steps - so the sort had to enter the whitelist with the
    # annotation (#1035). The fixture answers 0.0, 10.0, 33.33 and 50.0.
    Scenario Outline: Can sort processes by their progress
        Given I set a queryparam "sort" with value "<ordering>"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "data.[0].id" with value "<first>"

        Examples:
            | ordering  | first |
            | progress  | 4     |
            | -progress | 2     |

    # A rejected parameter belongs to the contract: a field the process does
    # not have stays answered with a bad request.
    Scenario: Can't sort by a field the process does not have
        Given I set a queryparam "sort" with value "not_a_field"
        When I send the request with GET method
        Then I expect the response status is 400
        Then I expect that response json has an attribute "errors.[0].code" with value "invalid"

    # The overview of the frontend starts with the processes which did not end yet. It asks for
    # them by the names the api answers the status with, while the database stores a number.
    Scenario Outline: Can filter processes by their status
        Given I set a queryparam "filter[status]" with value "<value>"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "meta.pagination.count" with value "<count>"

        Examples:
            | value           | count |
            | running         | 2     |
            | pending,running | 3     |
            | failed          | 1     |
            | 1               | 2     |
            | 3               | 1     |

    Scenario: Can't filter by a status which the api does not know
        Given I set a queryparam "filter[status]" with value "waiting"
        When I send the request with GET method
        Then I expect the response status is 400
        Then I expect that response json has an attribute "errors.[0].code" with value "invalid_choice"
