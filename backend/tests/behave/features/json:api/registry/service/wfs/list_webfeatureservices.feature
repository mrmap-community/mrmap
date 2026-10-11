@fixtures:test_crs.json @fixtures:test_wfs.json @fixtures:test_keywords.json
Feature: WebFeatureService List Endpoint
    As an API client,
    I want to search for web feature services,
    so that I can find relevant features.

    Background: Setup baseurl, content-type and payload
        Given I use the endpoint http://localhost:8000/api/registry/wfs

    Scenario: Can retrieve list as anonymous user
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "meta.pagination.count" with value "2"

    Scenario Outline: Can <action>
        Given I set a queryparam "<param>" with value "<value>"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "meta.pagination.count" with value "<count>"

        Examples:
            | action             | param                      | value         | count |
            | search by title    | filter[search]             | WFS1          | 1     |
            | search by abstract | filter[search]             | wfs1 abstract | 1     |
            | search by keywords | filter[search]             | meteorology   | 1     |
            | filter by title    | filter[title.icontains]    | WFS1          | 1     |
            | filter by abstract | filter[abstract.icontains] | wfs1 abstract | 1     |

    # The filter value is a whole GeoJSON polygon; it stays on its own step instead of blowing the
    # examples table above up to 220 characters per row.
    Scenario: Can filter by bbox
        Given I set a queryparam "filter[bboxLatLon.contains]" with value "{'type': 'Polygon', 'coordinates': [[[7.062835693359375, 50.043911679834615], [7.568206787109375, 50.043911679834615], [7.568206787109375, 50.39451208023374], [7.062835693359375, 50.39451208023374], [7.062835693359375, 50.043911679834615]]]}"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "meta.pagination.count" with value "4"

    Scenario: Can include featuretypes
        Given I set a queryparam "include" with value "featuretypes"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "included.[0].type" with value "FeatureType"
        Then I expect that "38" queries where made

    Scenario Outline: Can include <relation>
        Given I set a queryparam "include" with value "<relation>"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "included.[0].type" with value "<type>"

        Examples:
            | relation        | type                          |
            | keywords        | Keyword                       |
            | operationUrls   | WebFeatureServiceOperationUrl |
            | serviceContact  | MetadataContact               |
            | metadataContact | MetadataContact               |
            | createdBy       | User                          |
            | lastModifiedBy  | User                          |