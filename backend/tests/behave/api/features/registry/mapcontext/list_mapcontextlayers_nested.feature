Feature: MapContext Related MapContexLayers Endpoint
    As an API client,
    I want to get all related MapContextLayers for a given MapContext object,
    so that I can fetch them in a seperated request.

    Background: Setup base url
        Given I use the endpoint http://localhost:8000/api/v1/registry/mapcontexts/1/mapcontextlayers/

    Scenario: Can retrieve list as anonymous user
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute meta.pagination.count with value 5

    Scenario: Can retrieve list as authenticated user
        Given I am logged in as User1 with password User1
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute meta.pagination.count with value 5
