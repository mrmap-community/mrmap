@fixtures:test_wms.json @fixtures:test_keywords.json
Feature: WebMapService Retrieve Endpoint
    As an API client,
    I want to search for web map services,
    so that I can find relevant map content.

    Background: Setup baseurl, content-type and payload
        Given I use the endpoint http://localhost:8000/api/registry/wms/cd16cc1f-3abb-4625-bb96-fbe80dbe23e3

    Scenario: Can retrieve as anonymous user
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "data"
        Then I expect that "20" queries where made

    Scenario: Can include layers
        Given I set a queryparam "include" with value "layers"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "included.[0].type" with value "Layer"
        Then I expect that "31" queries where made


    Scenario Outline: Can include <relation>
        Given I set a queryparam "include" with value "<relation>"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "included.[0].type" with value "<type>"

        Examples:
            | relation        | type                      |
            | keywords        | Keyword                   |
            | operationUrls   | WebMapServiceOperationUrl |
            | serviceContact  | MetadataContact           |
            | metadataContact | MetadataContact           |
            | createdBy       | User                      |
            | lastModifiedBy  | User                      |