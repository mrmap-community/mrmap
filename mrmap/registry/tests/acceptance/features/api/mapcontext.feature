Feature: MapContext

Scenario: Retrieve GeoJSON MapContext
    Given the database contains a MapContext with id 1
    When I access the URL '/api/v1/registry/mapcontext/1'
    Then the HTTP response is a valid OWS Context GeoJSON document
