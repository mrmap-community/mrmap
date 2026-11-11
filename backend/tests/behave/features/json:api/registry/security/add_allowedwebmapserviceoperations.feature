@fixtures:test_wms.json @fixtures:test_keywords.json
Feature: AllowedWebMapServiceOperation Add Endpoint
    As an API client,
    I want to add new allowed operation configurations,
    so that I can secure services.

    Background: Setup baseurl, content-type and payload
        Given I use the endpoint http://localhost:8000/api/registry/security/allowed-wms-operations
        Given I set the content type of the request to application/vnd.api+json
        Given I set the request payload to:
            """
            {
                "data": {
                    "type": "AllowedWebMapServiceOperation",
                    "attributes": {
                        "description": "no spatial restriction"
                    },
                    "relationships": {
                        "operations": {
                            "data": [
                                {
                                    "id": 20,
                                    "type": "WebMapServiceOperation"
                                },
                                {
                                    "id": 21,
                                    "type": "WebMapServiceOperation"
                                }
                            ]
                        },
                        "secured_service": {
                            "data": {
                                "id": "cd16cc1f-3abb-4625-bb96-fbe80dbe23e3",
                                "type": "WebMapService"
                            }
                        },
                        "secured_layers": {
                            "data": [
                                {
                                    "id": "16b93d90-6e2e-497a-b26d-cadbe60ab76e",
                                    "type": "Layer"
                                },
                                {
                                    "id": "226e655b-b6cd-48a4-95e2-8bfe1c933790",
                                    "type": "Layer"
                                },
                                {
                                    "id": "c4ecdb87-31f4-4f30-8559-f577c8c59d08",
                                    "type": "Layer"
                                },
                                {
                                    "id": "ab645130-241d-4d6b-84c0-ab49c4bc6e4c",
                                    "type": "Layer"
                                },
                                {
                                    "id": "89fa6202-d252-4fb4-a772-22e2a441b312",
                                    "type": "Layer"
                                },
                                {
                                    "id": "d6e47039-b08a-4183-ae51-667083b8a803",
                                    "type": "Layer"
                                },
                                {
                                    "id": "4fdda4c4-c7bb-4525-a14d-f555ce0a9217",
                                    "type": "Layer"
                                },
                                {
                                    "id": "e95c2af1-9713-45fa-b6d4-7bb7e9813fdf",
                                    "type": "Layer"
                                }
                            ]
                        }
                    }
                }
            }
            """

    Scenario: Can add as authenticated user
        Given I am logged in as User1 with password User1
        When I send the request with POST method

        Then I expect the response status is 201

    Scenario: Can't add as anonymous user
        Given I am an anonymous user
        When I send the request with POST method
        Then I expect the response status is 403
        Then I expect that response json has an attribute "errors.[0].code" with value "not_authenticated"

    Scenario: Can't add incomplete subtrees of secured layers
        Given I am logged in as User1 with password User1
        Given I set the request payload to:
            """
            {
                "data": {
                    "type": "AllowedWebMapServiceOperation",
                    "attributes": {
                        "description": "no spatial restriction"
                    },
                    "relationships": {
                        "operations": {
                            "data": [
                                {
                                    "id": 20,
                                    "type": "WebMapServiceOperation"
                                },
                                {
                                    "id": 21,
                                    "type": "WebMapServiceOperation"
                                }
                            ]
                        },
                        "secured_service": {
                            "data": {
                                "id": "cd16cc1f-3abb-4625-bb96-fbe80dbe23e3",
                                "type": "WebMapService"
                            }
                        },
                        "secured_layers": {
                            "data": [
                                {
                                    "id": "16b93d90-6e2e-497a-b26d-cadbe60ab76e",
                                    "type": "Layer"
                                }
                            ]
                        }
                    }
                }
            }
            """
        When I send the request with POST method
        Then I expect the response status is 400

    Scenario: Can add subtrees of secured layers
        Given I am logged in as User1 with password User1
        Given I set the request payload to:
            """
            {
                "data": {
                    "type": "AllowedWebMapServiceOperation",
                    "attributes": {
                        "description": "no spatial restriction"
                    },
                    "relationships": {
                        "operations": {
                            "data": [
                                {
                                    "id": 20,
                                    "type": "WebMapServiceOperation"
                                },
                                {
                                    "id": 21,
                                    "type": "WebMapServiceOperation"
                                }
                            ]
                        },
                        "secured_service": {
                            "data": {
                                "id": "cd16cc1f-3abb-4625-bb96-fbe80dbe23e3",
                                "type": "WebMapService"
                            }
                        },
                        "secured_layers": {
                            "data": [
                                {
                                    "id": "226e655b-b6cd-48a4-95e2-8bfe1c933790",
                                    "type": "Layer"
                                },
                                {
                                    "id": "c4ecdb87-31f4-4f30-8559-f577c8c59d08",
                                    "type": "Layer"
                                },
                                {
                                    "id": "ab645130-241d-4d6b-84c0-ab49c4bc6e4c",
                                    "type": "Layer"
                                },
                                {
                                    "id": "89fa6202-d252-4fb4-a772-22e2a441b312",
                                    "type": "Layer"
                                }
                            ]
                        }
                    }
                }
            }
            """
        When I send the request with POST method
        Then I expect the response status is 201

    Scenario: Can't add layers of an other service
        Given I am logged in as User1 with password User1
        Given I set the request payload to:
            """
            {
                "data": {
                    "type": "AllowedWebMapServiceOperation",
                    "attributes": {
                        "description": "no spatial restriction"
                    },
                    "relationships": {
                        "operations": {
                            "data": [
                                {
                                    "id": 20,
                                    "type": "WebMapServiceOperation"
                                },
                                {
                                    "id": 21,
                                    "type": "WebMapServiceOperation"
                                }
                            ]
                        },
                        "secured_service": {
                            "data": {
                                "id": "cd16cc1f-3abb-4625-bb96-fbe80dbe23e3",
                                "type": "WebMapService"
                            }
                        },
                        "secured_layers": {
                            "data": [
                                {
                                    "id": "226e655b-b6cd-48a4-95e2-8bfe1c933790",
                                    "type": "Layer"
                                },
                                {
                                    "id": "c4ecdb87-31f4-4f30-8559-f577c8c59d08",
                                    "type": "Layer"
                                },
                                {
                                    "id": "ab645130-241d-4d6b-84c0-ab49c4bc6e4c",
                                    "type": "Layer"
                                },
                                {
                                    "id": "89fa6202-d252-4fb4-a772-22e2a441b312",
                                    "type": "Layer"
                                },
                                {
                                    "id": "05977f90-3bd9-4017-95e1-5252735d213f",
                                    "type": "Layer"
                                }
                            ]
                        }
                    }
                }
            }
            """
        When I send the request with POST method
        Then I expect the response status is 400

    Scenario: Can add with a spatial restriction
        Given I am logged in as User1 with password User1
        Given I set the request payload to:
            """
            {
                "data": {
                    "type": "AllowedWebMapServiceOperation",
                    "attributes": {
                        "description": "with a spatial restriction",
                        "allowedArea": {
                            "type": "MultiPolygon",
                            "coordinates": [[
                                [
                                    [12.6, 52.4],
                                    [13.4, 52.4],
                                    [13.4, 52.9],
                                    [12.6, 52.9],
                                    [12.6, 52.4]
                                ]
                            ]]
                        }
                    },
                    "relationships": {
                        "operations": {
                            "data": [
                                {
                                    "id": 20,
                                    "type": "WebMapServiceOperation"
                                },
                                {
                                    "id": 21,
                                    "type": "WebMapServiceOperation"
                                }
                            ]
                        },
                        "secured_service": {
                            "data": {
                                "id": "cd16cc1f-3abb-4625-bb96-fbe80dbe23e3",
                                "type": "WebMapService"
                            }
                        },
                        "secured_layers": {
                            "data": [
                                {
                                    "id": "226e655b-b6cd-48a4-95e2-8bfe1c933790",
                                    "type": "Layer"
                                },
                                {
                                    "id": "c4ecdb87-31f4-4f30-8559-f577c8c59d08",
                                    "type": "Layer"
                                },
                                {
                                    "id": "ab645130-241d-4d6b-84c0-ab49c4bc6e4c",
                                    "type": "Layer"
                                },
                                {
                                    "id": "89fa6202-d252-4fb4-a772-22e2a441b312",
                                    "type": "Layer"
                                }
                            ]
                        }
                    }
                }
            }
            """
        When I send the request with POST method
        Then I expect the response status is 201
        Then I expect that response json has an attribute "data.attributes.allowedArea.type" with value "MultiPolygon"

    # An EMPTY area is no area: the table refuses it through the check constraint
    # `registry_allowedwebmapserviceoperation_allowed_area_not_empty`. That refusal reached the
    # client as an IntegrityError with 500 (#1148), which is what a client sending the area of a
    # cleared drawing got. The refusal belongs to the payload, so it names the refused member.
    Scenario: Can't add an empty allowed area
        Given I am logged in as User1 with password User1
        Given I set the request payload to:
            """
            {
                "data": {
                    "type": "AllowedWebMapServiceOperation",
                    "attributes": {
                        "description": "with an empty spatial restriction",
                        "allowedArea": {
                            "type": "MultiPolygon",
                            "coordinates": []
                        }
                    },
                    "relationships": {
                        "operations": {
                            "data": [
                                {
                                    "id": 20,
                                    "type": "WebMapServiceOperation"
                                }
                            ]
                        },
                        "secured_service": {
                            "data": {
                                "id": "cd16cc1f-3abb-4625-bb96-fbe80dbe23e3",
                                "type": "WebMapService"
                            }
                        },
                        "secured_layers": {
                            "data": [
                                {
                                    "id": "226e655b-b6cd-48a4-95e2-8bfe1c933790",
                                    "type": "Layer"
                                },
                                {
                                    "id": "c4ecdb87-31f4-4f30-8559-f577c8c59d08",
                                    "type": "Layer"
                                },
                                {
                                    "id": "ab645130-241d-4d6b-84c0-ab49c4bc6e4c",
                                    "type": "Layer"
                                },
                                {
                                    "id": "89fa6202-d252-4fb4-a772-22e2a441b312",
                                    "type": "Layer"
                                }
                            ]
                        }
                    }
                }
            }
            """
        When I send the request with POST method
        Then I expect the response status is 400
        Then I expect that response json has an attribute "errors.[0].code" with value "invalid"
        Then I expect that response json has an attribute "errors.[0].source.pointer" with value "/data/attributes/allowedArea"

    # A MULTIPOLYGON column writes no POLYGON, and the database refuses it the same way.
    Scenario: Can't add an allowed area of another geometry type
        Given I am logged in as User1 with password User1
        Given I set the request payload to:
            """
            {
                "data": {
                    "type": "AllowedWebMapServiceOperation",
                    "attributes": {
                        "description": "with an area drawn as one polygon",
                        "allowedArea": {
                            "type": "Polygon",
                            "coordinates": [
                                [
                                    [12.6, 52.4],
                                    [13.4, 52.4],
                                    [13.4, 52.9],
                                    [12.6, 52.9],
                                    [12.6, 52.4]
                                ]
                            ]
                        }
                    },
                    "relationships": {
                        "operations": {
                            "data": [
                                {
                                    "id": 20,
                                    "type": "WebMapServiceOperation"
                                }
                            ]
                        },
                        "secured_service": {
                            "data": {
                                "id": "cd16cc1f-3abb-4625-bb96-fbe80dbe23e3",
                                "type": "WebMapService"
                            }
                        },
                        "secured_layers": {
                            "data": [
                                {
                                    "id": "226e655b-b6cd-48a4-95e2-8bfe1c933790",
                                    "type": "Layer"
                                },
                                {
                                    "id": "c4ecdb87-31f4-4f30-8559-f577c8c59d08",
                                    "type": "Layer"
                                },
                                {
                                    "id": "ab645130-241d-4d6b-84c0-ab49c4bc6e4c",
                                    "type": "Layer"
                                },
                                {
                                    "id": "89fa6202-d252-4fb4-a772-22e2a441b312",
                                    "type": "Layer"
                                }
                            ]
                        }
                    }
                }
            }
            """
        When I send the request with POST method
        Then I expect the response status is 400
        Then I expect that response json has an attribute "errors.[0].code" with value "invalid_geometry_type"
