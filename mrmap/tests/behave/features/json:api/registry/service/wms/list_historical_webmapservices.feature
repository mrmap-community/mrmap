Feature: Historical WebMapService List Endpoint
    As an API client,
    I want to search for historical web map services,
    so that I can find relevant changelog.

    Background: Setup baseurl, content-type and payload
        Given I use the endpoint http://localhost:8000/api/registry/wms-historical

    Scenario: Can retrieve list as anonymous user
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "meta.pagination.count" with value "2"
        Then I expect that response json has an attribute "data.[0].id" with value "40d6bddd-6e8b-4487-b3ed-ee2a4ac5dee2"
        Then I expect that response json has an attribute "data.[0].attributes.delta" with value "[{'field': 'title', 'old': 'WMS1', 'new': 'WMS1 huhu'}, {'field': 'abstract', 'old': 'wms1 abstract', 'new': 'wms1 abstract hihi'}]"

        Then I expect that "13" queries where made

    Scenario: Can include historyUser
        Given I set a queryparam "include" with value "historyUser"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "included.[0].type" with value "User"

    Scenario: Can include historyRelation
        Given I set a queryparam "include" with value "historyRelation"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "included.[0].type" with value "WebMapService"

