@fixtures:test_harvesting_states.json
Feature: HarvestingLog List Endpoint
    As a CSW administrator,
    I want to list, filter and sort the log lines of the harvesting runs,
    so that the warnings and errors of a run are reachable and ordered (#1080).

    # The fixture answers four lines: three of run 1080101 (an info at quarter past one,
    # a warning of kind 0 at twenty, an error at half past) and one info of run 1080102
    # at ten past three. The model has no default order, so every scenario which names
    # the first line also names the order it reads the answer in. The scenarios of the
    # flat endpoint scope on the three runs of the fixture: the `add_harvestingjob`
    # feature runs before this one and writes log lines of its own, and rows left by
    # other features are none of this endpoint's question.
    # The `extented_description` file of a line stays behind an explicit read: the list
    # answers the line, never the content of the file.

    Background: Setup base url
        Given I use the endpoint http://localhost:8000/api/registry/harvesting/harvesting-logs

    Scenario: Can retrieve the lines of the fixture runs as anonymous user
        Given I set a queryparam "filter[harvesting_job__in]" with value "1080101,1080102,1080103"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "meta.pagination.count" with value "4"

    # The lines of a run were only reachable through the nested route of exactly that
    # run; now the flat endpoint answers them by the run they belong to.
    Scenario Outline: Can <action>
        Given I set a queryparam "<param>" with value "<value>"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "meta.pagination.count" with value "<count>"

        Examples:
            | action              | param                      | value                            | count |
            | filter by run       | filter[harvesting_job]     | 1080101                          | 3     |
            | filter by run       | filter[harvesting_job]     | 1080102                          | 1     |
            | filter many runs    | filter[harvesting_job__in] | 1080101,1080102                  | 4     |

    # The levels read against their enum: fatal is 0 and debug is 4. The kind belongs
    # to the line, and many kinds answer as a comma separated list.
    Scenario Outline: Can <action>
        Given I set a queryparam "filter[harvesting_job__in]" with value "1080101,1080102,1080103"
        Given I set a queryparam "<param>" with value "<value>"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "meta.pagination.count" with value "<count>"

        Examples:
            | action                            | param                | value    | count |
            | filter by level                   | filter[level]        | 3        | 2     |
            | filter louder levels of the scale | filter[level__lte]   | 2        | 2     |
            | filter numerically higher levels  | filter[level__gte]   | 3        | 2     |
            | filter by kind                    | filter[kind]         | 0        | 1     |
            | filter many kinds                 | filter[kind__in]     | 0,1      | 1     |
            | filter by timestamp               | filter[timestamp__gt] | 2026-11-05T01:25:00Z | 2   |
            | filter a timestamp range          | filter[timestamp__range] | 2026-11-05T01:15:00Z,2026-11-05T01:25:00Z | 1 |

    # The warnings and errors an administrator wants are the lines BELOW the info of
    # an ordinary run. Asked with the run and read in the order of their own
    # timestamps, the answer is the noise of exactly that run in the order it happened.
    Scenario: Can read the warnings and errors of one run in the order of their timestamps
        Given I set a queryparam "filter[harvesting_job]" with value "1080101"
        Given I set a queryparam "filter[level__lte]" with value "2"
        Given I set a queryparam "sort" with value "timestamp"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "meta.pagination.count" with value "2"
        Then I expect that response json has an attribute "data.[0].id" with value "1080202"
        Then I expect that response json has an attribute "data.[1].id" with value "1080203"

    # Unlike the run itself, every log line really has a timestamp, so both directions
    # of it are offered and answered.
    Scenario Outline: Can sort the lines of the fixture runs by their own time
        Given I set a queryparam "filter[harvesting_job__in]" with value "1080101,1080102,1080103"
        Given I set a queryparam "sort" with value "<ordering>"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "data.[0].id" with value "<first>"

        Examples:
            | ordering   | first   |
            | timestamp  | 1080201 |
            | -timestamp | 1080204 |

    # A term which is not offered is refused rather than quietly ignored.
    Scenario: Can't sort by a field which is not offered
        Given I set a queryparam "sort" with value "description"
        When I send the request with GET method
        Then I expect the response status is 400
        Then I expect that response json has an attribute "errors.[0].code" with value "invalid"

    # The nested route of the run answers the same lines and keeps its parent filter.
    Scenario: Can retrieve the lines of one run through its nested route
        Given I use the endpoint http://localhost:8000/api/registry/harvesting/harvesting-jobs/1080101/harvesting-logs
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "meta.pagination.count" with value "3"

    # The stored response behind a line is read per line: the list answers whether
    # one exists and never the file itself. A list which answers the download names
    # a download per row and widens the read access #888 bounds for these very
    # files; the content belongs to the line read by a caller allowed to read the
    # run (#1083).
    Scenario: The list of lines names a stored response without answering the file
        Given I set a queryparam "filter[harvesting_job]" with value "1080101"
        Given I set a queryparam "sort" with value "id"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "data.[0].attributes.hasExtendedDescription" with value "false"
        Then I expect that response json has an attribute "data.[1].attributes.hasExtendedDescription" with value "true"
        Then I expect that response json does not have an attribute "data.[1].attributes.extentedDescription"

    # The nested list of the run is the same answer for the same rows.
    Scenario: The nested list of a run keeps the stored response out of its rows too
        Given I use the endpoint http://localhost:8000/api/registry/harvesting/harvesting-jobs/1080101/harvesting-logs
        Given I set a queryparam "sort" with value "id"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "data.[1].attributes.hasExtendedDescription" with value "true"
        Then I expect that response json does not have an attribute "data.[0].attributes.extentedDescription"
        Then I expect that response json does not have an attribute "data.[1].attributes.extentedDescription"

    # Read on its own - the act of the caller who reads the run - the line answers
    # the response stored behind it.
    Scenario: A line read on its own answers its stored response
        Given I use the endpoint http://localhost:8000/api/registry/harvesting/harvesting-logs/1080202
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "data.attributes.hasExtendedDescription" with value "true"
        Then I expect that response json has an attribute "data.attributes.extentedDescription"
