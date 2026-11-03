@fixtures:test_keywords.json @fixtures:test_datasetmetadata.json @fixtures:test_csw.json
Feature: HarvestingJob Add Endpoint
    As an API client,
    I want to add new harvesting job,
    so that I collect metadata records from registered catalogue services.

    Background: Setup baseurl, content-type and payload
        Given I use the endpoint http://localhost:8000/api/registry/harvesting/harvesting-jobs
        Given I set the content type of the request to application/vnd.api+json
        Given I set the request payload to:
            """
            {
                "data": {
                    "type": "HarvestingJob",
                    "relationships": {
                        "service": {
                            "data": {
                                "id": "9cc4889d-0cd4-4c3b-8975-58de6d30db41",
                                "type": "CatalogueService"
                            }
                        }
                    }
                }
            }
            """

    Scenario: Can add as authenticated user
        Given I am logged in as User1 with password User1
        When I send the request with POST method
        Then I expect the response status is 201
        And I expect that response json has an attribute "data.attributes.phaseLabel" with value "pending"

    Scenario: Can't add as anonymous user
        Given I am an anonymous user
        When I send the request with POST method
        Then I expect the response status is 403
        And I expect that response json has an attribute "errors.[0].code" with value "not_authenticated"

    Scenario Outline: The internal MrMap catalogue cannot be harvested or scheduled
        Given User1 has the model permission "registry.add_periodicharvestingjob"
        Given I am logged in as User1 with password User1
        Given I use the endpoint http://localhost:8000/api/registry/harvesting/<endpoint>
        Given I set the request payload to:
            """
            {
                "data": {
                    "type": "<resource>",
                    "attributes": <attributes>,
                    "relationships": {
                        "service": {
                            "data": {
                                "id": "650d436a-5837-4cc3-9cb5-6a0a5488ff09",
                                "type": "CatalogueService"
                            }
                        }
                    }
                }
            }
            """
        When I send the request with POST method
        Then I expect the response status is 400
        And I expect that response json has an attribute "errors.[0].source.pointer" with value "/data/relationships/service"

        Examples:
            | endpoint                 | resource              | attributes                         |
            | harvesting-jobs          | HarvestingJob         | {}                                 |
            | periodic-harvesting-jobs | PeriodicHarvestingJob | {"scheduling": "0 2 * * *"}         |

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
                                "type": "CatalogueService"
                            }
                        }
                    }
                }
            }
            """
        When I send the request with POST method
        Then I expect the response status is 400
