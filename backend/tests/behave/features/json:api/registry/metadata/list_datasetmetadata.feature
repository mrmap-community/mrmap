@fixtures:test_keywords.json @fixtures:test_datasetmetadata.json
Feature: DatasetMetadataRecord List Endpoint
    As an API client,
    I want to search dataset metadata records,
    so that I can search for.

    Background: Setup base url
        Given I use the endpoint http://localhost:8000/api/registry/dataset-metadata

    Scenario: Can retrieve list as anonymous user
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "meta.pagination.count" with value "2"

    Scenario: Can retrieve list as authenticated user
        Given I am logged in as User1 with password User1
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "meta.pagination.count" with value "2"

    Scenario Outline: Can <action>
        Given I set a queryparam "<param>" with value "<value>"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "meta.pagination.count" with value "<count>"

        Examples:
            | action             | param                                | value                           | count |
            | search             | filter[search]                       | niederschlag                    | 1     |
            | filter by keywords | filter[keywords__keyword__icontains] | niederschlag                    | 1     |
            | filter by title    | filter[title__icontains]             | Relative Feuchte                | 1     |
            | filter by abstract | filter[abstract__icontains]          | Messwerte der relativen Feuchte | 1     |
