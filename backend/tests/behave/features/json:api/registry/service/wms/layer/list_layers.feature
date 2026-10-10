Feature: Layer List Endpoint
    As an API client,
    I want to search for layer,
    so that I can find relevant map content.

    Background: Setup baseurl, content-type and payload
        Given I use the endpoint http://localhost:8000/api/registry/layers

    Scenario: Can retrieve list as anonymous user
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "meta.pagination.count" with value "9"
        Then I expect that "22" queries where made

    Scenario: Can sort by lft
        Given I set a queryparam "sort" with value "mpttLft"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "meta.pagination.count" with value "9"
        Then I expect that response json has an attribute "data.[0].attributes.mpttLft" with value "1"

    Scenario Outline: Can <action>
        Given I set a queryparam "<param>" with value "<value>"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "meta.pagination.count" with value "<count>"

        Examples:
            | action             | param                      | value       | count |
            | search by title    | filter[search]             | node1.3.1   | 1     |
            | search by abstract | filter[search]             | node1.3.1   | 1     |
            | search by keywords | filter[search]             | meteorology | 1     |
            | filter by title    | filter[title.icontains]    | node1.3.1   | 1     |
            | filter by abstract | filter[abstract.icontains] | node1.3.1   | 1     |

    # The filter value is a whole GeoJSON polygon; it stays on its own step instead of blowing the
    # examples table above up to 220 characters per row.
    Scenario: Can filter by bbox
        Given I set a queryparam "filter[bboxLatLon.contains]" with value "{'type': 'Polygon', 'coordinates': [[[7.062835693359375, 50.043911679834615], [7.568206787109375, 50.043911679834615], [7.568206787109375, 50.39451208023374], [7.062835693359375, 50.39451208023374], [7.062835693359375, 50.043911679834615]]]}"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "meta.pagination.count" with value "8"

    Scenario: Can include service
        Given I set a queryparam "include" with value "service"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "included.[0].type" with value "WebMapService"
        Then I expect that "42" queries where made

    Scenario: Can include keywords
        Given I set a queryparam "include" with value "keywords"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "included.[0].type" with value "Keyword"
        Then I expect that "22" queries where made

    Scenario Outline: Can include <relation>
        Given I set a queryparam "include" with value "<relation>"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "<attribute>" with value "<type>"

        Examples:
            | relation              | attribute         | type                      |
            | service.operationUrls | included.[3].type | WebMapServiceOperationUrl |
            | styles                | included.[0].type | Style                     |
            | createdBy             | included.[0].type | User                      |
            | lastModifiedBy        | included.[0].type | User                      |
            | referenceSystems      | included.[0].type | ReferenceSystem           |