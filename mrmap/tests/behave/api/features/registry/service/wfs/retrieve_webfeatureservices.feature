Feature: WebFeatureService Retrieve Endpoint
    As an API client,
    I want to search for web feature services,
    so that I can find relevant features.

    Background: Setup baseurl, content-type and payload
        Given I use the endpoint http://localhost:8000/api/v1/registry/wfs/9cc4889d-0cd4-4c3b-8975-58de6d30db41/

    Scenario: Can retrieve as anonymous user
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "data"

    Scenario: Can include featuretypes
        Given I set a queryparam "include" with value "featuretypes"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "included.[0].type" with value "FeatureType"

    Scenario: Can include keywords
        Given I set a queryparam "include" with value "keywords"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "included.[0].type" with value "Keyword"

    Scenario: Can include operationUrls
        Given I set a queryparam "include" with value "operationUrls"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "included.[0].type" with value "WebFeatureServiceOperationUrl"

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