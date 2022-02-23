Feature: MapContextLayer Move Endpoint
    As an API client,
    I want to add mapcontextlayers,
    so that I can configure map applications.

    Background: Setup baseurl, content-type and payload
        Given I use the endpoint http://localhost:8000/api/v1/registry/mapcontextlayers/8/
        Given I set the content type of the request to application/vnd.api+json

    Scenario: Can move as authenticated user to position 0
        Given I set the request payload to:
            """
            {
                "data": {
                    "type": "MapContextLayer",
                    "id": "8",
                    "attributes": {
                        "position": "0"
                    }
                }
            }
            """
        Given I am logged in as mrmap with password mrmap
        When I send the request with PATCH method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "data.attributes.lft" with value "2"
        Then I expect that response json has an attribute "data.attributes.rght" with value "3"
        Then I expect that response json has an attribute "data.attributes.treeId" with value "2"
        Then I expect that response json has an attribute "data.attributes.level" with value "1"

    Scenario: Can move as authenticated user to position 1
        Given I set the request payload to:
            """
            {
                "data": {
                    "type": "MapContextLayer",
                    "id": "8",
                    "attributes": {
                        "position": "1"
                    }
                }
            }
            """
        Given I am logged in as mrmap with password mrmap
        When I send the request with PATCH method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "data.attributes.lft" with value "4"
        Then I expect that response json has an attribute "data.attributes.rght" with value "5"
        Then I expect that response json has an attribute "data.attributes.treeId" with value "2"
        Then I expect that response json has an attribute "data.attributes.level" with value "1"

    Scenario: Can't move as authenticated user without permissions
        Given I set the request payload to:
            """
            {
                "data": {
                    "type": "MapContextLayer",
                    "id": "8",
                    "attributes": {
                        "position": "0"
                    }
                }
            }
            """
        Given I am logged in as User1 with password User1
        When I send the request with PATCH method
        Then I expect the response status is 403

    Scenario: Can't move as anonymous user
        Given I set the request payload to:
            """
            {
                "data": {
                    "type": "MapContextLayer",
                    "id": "8",
                    "attributes": {
                        "position": "0"
                    }
                }
            }
            """
        When I send the request with PATCH method
        Then I expect the response status is 401
