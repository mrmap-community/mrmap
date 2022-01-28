Feature: Related AllowedWebMapServiceOperation for wms List Endpoint
    As an API client,
    I want to add new allowed operation configurations,
    so that I can secure services.

    Background: Setup baseurl, content-type and payload
        Given I use the endpoint http://localhost:8000/api/v1/registry/wms/cd16cc1f-3abb-4625-bb96-fbe80dbe23e3/allowed-wms-operations/

    Scenario: Can retrieve list as authenticated user
        Given I am logged in as User1 with password User1
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute meta.pagination.count with value 3

    Scenario: Can't retrieve list as anonymous user
        When I send the request with GET method
        Then I expect the response status is 403
