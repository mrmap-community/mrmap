@fixtures:test_crs.json @fixtures:test_wfs.json @fixtures:test_keywords.json
Feature: WebFeatureService Retrieve Endpoint
    As an API client,
    I want to search for web feature services,
    so that I can find relevant features.

    Background: Setup baseurl, content-type and payload
        Given I use the endpoint http://localhost:8000/api/registry/wfs/9cc4889d-0cd4-4c3b-8975-58de6d30db41

    Scenario: Can retrieve as anonymous user
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "data"

    Scenario Outline: Can include <relation>
        Given I set a queryparam "include" with value "<relation>"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "included.[0].type" with value "<type>"

        Examples:
            | relation        | type                          |
            | featuretypes    | FeatureType                   |
            | keywords        | Keyword                       |
            | operationUrls   | WebFeatureServiceOperationUrl |
            | serviceContact  | MetadataContact               |
            | metadataContact | MetadataContact               |
            | createdBy       | User                          |
            | lastModifiedBy  | User                          |