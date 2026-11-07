@fixtures:test_csw.json
Feature: HarvestingJob List Endpoint
    As an API client,
    I want to list harvesting jobs,
    so that I can see which catalogue services are being harvested.

    Background: Setup base url
        Given I use the endpoint http://localhost:8000/api/registry/harvesting/harvesting-jobs

    Scenario: Can retrieve list as anonymous user
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "meta.pagination.count" with value "2"

    # The lookups of the primary key are generated from the model field: `exact` and `in` become number
    # filters, `contains` and `icontains` fall back to a char filter that compares the id as text, so
    # they do match. The allowed operations declare their number filters by hand as NumberInFilter and
    # there the same lookups never match (see the feature of the spatial rules).
    Scenario Outline: Can <action>
        Given I set a queryparam "<param>" with value "<value>"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "meta.pagination.count" with value "<count>"

        Examples:
            | action                 | param                        | value                                  | count |
            | filter by id           | filter[id]                   | 1                                      | 1     |
            | filter by id           | filter[id]                   | 3                                      | 0     |
            | filter by id contains  | filter[id.contains]          | 2                                      | 1     |
            | filter by id icontains | filter[id.icontains]         | 1                                      | 1     |
            | filter by id in        | filter[id.in]                | 1                                      | 1     |
            | filter by id in        | filter[id.in]                | 1,2                                    | 2     |
            | filter by service      | filter[service.id]           | 3df586c6-b89b-4ce5-980a-12dc3ca23df2  | 1     |
            | filter by service      | filter[service.id.contains]  | 3df586c6-b89b-4ce5-980a-12dc3ca23df2  | 1     |
            | filter by service      | filter[service.id.icontains] | 3DF586C6-B89B-4CE5-980A-12DC3CA23DF2  | 1     |
            | filter by service      | filter[service.id.in]        | 3df586c6-b89b-4ce5-980a-12dc3ca23df2,57cf66c2-3bde-49ad-b76e-bae49da57516 | 2 |

    # `is_unready` matches jobs without a done_at whose phase did not stay below COMPLETED. The job
    # of CSW2 is still pending (phase 0), the job of CSW3 was loaded in phase 4 without a done_at
    # and is therefore the unready one.
    Scenario Outline: Can filter the readiness of a job
        Given I set a queryparam "filter[is_unready]" with value "<value>"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "meta.pagination.count" with value "<count>"
        Then I expect that response json has an attribute "data.[0].id" with value "<job>"

        Examples:
            | value | count | job |
            | true  | 1     | 2   |
            | false | 1     | 1   |

    # The harvesting job list of the frontend is ordered by the id of the job, newest first.
    Scenario Outline: Can sort jobs by their id
        Given I set a queryparam "sort" with value "<ordering>"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "data.[0].id" with value "<first>"

        Examples:
            | ordering | first |
            | id       | 1     |
            | -id      | 2     |

    # The end of a run is the order the throughput of a catalogue is measured by: the screen which
    # recommends a page size asks the runs which finished last (#692). Both jobs of the fixture
    # never ended, so the order itself is nothing to assert here - what is asserted is that the
    # endpoint answers the order at all, because an unknown sort field is answered with a bad
    # request. The moment a run was made is ordered by the scenario below, which writes two runs
    # whose starts it knows.
    Scenario Outline: Can sort jobs by the end of the run
        Given I set a queryparam "sort" with value "<ordering>"
        When I send the request with GET method
        Then I expect the response status is 200

        Examples:
            | ordering |
            | doneAt   |
            | -doneAt  |

    # The harvesting activity card of a catalogue asks the runs of that catalogue newest first
    # (`sort=dateCreated` of HarvestingActivityCard.tsx) and names the moment of its last run. Both
    # is asserted on CSW1, which has no job in the fixture: the two runs of one catalogue are
    # written by the step and rolled back after the scenario, because the fixture is shared with
    # the scenarios above and below this one (#1079).
    Scenario: Orders the runs of a catalogue by the moment they were made
        Given the catalogue 9cc4889d-0cd4-4c3b-8975-58de6d30db41 has two finished runs started at 2024-05-03T08:00:00Z and 2024-05-04T08:30:00Z
        Given I set a queryparam "filter[service.id]" with value "9cc4889d-0cd4-4c3b-8975-58de6d30db41"
        Given I set a queryparam "sort" with value "-dateCreated"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "meta.pagination.count" with value "2"
        Then I expect the runs of the catalogue newest first

    # The time range a client asks a list of runs within (#1080) answers nothing while the column is
    # empty. The moment between the two runs of the setup above is inside the range for the newer
    # one only.
    Scenario: Answers the runs of a catalogue within a time range
        Given the catalogue 9cc4889d-0cd4-4c3b-8975-58de6d30db41 has two finished runs started at 2024-05-03T08:00:00Z and 2024-05-04T08:30:00Z
        Given I set a queryparam "filter[service.id]" with value "9cc4889d-0cd4-4c3b-8975-58de6d30db41"
        Given I set a queryparam "filter[dateCreated.gt]" with value "2024-05-04T00:00:00Z"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "meta.pagination.count" with value "1"
        Then I expect only the newer run of the catalogue

    # The records per minute of a run are its records against the time their download and their way
    # into the database measured. The jobs of the fixture carry no harvested records and no
    # durations, so they measured nothing and are answered without a throughput - a number which
    # was never measured must not look like a measurement (#692).
    Scenario: Answers no throughput for a job whose records measured nothing
        Given I set a queryparam "fields[HarvestingJob]" with value "id,records_per_minute"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "data.[0].attributes.recordsPerMinute" with value "None"
