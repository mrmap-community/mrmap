@fixtures:test_wms.json @fixtures:test_keywords.json
Feature: WebMapService List Endpoint
    As an API client,
    I want to search for web map services,
    so that I can find relevant map content.

    Background: Setup base url
        Given I use the endpoint http://localhost:8000/api/registry/wms

    Scenario: Can retrieve list as anonymous user
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "meta.pagination.count" with value "2"
        Then I expect that "22" queries where made

    Scenario Outline: Can <action>
        Given I set a queryparam "<param>" with value "<value>"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "meta.pagination.count" with value "<count>"

        Examples:
            | action             | param                      | value         | count |
            | search by title    | filter[search]             | WMS1          | 1     |
            | search by abstract | filter[search]             | wms1 abstract | 1     |
            | search by keywords | filter[search]             | meteorology   | 1     |
            | filter by title    | filter[title.icontains]    | WMS1          | 1     |
            | filter by abstract | filter[abstract.icontains] | wms1 abstract | 1     |

    # The filter value is a whole GeoJSON polygon; it stays on its own step instead of blowing the
    # examples table above up to 220 characters per row.
    Scenario: Can filter by bbox
        Given I set a queryparam "filter[bboxLatLon.contains]" with value "{'type': 'Polygon', 'coordinates': [[[7.062835693359375, 50.043911679834615], [7.568206787109375, 50.043911679834615], [7.568206787109375, 50.39451208023374], [7.062835693359375, 50.39451208023374], [7.062835693359375, 50.043911679834615]]]}"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "meta.pagination.count" with value "1"

    # Scenario: Can include layers
    #     Given I set a queryparam "include" with value "layers"
    #     When I send the request with GET method
    #     Then I expect the response status is 200
    #     Then I expect that response json has an attribute "included.[0].type" with value "Layer"
    #     Then I expect that "14" queries where made

    Scenario Outline: Can include <relation>
        Given I set a queryparam "include" with value "<relation>"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "included.[0].type" with value "<type>"

        Examples:
            | relation        | type                       |
            | keywords        | Keyword                    |
            | operationUrls   | WebMapServiceOperationUrl  |
            | serviceContact  | MetadataContact            |
            | metadataContact | MetadataContact            |
            | createdBy       | User                       |
            | lastModifiedBy  | User                       |
