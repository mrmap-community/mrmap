@fixtures:test_wms.json @fixtures:test_keywords.json
Feature: Layer List Endpoint
    As an API client,
    I want to search for layer,
    so that I can find relevant map content.

    Background: Setup baseurl, content-type and payload
        Given I use the endpoint http://localhost:8000/api/registry/layers/16b93d90-6e2e-497a-b26d-cadbe60ab76e

    Scenario: Can retrieve as anonymous user
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "data"
        Then I expect that "8" queries where made

    Scenario: Can retrieve camelCase sparse history fields and a relationship
        Given I set a queryparam "fields[Layer]" with value "createdAt,lastModifiedAt,service"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "data.attributes.createdAt"
        Then I expect that response json has an attribute "data.attributes.lastModifiedAt"
        Then I expect that response json has an attribute "data.relationships.service.data.id" with value "cd16cc1f-3abb-4625-bb96-fbe80dbe23e3"

    Scenario: Reports no access rules for an unconfigured layer
        Given I use the endpoint http://localhost:8000/api/registry/layers/05977f90-3bd9-4017-95e1-5252735d213f
        And I set a queryparam "fields[Layer]" with value "isSecured,isSpatialSecured"
        When I send the request with GET method
        Then I expect the response status is 200
        And I expect that response json has an attribute "data.attributes.isSecured" with value "false"
        And I expect that response json has an attribute "data.attributes.isSpatialSecured" with value "false"

    Scenario Outline: Can include <relation>
        Given I set a queryparam "include" with value "<relation>"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "<attribute>" with value "<type>"

        Examples:
            | relation              | attribute         | type                      |
            | service               | included.[0].type | WebMapService             |
            | keywords              | included.[0].type | Keyword                   |
            | service.operationUrls | included.[2].type | WebMapServiceOperationUrl |
            | styles                | included.[0].type | Style                     |
            | createdBy             | included.[0].type | User                      |
            | lastModifiedBy        | included.[0].type | User                      |
