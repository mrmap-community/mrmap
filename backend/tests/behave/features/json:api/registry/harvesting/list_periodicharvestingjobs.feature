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

    # The readable ordering of the schedules is by the catalogue they harvest; the
    # uuid of the service is what groups them, both directions.
    Scenario Outline: Can <action>
        Given I set a queryparam "filter[service.id.in]" with value "aaaa1080-0000-4000-8000-00000000000a,bbbb1080-0000-4000-8000-00000000000b"
        Given I set a queryparam "sort" with value "<ordering>"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "data.[0].id" with value "<first>"

        Examples:
            | action                | ordering  | first  |
            | sort by id            | id        | 1080502 |
            | sort by catalogue     | service   | 1080502 |
            | newest catalogue first | -service | 1080503 |

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

    # The generated name is not an ordering: it says nothing about the schedules
    # and this endpoint does not offer it (#1080).
    Scenario: Can't sort by the generated name
        Given I set a queryparam "sort" with value "name"
        When I send the request with GET method
        Then I expect the response status is 400
        Then I expect that response json has an attribute "errors.[0].code" with value "invalid"
