@fixtures:test_harvesting_states.json
Feature: PeriodicHarvestingJob List Endpoint
    As a CSW administrator,
    I want to list the harvest schedules ordered by the catalogue they harvest,
    so that the schedules of a catalogue are reachable by its title (#1080).

    # The fixture answers two schedules: the nightly harvest of catalogue Alpha (enabled)
    # and of catalogue Beta (disabled). The name of a schedule is the uuid the system
    # generates for the uniqueness of the celery task - it is no ordering an
    # administrator reads, which is why `sort=name` is refused. The `add_harvestingjob`
    # feature runs before this one and leaves a schedule of its own behind, so the
    # scenarios which count or sort scope on the two catalogues of the fixture.

    Background: Setup base url
        Given I use the endpoint http://localhost:8000/api/registry/harvesting/periodic-harvesting-jobs

    Scenario: Can retrieve the schedules of the two catalogues as anonymous user
        Given I set a queryparam "filter[service.id.in]" with value "aaaa1080-0000-4000-8000-00000000000a,bbbb1080-0000-4000-8000-00000000000b"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "meta.pagination.count" with value "2"

    # The readable ordering of the schedules is by the title of the catalogue
    # they harvest, both directions; the uuid of the service is refused since
    # it is no order an administrator reads (#1082).
    Scenario Outline: Can <action>
        Given I set a queryparam "filter[service.id.in]" with value "aaaa1080-0000-4000-8000-00000000000a,bbbb1080-0000-4000-8000-00000000000b"
        Given I set a queryparam "sort" with value "<ordering>"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "data.[0].id" with value "<first>"

        Examples:
            | action                | ordering  | first  |
            | sort by id            | id        | 1080502 |
            | sort by catalogue     | service__title   | 1080502 |
            | newest catalogue first | -service__title | 1080503 |

    # The states of the row an administrator sorts by: the enabled flag, the
    # last dispatch and the next one. Both schedules fired at the same moment,
    # so the last run is decided by the second term; the enabled one of Alpha
    # answers a next run while the disabled one answers nothing, which the
    # database sorts last ascending and first descending. The flag itself is
    # sorted by the database with false before true.
    Scenario Outline: Can <action>
        Given I set a queryparam "filter[service.id.in]" with value "aaaa1080-0000-4000-8000-00000000000a,bbbb1080-0000-4000-8000-00000000000b"
        Given I set a queryparam "sort" with value "<ordering>"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "data.[0].id" with value "<first>"

        Examples:
            | action                 | ordering         | first   |
            | sort by enabled        | enabled          | 1080503 |
            | enabled first          | -enabled         | 1080502 |
            | sort by last run       | -lastRunAt,-id   | 1080503 |
            | sort by next run       | nextRunAt        | 1080502 |
            | next run last descending | -nextRunAt     | 1080503 |

    # Whether the screen asks for a next run and when it is due: the enabled
    # schedule answers a moment it can sort and format, the disabled one nothing
    # - and the answer is never the German word which the endpoint answered
    # until now (#1082). The moment itself is pinned by
    # `tests/django/registry/tests_harvesting_schedule_answer.py`, because the
    # deployment decides by which offset an aware instant is printed.
    Scenario: Answers the next run of the enabled schedule as a moment
        Given I set a queryparam "filter[service.id.in]" with value "aaaa1080-0000-4000-8000-00000000000a"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "data.[0].attributes.nextRunAt"
        Then I expect that response json has an attribute "data.[0].attributes.lastRunAt"
        Then I expect that response json has an attribute "data.[0].attributes.totalRunCount" with value "0"

    Scenario: Answers nothing as next run of the disabled schedule
        Given I set a queryparam "filter[service.id.in]" with value "bbbb1080-0000-4000-8000-00000000000b"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "data.[0].attributes.nextRunAt" with value "None"

    # The half remembered title of a catalogue finds its schedule without its id.
    Scenario Outline: Can <action>
        Given I set a queryparam "<param>" with value "<value>"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "meta.pagination.count" with value "<count>"
        Then I expect that response json has an attribute "data.[0].id" with value "<first>"

        Examples:
            | action                    | param                             | value                                  | count | first   |
            | filter by whole title     | filter[service.title]             | Harvesting Catalogue Beta              | 1     | 1080503 |
            | search a title part       | filter[service.title.icontains]   | alpha                                  | 1     | 1080502 |
            | title case does not matter | filter[service.title.icontains]  | ALPHA                                  | 1     | 1080502 |
            | filter by catalogue id    | filter[service.id]                | bbbb1080-0000-4000-8000-00000000000b   | 1     | 1080503 |

    # The flag every row of the screen shows is also the facet its filter offers:
    # the disabled schedules are the ones an administrator looks for first, and
    # the endpoint answers the flag only because the screen asks for it (#1082).
    Scenario Outline: Can filter by the enabled flag
        Given I set a queryparam "filter[service.id.in]" with value "aaaa1080-0000-4000-8000-00000000000a,bbbb1080-0000-4000-8000-00000000000b"
        Given I set a queryparam "<param>" with value "<value>"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "meta.pagination.count" with value "1"
        Then I expect that response json has an attribute "data.[0].id" with value "<first>"

        Examples:
            | param            | value | first   |
            | filter[enabled]  | true  | 1080502 |
            | filter[enabled]  | false | 1080503 |

    # The generated name is not an ordering: it says nothing about the schedules
    # and this endpoint does not offer it (#1080).
    Scenario: Can't sort by the generated name
        Given I set a queryparam "sort" with value "name"
        When I send the request with GET method
        Then I expect the response status is 400
        Then I expect that response json has an attribute "errors.[0].code" with value "invalid"
