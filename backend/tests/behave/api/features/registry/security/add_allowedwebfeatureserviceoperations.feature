Feature: AllowedWebFeatureServiceOperation Add Endpoint
    As an API client,
    I want to add new allowed operation configurations,
    so that I can secure services.

    Background: Setup baseurl, content-type and payload
        Given I use the endpoint http://localhost:8000/api/v1/registry/security/allowed-wfs-operations/
        Given I set the content type of the request to application/vnd.api+json

    Scenario: Can add as authenticated user
        Given I am logged in as User1 with password User1
        Given I set the request payload to:
            """
            {
                "data": {
                    "type": "AllowedWebFeatureServiceOperation",
                    "attributes": {
                        "description": "no spatial restriction"
                    },
                    "relationships": {
                        "operations": {
                            "data": [
                                {
                                    "id": "GetFeature",
                                    "type": "WebFeatureServiceOperation"
                                },
                                {
                                    "id": "Transaction",
                                    "type": "WebFeatureServiceOperation"
                                }
                            ]
                        },
                        "secured_service": {
                            "data": {
                                "id": "9cc4889d-0cd4-4c3b-8975-58de6d30db41",
                                "type": "WebFeatureService"
                            }
                        },
                        "secured_feature_types": {
                            "data": [
                                {
                                    "id": "efba476a-d3ff-44f8-a0db-7f2c811f7247",
                                    "type": "FeatureType"
                                },
                                {
                                    "id": "fa8713a6-875f-48b4-95f2-f9bb7cf47001",
                                    "type": "FeatureType"
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
                    "type": "AllowedWebFeatureServiceOperation",
                    "attributes": {
                        "description": "no spatial restriction"
                    },
                    "relationships": {
                        "operations": {
                            "data": [
                                {
                                    "id": "GetFeature",
                                    "type": "WebFeatureServiceOperation"
                                },
                                {
                                    "id": "Transaction",
                                    "type": "WebFeatureServiceOperation"
                                }
                            ]
                        },
                        "secured_service": {
                            "data": {
                                "id": "9cc4889d-0cd4-4c3b-8975-58de6d30db41",
                                "type": "WebFeatureService"
                            }
                        },
                        "secured_feature_types": {
                            "data": [
                                {
                                    "id": "efba476a-d3ff-44f8-a0db-7f2c811f7247",
                                    "type": "FeatureType"
                                },
                                {
                                    "id": "fa8713a6-875f-48b4-95f2-f9bb7cf47001",
                                    "type": "FeatureType"
                                }
                            ]
                        }
                    }
                }
            }
            """
        When I send the request with POST method
        Then I expect the response status is 403
