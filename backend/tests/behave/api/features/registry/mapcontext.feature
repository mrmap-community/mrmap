Feature: MapContext
    As an API client,
    I want to retrieve mapcontext documents according to the OGC OWS Context GeoJSON Encoding Standard,
    so that I get all information needed to initialize a map view with a hierarchy of WMS layers.

    @skip
    Scenario: Retrieve some existing map context as GeoJSON.
        Given an authorized session
        Given a request url http://localhost:8000/api/v1/registry/mapcontexts/1.json
        When the request sends GET
        Then the response status is OK
        And the response json matches
            """
            {
                "title": "GeoJSON OWS Context",
                "type": "object",
                "properties": {
                    "type": {
                        "type": "string"
                    },
                    "id": {
                        "type": "string",
                        "format": "uri"
                    }
                },
                "required": [
                    "type",
                    "id"
                ]
            }
            """
    @skip
    Scenario: Trying to retrieve a non-existing map context.
        Given an authorized session
        Given a request url http://localhost:8000/api/v1/registry/mapcontexts/2.json
        When the request sends GET
        Then the response status is 404

    @skip
    Scenario: Retrieve DWD test map context as GeoJSON and check layer tree structure.
        Given an authorized session
        Given a request url http://localhost:8000/api/v1/registry/mapcontexts/1.json
        When the request sends GET
        Then the response status is OK
        And the response json at $.features[0].properties.title is equal to "Wetter"
        And the response json at $.features[0].properties.folder is missing
        And the response json at $.features[1].properties.title is equal to "Temperatur über Grund"
        And the response json at $.features[1].properties.folder is missing
        And the response json at $.features[2].properties.title is equal to "Relative Feuchte"
        And the response json at $.features[2].properties.folder is missing
        And the response json at $.features[3].properties.title is equal to "Temperatur 2m"
        And the response json at $.features[3].properties.folder is missing
        And the response json at $.features[4].properties.title is equal to "Satellitenbild Europa"
        And the response json at $.features[4].properties.folder is equal to "Satellitenbilder"
        And the response json at $.features[5].properties.title is equal to "Satellitenbild Welt"
        And the response json at $.features[5].properties.folder is equal to "Satellitenbilder"
