@fixtures:test_keywords.json @fixtures:test_crs.json @fixtures:test_csw.json @fixtures:test_datasetmetadata.json
Feature: Metadata record detail
    Curators can inspect the parsed record and follow its related lists without changing it.

    Background:
        Given I use the endpoint http://localhost:8000/api/registry/dataset-metadata/d8b50d33-2ad7-4a41-bd0d-2d518ea10fd4

    Scenario: Read a record with every include used by its detail page
        Given I set a queryparam "include" with value "metadataContact,datasetContact,licence,keywords,referenceSystems,timeExtents,languages,categories,createdBy,lastModifiedBy,harvestedThrough"
        Given I set a queryparam "fields[CatalogueService]" with value "title,string_representation"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "data.type" with value "DatasetMetadataRecord"
        Then I expect that response json has an attribute "data.attributes.title" with value "Niederschlag an RBSN Stationen"
        Then I expect that response json has an attribute "data.attributes.canEdit" with value "False"

    Scenario: Follow the record's keywords
        Given I use the endpoint http://localhost:8000/api/registry/dataset-metadata/d8b50d33-2ad7-4a41-bd0d-2d518ea10fd4/keywords
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "data.[0].attributes.keyword" with value "Niederschlag"
