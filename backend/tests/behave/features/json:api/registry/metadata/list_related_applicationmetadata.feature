@fixtures:test_keywords.json @fixtures:test_crs.json @fixtures:test_csw.json @fixtures:test_applicationmetadata.json
Feature: Related ApplicationMetadataRecord for csw List Endpoint
    As an API client,
    I want to list the application metadata records harvested through a catalogue,
    so that the records tab of the catalogue can show them beside the dataset records.

    Background: Setup base url
        Given I use the endpoint http://localhost:8000/api/registry/csw/9cc4889d-0cd4-4c3b-8975-58de6d30db41/application-metadata

    # Both records of the fixture carry CSW1 in `harvested_through` - the same row the
    # harvest writes when it imports a record (update_relations in
    # registry/models/harvest.py), so the nested route answers what a harvesting
    # catalogue really has. The resource type is what the records tab of #1279 derives
    # its card from.
    Scenario: Can list the application records of a catalogue as anonymous user
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "meta.pagination.count" with value "2"
        Then I expect that response json has an attribute "data.[0].type" with value "ApplicationMetadataRecord"

    # A catalogue which harvested no application record answers empty instead of
    # refusing: that is what lets the frontend card show its honest empty state.
    Scenario: A catalogue without application records answers empty
        Given I use the endpoint http://localhost:8000/api/registry/csw/3df586c6-b89b-4ce5-980a-12dc3ca23df2/application-metadata
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "meta.pagination.count" with value "0"

    # The list is about one catalogue but the route filters its records by
    # `harvested_through` and does not look the parent up: a well-formed id of a
    # catalogue that does not exist answers the empty list, like any filtered
    # list does, and only a malformed id is refused - get_parents_query_dict in
    # extras/viewsets.py turns the ValidationError of the uuid conversion into
    # the 404.
    Scenario: A well-formed catalogue id that does not exist answers empty
        Given I use the endpoint http://localhost:8000/api/registry/csw/00000000-0000-0000-0000-000000000000/application-metadata
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "meta.pagination.count" with value "0"

    Scenario: Refuses a malformed catalogue id
        Given I use the endpoint http://localhost:8000/api/registry/csw/not-a-uuid/application-metadata
        When I send the request with GET method
        Then I expect the response status is 404
        Then I expect that response json has an attribute "errors.[0].code" with value "not_found"
