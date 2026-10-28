@fixtures:test_keywords.json @fixtures:test_datasetmetadata.json @fixtures:test_csw.json
Feature: CatalogueService List Endpoint
    As an API client,
    I want to search for csw,
    so that I can find relevant features.

    Background: Setup baseurl, content-type and payload
        Given I use the endpoint http://localhost:8000/api/registry/csw

    Scenario: Can retrieve list as anonymous user
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "meta.pagination.count" with value "4"

    Scenario: Published counts describe records linked to the catalogue
        Given I set a queryparam "filter[id]" with value "9cc4889d-0cd4-4c3b-8975-58de6d30db41"
        Given I set a queryparam "fields[CatalogueService]" with value "harvestedDatasetCount,harvestedServiceCount,harvestedTotalCount"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "data.[0].attributes.harvestedDatasetCount" with value "2"
        Then I expect that response json has an attribute "data.[0].attributes.harvestedServiceCount" with value "0"
        Then I expect that response json has an attribute "data.[0].attributes.harvestedTotalCount" with value "2"

    Scenario Outline: Can <action>
        Given I set a queryparam "<param>" with value "<value>"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "meta.pagination.count" with value "<count>"

        Examples:
            | action             | param                      | value       | count |
            | search by title    | filter[search]             | CSW1        | 1     |
            | search by abstract | filter[search]             | abstract1   | 1     |
            | search by keywords | filter[search]             | meteorology | 2     |
            | filter by title    | filter[title.icontains]    | CSW1        | 1     |
            | filter by abstract | filter[abstract.icontains] | abstract1   | 1     |

    # We no longer support this, cause it could be over 600k of items
    # Scenario: Can include dataset metadata
    #     Given I set a queryparam "include" with value "harvestedDatasets"
    #     When I send the request with GET method
    #     Then I expect the response status is 200
    #     Then I expect that response json has an attribute "included.[0].type" with value "DatasetMetadataRecord"

    Scenario Outline: Can include <relation>
        Given I set a queryparam "include" with value "<relation>"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "included.[0].type" with value "<type>"

        Examples:
            | relation        | type                         |
            | keywords        | Keyword                      |
            | operationUrls   | CatalogueServiceOperationUrl |
            | serviceContact  | MetadataContact              |
            | metadataContact | MetadataContact              |
            | createdBy       | User                         |
            | lastModifiedBy  | User                         |
