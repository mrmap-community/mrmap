Feature: OwsContext detail view
    As an API client,
    I want to retrieve mapcontext documents according to the OGC OWS Context GeoJSON Encoding Standard,
    so that I get all information needed to initialize a map view with a hierarchy of WMS layers.

    Background: Setup base url
        Given I use the endpoint http://localhost:8000/mrmap-proxy/ows/1


    Scenario: Can retrieve as anonymous user
        When I send the request with GET method
        Then I expect the response status is 200
