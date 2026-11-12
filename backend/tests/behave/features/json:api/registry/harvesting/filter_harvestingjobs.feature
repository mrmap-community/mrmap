@fixtures:test_harvesting_states.json
Feature: HarvestingJob Filter Endpoint
    As a CSW administrator,
    I want to filter harvesting runs by phase, time, catalogue and stored files,
    so that the run list answers the questions of the screen (#1080).

    # The states of this feature are not in test_csw.json: its two jobs carry no phase
    # between 1 and 3, no end and no failed file, which are exactly what the facets of
    # the run list narrow. So the feature loads its own fixture instead of moving the
    # counts of every sibling feature which shares test_csw.json with the unit tests,
    # and `environment.py` removes its rows again when the feature is done.
    # The `add_harvestingjob` feature runs before this one and leaves its created runs
    # behind, so every scenario asks within the two catalogues of the fixture: the runs
    # of other catalogues are not the question of the facet under test. The default
    # order of the list is the creation of the run, newest first.

    Background: Setup base url
        Given I use the endpoint http://localhost:8000/api/registry/harvesting/harvesting-jobs

    Scenario: Can retrieve the runs of the two catalogues as anonymous user
        Given I set a queryparam "filter[service.id.in]" with value "aaaa1080-0000-4000-8000-00000000000a,bbbb1080-0000-4000-8000-00000000000b"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "meta.pagination.count" with value "3"

    # The fixture answers: job 1080101 of catalogue Alpha completed (phase 4) at two,
    # job 1080102 of Alpha is downloading records (phase 2) and did not end, job 1080103
    # of catalogue Beta aborted (phase 5) at four.
    Scenario Outline: Can <action>
        Given I set a queryparam "filter[service.id.in]" with value "aaaa1080-0000-4000-8000-00000000000a,bbbb1080-0000-4000-8000-00000000000b"
        Given I set a queryparam "<param>" with value "<value>"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "meta.pagination.count" with value "<count>"
        Then I expect that response json has an attribute "data.[0].id" with value "<job>"

        Examples:
            | action                | param               | value | count | job    |
            | filter by phase       | filter[phase]       | 4     | 1     | 1080101 |
            | filter by phase       | filter[phase]       | 5     | 1     | 1080103 |
            | filter below a phase  | filter[phase__lt]   | 3     | 1     | 1080102 |
            | filter above a phase  | filter[phase__gt]   | 4     | 1     | 1080103 |
            | filter many phases    | filter[phase__in]   | 4,5   | 2     | 1080101 |

    # The phases behind the running facet of the run list: 1, 2 and 3 are the work of a
    # harvest, and the runs which ended (4 and 5) are not among them.
    Scenario: Can ask the working runs of one catalogue
        Given I set a queryparam "filter[service.id]" with value "aaaa1080-0000-4000-8000-00000000000a"
        Given I set a queryparam "filter[phase__in]" with value "1,2,3"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "meta.pagination.count" with value "1"
        Then I expect that response json has an attribute "data.[0].id" with value "1080102"

    # `is_running` asks the run: made and not ended. It is named apart from
    # `is_unready`, which asks the celery state and counts a queued run and an aborted
    # one alike.
    Scenario Outline: Can filter the runs by whether they ended
        Given I set a queryparam "filter[service.id.in]" with value "aaaa1080-0000-4000-8000-00000000000a,bbbb1080-0000-4000-8000-00000000000b"
        Given I set a queryparam "filter[is_running]" with value "<value>"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "meta.pagination.count" with value "<count>"
        Then I expect that response json has an attribute "data.[0].id" with value "<job>"

        Examples:
            | value | count | job     |
            | true  | 1     | 1080102 |
            | false | 2     | 1080101 |

    # The first question after a night of harvesting: which runs ended in it? The range
    # takes two ISO 8601 values separated by a comma, the same lookups a background
    # process answers for its dates.
    Scenario Outline: Can <action>
        Given I set a queryparam "filter[service.id.in]" with value "aaaa1080-0000-4000-8000-00000000000a,bbbb1080-0000-4000-8000-00000000000b"
        Given I set a queryparam "<param>" with value "<value>"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "meta.pagination.count" with value "<count>"
        Then I expect that response json has an attribute "data.[0].id" with value "<job>"

        Examples:
            | action                  | param                      | value                                       | count | job     |
            | filter the runs of a night | filter[done_at__range]  | 2026-11-05T00:00:00Z,2026-11-05T03:30:00Z   | 1     | 1080101 |
            | filter both ends of the night | filter[done_at__range] | 2026-11-05T00:00:00Z,2026-11-05T05:00:00Z   | 2     | 1080101 |
            | filter runs ended late  | filter[done_at__gt]        | 2026-11-05T02:00:00Z                        | 1     | 1080103 |
            | filter runs ended early | filter[done_at__lt]        | 2026-11-05T02:30:00Z                        | 1     | 1080101 |
            | filter runs made early  | filter[date_created__range] | 2026-11-05T00:00:00Z,2026-11-05T02:00:00Z  | 1     | 1080101 |
            | filter runs made before the night | filter[date_created__lt] | 2026-11-05T00:00:00Z             | 1     | 1080103 |

    # The half remembered title of a catalogue is the lookup which finds its runs
    # without their ids; both spellings of the relation path answer it.
    Scenario Outline: Can <action>
        Given I set a queryparam "<param>" with value "<value>"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "meta.pagination.count" with value "<count>"
        Then I expect that response json has an attribute "data.[0].id" with value "<job>"

        Examples:
            | action              | param                             | value                     | count | job     |
            | search a known title part | filter[service.title.icontains] | alpha                     | 2     | 1080102 |
            | title case does not matter | filter[service.title.icontains] | ALPHA                     | 2     | 1080102 |
            | filter the whole title | filter[service.title]         | Harvesting Catalogue Beta | 1     | 1080103 |
            | underscore spelling | filter[service__title__icontains] | eta                       | 1     | 1080103 |

    # The files a run could not store, and the files still waiting for the database:
    # the facets narrow on the very subqueries the endpoint answers the counts with,
    # so a facet nobody chose costs nothing (#1037). Job 1080102 has one failed and one
    # waiting file; the runs which ended have no files at all.
    Scenario Outline: Can <action>
        Given I set a queryparam "filter[service.id.in]" with value "aaaa1080-0000-4000-8000-00000000000a,bbbb1080-0000-4000-8000-00000000000b"
        Given I set a queryparam "<param>" with value "<value>"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "meta.pagination.count" with value "<count>"
        Then I expect that response json has an attribute "data.[0].id" with value "<job>"

        Examples:
            | action           | param                       | value | count | job     |
            | runs which failed to store a file | filter[has_import_error]  | true  | 1     | 1080102 |
            | runs which stored all their files | filter[has_import_error]  | false | 2     | 1080101 |
            | runs with files waiting | filter[unhandled_records] | true  | 1     | 1080102 |
            | runs with nothing waiting | filter[unhandled_records] | false | 2     | 1080101 |

    # A facet which the endpoint does not declare is answered loudly: a filter the
    # filterset does not know is refused, it never silently answers the whole table.
    # Which filters exist, the api schema lists - they are the whole filter surface.
    Scenario: Can't filter by a field the resource does not have
        Given I set a queryparam "filter[not_a_field]" with value "1"
        When I send the request with GET method
        Then I expect the response status is 400
        Then I expect that response json has an attribute "errors.[0].code" with value "invalid"

    # The same holds for a lookup on a declared field: `phase` answers exact, in, lt
    # and gt - a text lookup on the number is the question the filterset does not ask.
    Scenario: Can't filter the phase by a lookup which is not declared
        Given I set a queryparam "filter[phase__contains]" with value "4"
        When I send the request with GET method
        Then I expect the response status is 400
        Then I expect that response json has an attribute "errors.[0].code" with value "invalid"
