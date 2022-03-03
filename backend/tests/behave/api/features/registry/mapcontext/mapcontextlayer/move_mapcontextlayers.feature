Feature: MapContextLayer Move Endpoint
    As an API client,
    I want to add mapcontextlayers,
    so that I can configure map applications.

    Background: Setup baseurl, content-type and payload
        Given I use the endpoint http://localhost:8000/api/v1/registry/mapcontextlayers/10/
        Given I set the content type of the request to application/vnd.api+json

    Scenario: Can move 10 as authenticated user to parent 6, position 0 (first-child)
        Given I set the request payload to:
            """
            {
                "data": {
                    "type": "MapContextLayer",
                    "id": "10",
                    "attributes": {
                        "position": "0"
                    },
                    "relationships": {
                        "parent": {
                            "data": {
                                "id": "6",
                                "type": "MapContextLayer"
                            }
                        }
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

    Scenario: Can move 10 as authenticated user to parent 6, position 1
        Given I set the request payload to:
            """
            {
                "data": {
                    "type": "MapContextLayer",
                    "id": "10",
                    "attributes": {
                        "position": "1"
                    },
                    "relationships": {
                        "parent": {
                            "data": {
                                "id": "6",
                                "type": "MapContextLayer"
                            }
                        }
                    }
                }
            }
            """
        Given I am logged in as User2 with password User2
        When I send the request with PATCH method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "data.attributes.lft" with value "4"
        Then I expect that response json has an attribute "data.attributes.rght" with value "5"
        Then I expect that response json has an attribute "data.attributes.treeId" with value "2"
        Then I expect that response json has an attribute "data.attributes.level" with value "1"

    Scenario: Can move 10 as authenticated user to parent 6, position 2
        Given I set the request payload to:
            """
            {
                "data": {
                    "type": "MapContextLayer",
                    "id": "10",
                    "attributes": {
                        "position": "2"
                    },
                    "relationships": {
                        "parent": {
                            "data": {
                                "id": "6",
                                "type": "MapContextLayer"
                            }
                        }
                    }
                }
            }
            """
        Given I am logged in as User2 with password User2
        When I send the request with PATCH method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "data.attributes.lft" with value "8"
        Then I expect that response json has an attribute "data.attributes.rght" with value "9"
        Then I expect that response json has an attribute "data.attributes.treeId" with value "2"
        Then I expect that response json has an attribute "data.attributes.level" with value "1"

    Scenario: Can move 10 as authenticated user to parent 6, position 3 (last-child)
        Given I set the request payload to:
            """
            {
                "data": {
                    "type": "MapContextLayer",
                    "id": "10",
                    "attributes": {
                        "position": "3"
                    },
                    "relationships": {
                        "parent": {
                            "data": {
                                "id": "6",
                                "type": "MapContextLayer"
                            }
                        }
                    }
                }
            }
            """
        Given I am logged in as User2 with password User2
        When I send the request with PATCH method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "data.attributes.lft" with value "10"
        Then I expect that response json has an attribute "data.attributes.rght" with value "11"
        Then I expect that response json has an attribute "data.attributes.treeId" with value "2"
        Then I expect that response json has an attribute "data.attributes.level" with value "1"

    Scenario: Can not move 10 as authenticated user to parent 6, position 4 (out-of-range)
        Given I set the request payload to:
            """
            {
                "data": {
                    "type": "MapContextLayer",
                    "id": "10",
                    "attributes": {
                        "position": "4"
                    },
                    "relationships": {
                        "parent": {
                            "data": {
                                "id": "6",
                                "type": "MapContextLayer"
                            }
                        }
                    }
                }
            }
            """
        Given I am logged in as User2 with password User2
        When I send the request with PATCH method
        Then I expect the response status is 400
        Then I expect that response json has an attribute "errors.[0].detail" with value "position index out of range"
        Then I expect that response json has an attribute "errors.[0].source.pointer" with value "/data/attributes/position"



    Scenario: Can move as authenticated user to new parent with position 1
        Given I use the endpoint http://localhost:8000/api/v1/registry/mapcontextlayers/9/
        Given I set the request payload to:
            """
            {
                "data": {
                    "type": "MapContextLayer",
                    "id": "9",
                    "attributes": {
                        "position": "1"
                    },
                    "relationships": {
                        "parent": {
                            "data": {
                                "id": "6",
                                "type": "MapContextLayer"
                            }
                        }
                    }
                }
            }
            """
        Given I am logged in as User2 with password User2
        When I send the request with PATCH method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "data.attributes.lft" with value "4"
        Then I expect that response json has an attribute "data.attributes.rght" with value "5"
        Then I expect that response json has an attribute "data.attributes.treeId" with value "2"
        Then I expect that response json has an attribute "data.attributes.level" with value "1"


    Scenario: Validation Error is raised on moving root node
        Given I use the endpoint http://localhost:8000/api/v1/registry/mapcontextlayers/6/

        Given I set the request payload to:
            """
            {
                "data": {
                    "type": "MapContextLayer",
                    "id": "6",
                    "attributes": {
                        "position": "123"
                    }
                }
            }
            """
        Given I am logged in as User2 with password User2
        When I send the request with PATCH method
        Then I expect the response status is 400
        Then I expect that response json has an attribute "errors.[0].detail" with value "root node can not be moved"


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
