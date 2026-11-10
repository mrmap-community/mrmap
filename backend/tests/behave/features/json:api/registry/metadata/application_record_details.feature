@fixtures:test_keywords.json @fixtures:test_crs.json @fixtures:test_csw.json @fixtures:test_applicationmetadata.json
Feature: Application metadata record detail
    Curators can inspect a parsed application record and follow its related lists without
    changing it, as they do with the dataset and service records.

    Background:
        Given I use the endpoint http://localhost:8000/api/registry/application-metadata/a11c0000-0000-4000-8000-000000000001

    Scenario: Read a record with every include used by its detail page
        Given I set a queryparam "include" with value "metadataContact,applicationContact,licence,keywords,referenceSystems,timeExtents,languages,categories,createdBy,lastModifiedBy,harvestedThrough"
        Given I set a queryparam "fields[CatalogueService]" with value "title,string_representation"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "data.type" with value "ApplicationMetadataRecord"
        Then I expect that response json has an attribute "data.attributes.title" with value "Anwendung Niederschlag"
        Then I expect that response json has an attribute "data.attributes.canEdit" with value "False"

    Scenario: Follow the record's keywords
        Given I use the endpoint http://localhost:8000/api/registry/application-metadata/a11c0000-0000-4000-8000-000000000001/keywords
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "data.[0].attributes.keyword" with value "Niederschlag"

    # the contact which provides the application answers under its own resource name, as
    # the dataset contact of a dataset record does
    Scenario: Follow the contact which provides the record
        Given I use the endpoint http://localhost:8000/api/registry/application-metadata/a11c0000-0000-4000-8000-000000000001/application-contact
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "data.[0].type" with value "ApplicationContact"
        Then I expect that response json has an attribute "data.[0].attributes.name" with value "Anwendungsbetreiber"

    # The nested catalogue list answers the catalogue of the record; the pagination
    # count of the nested catalogue endpoints counts unfiltered (as it does below
    # dataset-metadata), so the row itself is what carries the behaviour.
    Scenario: Follow the catalogue the record was harvested through
        Given I use the endpoint http://localhost:8000/api/registry/application-metadata/a11c0000-0000-4000-8000-000000000001/csws
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "data.[0].id" with value "9cc4889d-0cd4-4c3b-8975-58de6d30db41"

    # The remaining nested routes of the record answer like those of the dataset record; the
    # fixture carries no reference system, licence or time extent, so their lists are empty.
    Scenario Outline: Follow the record's <relation>
        Given I use the endpoint http://localhost:8000/api/registry/application-metadata/a11c0000-0000-4000-8000-000000000001/<relation>
        When I send the request with GET method
        Then I expect the response status is 200

        Examples:
            | relation          |
            | metadata-contact  |
            | referencesystems  |
            | licence           |
