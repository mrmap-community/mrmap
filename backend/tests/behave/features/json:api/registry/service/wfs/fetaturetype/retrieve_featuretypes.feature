Feature: Featuretype List Endpoint
    As an API client,
    I want to search for featuretype,
    so that I can find relevant map content.

    Background: Setup baseurl, content-type and payload
        Given I use the endpoint http://localhost:8000/api/registry/featuretypes/efba476a-d3ff-44f8-a0db-7f2c811f7247

    Scenario: Can retrieve as anonymous user
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "data"

    Scenario Outline: Can include <relation>
        Given I set a queryparam "include" with value "<relation>"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "<attribute>" with value "<type>"

        Examples:
            | relation              | attribute         | type                          |
            | service               | included.[0].type | WebFeatureService             |
            | keywords              | included.[0].type | Keyword                       |
            | service.operationUrls | included.[1].type | WebFeatureServiceOperationUrl |
            | createdBy             | included.[0].type | User                          |
            | lastModifiedBy        | included.[0].type | User                          |