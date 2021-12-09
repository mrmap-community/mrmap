Feature: MapContext List Endpoint
    As an API client,
    I want to search mapcontexts,
    so that I can search for map applications.

    Background: Setup base url
        Given I use the endpoint http://localhost:8000/api/v1/registry/mapcontexts/

    Scenario: Can retrieve list as anonymous user
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute data.[0].relationships.map_context_layers.links.meta.count with value 5

    Scenario: Can retrieve list as authenticated user
        Given I am logged in as User1 with password User1
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute data.[0].relationships.map_context_layers.links.meta.count with value 5

    Scenario: Can retrieve list with included map context layers
        Given I set a queryparam include with value map_context_layers
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute included
        Then I expect that response json has an attribute data.[0].relationships.map_context_layers.meta.count with value 5
