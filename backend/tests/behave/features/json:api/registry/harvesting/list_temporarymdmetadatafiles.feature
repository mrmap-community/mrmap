@fixtures:test_harvesting_states.json
Feature: TemporaryMdMetadataFile List Endpoint
    As a CSW administrator,
    I want to ask the temporary metadata files by the catalogue behind their run,
    so that the alert "harvesting incomplete" leads to records and not to a count (#1083).

    # The fixture answers two files, both of run 1080102 of catalogue Alpha: one the
    # import could not store and one still waiting. The model has no default order, so
    # every scenario which names the first row also names the order it reads in. The
    # `add_harvestingjob` feature runs before this one and leaves files of its own
    # behind, so the scenarios which count or sort scope on the two catalogues of the
    # fixture - the flat endpoint is `harvesting/temporary-md-metadata-file`, the
    # nested one under a run is plural.

    Background: Setup base url
        Given I use the endpoint http://localhost:8000/api/registry/harvesting/temporary-md-metadata-file

    Scenario: Can retrieve the files of the two catalogues as anonymous user
        Given I set a queryparam "filter[job.service.id.in]" with value "aaaa1080-0000-4000-8000-00000000000a,bbbb1080-0000-4000-8000-00000000000b"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "meta.pagination.count" with value "2"

    # The files which failed IN A run become the files which failed FOR a catalogue:
    # the job__service lookups answer the question of the alert, through the run.
    Scenario Outline: Can <action>
        Given I set a queryparam "<param>" with value "<value>"
        Given I set a queryparam "sort" with value "id"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "meta.pagination.count" with value "<count>"
        Then I expect that response json has an attribute "data.[0].id" with value "<first>"

        Examples:
            | action                    | param                    | value                                  | count | first   |
            | filter by catalogue       | filter[job.service]      | aaaa1080-0000-4000-8000-00000000000a   | 2     | 1080301 |
            | filter by catalogue id    | filter[job.service.id]   | aaaa1080-0000-4000-8000-00000000000a   | 2     | 1080301 |
            | filter many catalogues    | filter[job.service.id.in] | aaaa1080-0000-4000-8000-00000000000a,bbbb1080-0000-4000-8000-00000000000b | 2 | 1080301 |

    # The trail of the alert: the files this catalogue could not import.
    Scenario: Can ask the files a catalogue could not import
        Given I set a queryparam "filter[job.service]" with value "aaaa1080-0000-4000-8000-00000000000a"
        Given I set a queryparam "filter[has_import_error]" with value "true"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "meta.pagination.count" with value "1"
        Then I expect that response json has an attribute "data.[0].id" with value "1080301"

    # The request_id is the moment the catalogue was asked for this file; a screen
    # which lists the files of a run orders them by it in both directions.
    Scenario Outline: Can <action>
        Given I set a queryparam "filter[job.service.id.in]" with value "aaaa1080-0000-4000-8000-00000000000a,bbbb1080-0000-4000-8000-00000000000b"
        Given I set a queryparam "sort" with value "<ordering>"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "data.[0].id" with value "<first>"

        Examples:
            | action          | ordering    | first   |
            | sort by request | request_id  | 1080301 |
            | newest request  | -request_id | 1080302 |
