Feature: MrMap CatalogueService Endpoint
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
        #Given I set a queryparam "TYPENAMES" with value "csw:Record"
        #Given I set a queryparam "CONSTRAINTLANGUAGE" with value "CQL_TEXT"
        #Given I set a queryparam "Constraint" with value "ResourceIdentifier LIKE '%de.dwd.geoserver.fach.RBSN_RR'"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that there is a xpath ".//*[local-name()='SearchResults']/@numberOfRecordsMatched" with value "1"

    @huhu
    Scenario: GetRecordById results response
        Given I set a queryparam "REQUEST" with value "GetRecords"
        Given I set a queryparam "version" with value "2.0.2"
        Given I set a queryparam "service" with value "CSW"
        Given I set a queryparam "Id" with value "d8b50d33-2ad7-4a41-bd0d-2d518ea10fd4"
        When I send the request with GET method
        Then I expect the response status is 200