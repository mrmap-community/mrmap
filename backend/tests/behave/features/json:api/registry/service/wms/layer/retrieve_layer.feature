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
        Then I expect that "12" queries where made

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