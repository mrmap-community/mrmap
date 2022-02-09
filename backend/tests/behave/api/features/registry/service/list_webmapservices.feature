Feature: WebMapService List Endpoint
    As an API client,
    I want to search for web map services,
    so that I can find relevant map content.

    Background: Setup baseurl, content-type and payload
        Given I use the endpoint http://localhost:8000/api/v1/registry/wms/

    Scenario: Can retrieve list as anonymous user
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute meta.pagination.count with value 2

    Scenario: Can search by title
        Given I set a queryparam "filter[search]" with value "WMS1"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute meta.pagination.count with value 1

    Scenario: Can search by abstract
        Given I set a queryparam "filter[search]" with value "wms1 abstract"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute meta.pagination.count with value 1

    Scenario: Can search by keywords
        Given I set a queryparam "filter[search]" with value "meteorology"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute meta.pagination.count with value 1

    Scenario: Can filter by title
        Given I set a queryparam "filter[title.icontains]" with value "WMS1"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute meta.pagination.count with value 1

    Scenario: Can filter by abstract
        Given I set a queryparam "filter[abstract.icontains]" with value "wms1 abstract"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute meta.pagination.count with value 1

    Scenario: Can filter by bbox
        Given I set a queryparam "filter[bboxLatLon.contains]" with value "{'type': 'Polygon', 'coordinates': [[[7.062835693359375, 50.043911679834615], [7.568206787109375, 50.043911679834615], [7.568206787109375, 50.39451208023374], [7.062835693359375, 50.39451208023374], [7.062835693359375, 50.043911679834615]]]}"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute meta.pagination.count with value 2
