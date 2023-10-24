Feature: CSW Endpoint
    As an API client,
    I want to retreive metadata records,
    so that I can consume them by the mrmap csw endpoint.

    Background: Setup base url
        Given I use the endpoint http://localhost:8000/csw

    Scenario: GetRecords Hits response
        Given I set a queryparam "REQUEST" with value "GetRecords"
        Given I set a queryparam "version" with value "2.0.2"
        Given I set a queryparam "service" with value "CSW"
        Given I set a queryparam "resultType" with value "hits"
        When I send the request with GET method
        Then I expect the response status is 200
