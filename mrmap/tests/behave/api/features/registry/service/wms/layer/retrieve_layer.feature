Feature: Layer List Endpoint
    As an API client,
    I want to search for layer,
    so that I can find relevant map content.

    Background: Setup baseurl, content-type and payload
        Given I use the endpoint http://localhost:8000/api/v1/registry/layers/16b93d90-6e2e-497a-b26d-cadbe60ab76e/

    Scenario: Can retrieve as anonymous user
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "data"
        Then I expect that "8" queries where made

    Scenario: Can include service
        Given I set a queryparam "include" with value "service"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "included.[0].type" with value "WebMapService"

    Scenario: Can include keywords
        Given I set a queryparam "include" with value "keywords"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "included.[0].type" with value "Keyword"

    Scenario: Can include service.operationUrls
        Given I set a queryparam "include" with value "service.operationUrls"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "included.[2].type" with value "WebMapServiceOperationUrl"

    Scenario: Can include styles
        Given I set a queryparam "include" with value "styles"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "included.[0].type" with value "Style"

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