Feature: HarvestingJob Add Endpoint
    As an API client,
    I want to add new harvesting job,
    so that I collect metadata records from registered catalouge services.

    Background: Setup baseurl, content-type and payload
        Given I use the endpoint http://localhost:8000/api/v1/registry/harvesting/harvesting-jobs/
        Given I set the content type of the request to application/vnd.api+json

    Scenario: Can add as authenticated user
        Given I am logged in as User1 with password User1
        Given I set the request payload to:
            """
            {
                "data": {
                    "type": "HarvestingJob",
                    "relationships": {
                        "service": {
                            "data": {
                                "id": "9cc4889d-0cd4-4c3b-8975-58de6d30db41",
                                "type": "CatalougeService"
                            }
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
                    "type": "HarvestingJob",
                    "relationships": {
                        "service": {
                            "data": {
                                "id": "9cc4889d-0cd4-4c3b-8975-58de6d30db41",
                                "type": "CatalougeService"
                            }
                        }
                    }
                }
            }
            """
        When I send the request with POST method
        Then I expect the response status is 401

    Scenario: Can't add another if there is one running job
        Given I am logged in as User1 with password User1
        Given I set the request payload to:
            """
            {
                "data": {
                    "type": "HarvestingJob",
                    "relationships": {
                        "service": {
                            "data": {
                                "id": "3df586c6-b89b-4ce5-980a-12dc3ca23df2",
                                "type": "CatalougeService"
                            }
                        }
                    }
                }
            }
            """
        When I send the request with POST method
        Then I expect the response status is 400
