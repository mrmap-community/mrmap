@fixtures:test_crs.json @fixtures:test_wfs.json @fixtures:test_keywords.json
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

    Scenario: Can retrieve camelCase sparse history fields and a relationship
        Given I set a queryparam "fields[FeatureType]" with value "createdAt,lastModifiedAt,service"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "data.attributes.createdAt"
        Then I expect that response json has an attribute "data.attributes.lastModifiedAt"
        Then I expect that response json has an attribute "data.relationships.service.data.id" with value "9cc4889d-0cd4-4c3b-8975-58de6d30db41"

    Scenario: Reports no access rules for an unconfigured feature type
        Given I set a queryparam "fields[FeatureType]" with value "isSecured,isSpatialSecured"
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
            | relation              | attribute         | type                          |
            | service               | included.[0].type | WebFeatureService             |
            | keywords              | included.[0].type | Keyword                       |
            | service.operationUrls | included.[1].type | WebFeatureServiceOperationUrl |
            | createdBy             | included.[0].type | User                          |
            | lastModifiedBy        | included.[0].type | User                          |
