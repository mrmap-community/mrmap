Feature: WebMapService Retrieve Endpoint
    As an API client,
    I want to search for web map services,
    so that I can find relevant map content.

    Background: Setup baseurl, content-type and payload
        Given I use the endpoint http://localhost:8000/api/v1/registry/wms/cd16cc1f-3abb-4625-bb96-fbe80dbe23e3/

    Scenario: Can retrieve as anonymous user
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "data"
        Then I expect that "13" queries where made

    # disabled for now
    # Scenario: Can include layers
    #     Given I set a queryparam "include" with value "layers"
    #     When I send the request with GET method
    #     Then I expect the response status is 200
    #     Then I expect that response json has an attribute "included.[0].type" with value "Layer"

    Scenario: Can include keywords
        Given I set a queryparam "include" with value "keywords"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "included.[0].type" with value "Keyword"

    Scenario: Can include operationUrls
        Given I set a queryparam "include" with value "operationUrls"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "included.[0].type" with value "WebMapServiceOperationUrl"

    Scenario: Can include serviceContact
        Given I set a queryparam "include" with value "serviceContact"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "included.[0].type" with value "MetadataContact"

    Scenario: Can include metadataContact
        Given I set a queryparam "include" with value "metadataContact"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "included.[0].type" with value "MetadataContact"

    Scenario: Can include createdBy
        Given I set a queryparam "include" with value "createdBy"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "included.[0].type" with value "User"

    Scenario: Can include lastModifiedBy
        Given I set a queryparam "include" with value "lastModifiedBy"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "included.[0].type" with value "User"