@fixtures:test_registration_reference_work.json
Feature: Retained registration references and their retry mutation
    As a service editor,
    I want the failed references of a registration answerable per process, and the
    retry mutation closed to the clients which must not use it,
    so that the screen of #1265 reads its table over a pinned contract (#1265).

    # The fixture answers one completed registration process (1265010) with the two
    # work rows #1263 retains for it: one still PENDING (the run counted it skipped)
    # and one FAILED with its error kind. Successful references are no rows - the
    # counters answer them - so everything the process still "has" is unresolved.
    # The filters below are exactly what that screen sends; the accepting retry -
    # which dispatches the reference's own consumer - is pinned in the django tests
    # (`tests_reference_retry_api.py`), where no broker stands behind the ask.

    Background: Setup base url
        Given I use the endpoint http://localhost:8000/api/registry/harvesting/temporary-md-metadata-file

    Scenario: The screen asks the work of one process by its id
        Given I set a queryparam "filter[background_process__id]" with value "1265010"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "meta.pagination.count" with value "2"

    Scenario: The retry table asks only the decided failures of one process
        Given I set a queryparam "filter[background_process__id]" with value "1265010"
        Given I set a queryparam "filter[state]" with value "2"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "meta.pagination.count" with value "1"
        Then I expect that response json has an attribute "data.[0].id" with value "1265002"
        Then I expect that response json has an attribute "data.[0].attributes.errorKind" with value "fetch_unreachable"

    # The mutation is decided like the abort of a process: nobody without the
    # permission of its resource asks a fetch, anonymous included.
    Scenario: An anonymous client may not ask the retry
        Given I use the endpoint http://localhost:8000/api/registry/harvesting/temporary-md-metadata-file/1265002
        When I send the request with PATCH method
        Then I expect the response status is 403
        Then I expect that response json has an attribute "errors.[0].code" with value "not_authenticated"

    Scenario: A user without the permission of the resource may not ask the retry
        Given I am logged in as User1 with password User1
        Given I use the endpoint http://localhost:8000/api/registry/harvesting/temporary-md-metadata-file/1265002
        Given I set the request payload to:
        """
        {
            "data": {
                "type": "TemporaryMdMetadataFile",
                "id": "1265002",
                "attributes": {
                    "retry": true
                }
            }
        }
        """
        When I send the request with PATCH method
        Then I expect the response status is 403
        Then I expect that response json has an attribute "errors.[0].code" with value "permission_denied"
