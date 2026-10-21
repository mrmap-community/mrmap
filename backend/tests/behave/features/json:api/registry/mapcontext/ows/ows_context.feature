@fixtures:test_keywords.json @fixtures:test_mapcontext.json @fixtures:test_wms.json
Feature: OwsContext detail view
    As an API client,
    I want to retrieve mapcontext documents according to the OGC OWS Context GeoJSON Encoding Standard,
    so that I get all information needed to initialize a map view with a hierarchy of WMS layers.

    Background: Setup base url
        Given I use the endpoint http://localhost:8000/mrmap-proxy/ows/1


    Scenario: Can retrieve as anonymous user
        When I send the request with GET method
        Then I expect the response status is 200
        And I expect that response json has an attribute "properties.lang" with value "en"
        And I expect that response json has an attribute "properties.subtitle" with value "MapContext1"
        And I expect that response json has an attribute "features.[0].properties.folder" with value "/0"
        And I expect that response json has an attribute "features.[1].properties.folder" with value "/0/0"
        And I expect that response json has an attribute "features.[0].properties.offerings.[0].code" with value "http://www.opengis.net/spec/owc-geojson/1.0/req/wms"
