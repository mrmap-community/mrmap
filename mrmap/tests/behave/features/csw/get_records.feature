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

    @huhu
    Scenario: GetRecords results response
        Given I set a queryparam "REQUEST" with value "GetRecords"
        Given I set a queryparam "version" with value "2.0.2"
        Given I set a queryparam "service" with value "CSW"
        Given I set a queryparam "resultType" with value "results"
        Given I set a queryparam "TYPENAMES" with value "csw:Record"
        Given I set a queryparam "CONSTRAINTLANGUAGE" with value "CQL_TEXT"
        Given I set a queryparam "Constraint" with value "ResourceIdentifier LIKE '%de.dwd.geoserver.fach.RBSN_FF'"
        When I send the request with GET method
        Then I expect the response status is 200
