Feature: AllowedWebMapServiceOperation Add Endpoint
    As an API client,
    I want to add new allowed operation configurations,
    so that I can secure services.

    Background: Setup baseurl, content-type and payload
        Given I use the endpoint http://localhost:8000/api/v1/registry/security/allowed-wms-operations/
        Given I set the content type of the request to application/vnd.api+json

    Scenario: Can add as authenticated user
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
                                    "id": "GetMap",
                                    "type": "WebMapServiceOperation"
                                },
                                {
                                    "id": "GetFeatureInfo",
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
        When I send the request with POST method

        Then I expect the response status is 201

    Scenario: Can't add as anonymous user
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
                                    "id": "GetMap",
                                    "type": "WebMapServiceOperation"
                                },
                                {
                                    "id": "GetFeatureInfo",
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
        When I send the request with POST method
        Then I expect the response status is 403

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
                                    "id": "GetMap",
                                    "type": "WebMapServiceOperation"
                                },
                                {
                                    "id": "GetFeatureInfo",
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
                                    "id": "GetMap",
                                    "type": "WebMapServiceOperation"
                                },
                                {
                                    "id": "GetFeatureInfo",
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
                                    "id": "GetMap",
                                    "type": "WebMapServiceOperation"
                                },
                                {
                                    "id": "GetFeatureInfo",
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