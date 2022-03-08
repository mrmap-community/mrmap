Feature: MapContext List Endpoint
    As an API client,
    I want to search mapcontexts,
    so that I can search for map applications.

    Background: Setup base url
        Given I use the endpoint http://localhost:8000/api/v1/registry/mapcontexts/

    Scenario: Can retrieve list as anonymous user
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "data.[0].relationships.mapContextLayers.meta.count" with value "5"

    Scenario: Can retrieve list as authenticated user
        Given I am logged in as User1 with password User1
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "data.[0].relationships.mapContextLayers.meta.count" with value "5"

    Scenario: Can search by title
        Given I set a queryparam "filter[search]" with value "MapContext1"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "meta.pagination.count" with value "1"

    Scenario: Can search by abstract
        Given I set a queryparam "filter[search]" with value "MapContext1"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "meta.pagination.count" with value "1"

    Scenario: Can filter by title
        Given I set a queryparam "filter[title.icontains]" with value "MapContext1"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "meta.pagination.count" with value "1"

    Scenario: Can filter by abstract
        Given I set a queryparam "filter[abstract.icontains]" with value "MapContext1"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "meta.pagination.count" with value "1"

    Scenario: Can include mapContextLayers
        Given I set a queryparam "include" with value "mapContextLayers"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "included.[0].type" with value "MapContextLayer"
        Then I expect that response json has an attribute "data.[0].relationships.mapContextLayers.meta.count" with value "5"
