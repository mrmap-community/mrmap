@fixtures:test_wms.json @fixtures:test_keywords.json
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
        Then I expect that "10" queries where made

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

    # The layers of the fixture form a tree below WMS1 and one layer below WMS2. `service` is the
    # relation filter the frontend uses to show the layers of a single service, the depth and the
    # activity are plain number and boolean lookups.
    Scenario Outline: Can <action>
        Given I set a queryparam "<param>" with value "<value>"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "meta.pagination.count" with value "<count>"

        Examples:
            | action                    | param                    | value                                | count |
            | filter by service         | filter[service]          | cd16cc1f-3abb-4625-bb96-fbe80dbe23e3 | 8     |
            | filter by service         | filter[service]          | 1b195589-dcfa-403f-9e66-e7e1c0a67024 | 1     |
            | filter by mptt depth      | filter[mpttDepth]        | 2                                    | 4     |
            | filter by mptt depth      | filter[mpttDepth.gt]     | 0                                    | 7     |
            | filter by mptt depth      | filter[mpttDepth.gte]    | 1                                    | 7     |
            | filter by mptt depth      | filter[mpttDepth.lt]     | 1                                    | 2     |
            | filter by mptt depth      | filter[mpttDepth.lte]    | 1                                    | 5     |
            | filter by active layers   | filter[isActive]         | true                                 | 8     |
            | filter by active layers   | filter[isActive]         | false                                | 1     |

    # Eight layers of the fixture span the whole world and the layer of WMS2 is a small rectangle
    # inside it. Filtering with the world polygon matches the eight and, for `intersects`, the
    # ninth one as well; the same polygon is what `equals` compares its geometries against.
    Scenario Outline: Can filter by bbox <lookup> of the whole world
        Given I set a queryparam "filter[bboxLatLon.<lookup>]" with value "{'type': 'Polygon', 'coordinates': [[[-180, -90], [-180, 90], [180, 90], [180, -90], [-180, -90]]]}"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "meta.pagination.count" with value "<count>"

        Examples:
            | lookup     | count |
            | contains   | 8     |
            | covers     | 8     |
            | intersects | 9     |
            | equals     | 8     |

    # The small rectangle is the bounding box of the layer of WMS2, so `equals` must find exactly
    # it and `intersects` additionally finds the eight layers that contain it.
    Scenario Outline: Can filter by bbox <lookup> of one layer
        Given I set a queryparam "filter[bboxLatLon.<lookup>]" with value "{'type': 'Polygon', 'coordinates': [[[3, 1], [3, 2], [4, 2], [4, 1], [3, 1]]]}"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "meta.pagination.count" with value "<count>"

        Examples:
            | lookup     | count |
            | equals     | 1     |
            | intersects | 9     |

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
        Then I expect that "23" queries where made

    Scenario: Can include keywords
        Given I set a queryparam "include" with value "keywords"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "included.[0].type" with value "Keyword"
        Then I expect that "10" queries where made

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