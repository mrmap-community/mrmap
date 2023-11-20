@huhu
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

    Scenario: GetRecords results response without filter
        Given I set a queryparam "REQUEST" with value "GetRecords"
        Given I set a queryparam "version" with value "2.0.2"
        Given I set a queryparam "service" with value "CSW"
        Given I set a queryparam "resultType" with value "results"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that there is a xpath ".//*[local-name()='SearchResults']/@numberOfRecordsMatched" with value "2"

    Scenario: GetRecords results response with cql filter
        Given I set a queryparam "REQUEST" with value "GetRecords"
        Given I set a queryparam "version" with value "2.0.2"
        Given I set a queryparam "service" with value "CSW"
        Given I set a queryparam "resultType" with value "results"
        Given I set a queryparam "CONSTRAINTLANGUAGE" with value "CQL_TEXT"
        Given I set a queryparam "Constraint" with value "ResourceIdentifier LIKE '%de.dwd.geoserver.fach.RBSN_RR'"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that there is a xpath ".//*[local-name()='SearchResults']/@numberOfRecordsMatched" with value "1"

    Scenario: GetRecords results response with wrong filter field
        Given I set a queryparam "REQUEST" with value "GetRecords"
        Given I set a queryparam "version" with value "2.0.2"
        Given I set a queryparam "service" with value "CSW"
        Given I set a queryparam "resultType" with value "results"
        Given I set a queryparam "CONSTRAINTLANGUAGE" with value "CQL_TEXT"
        Given I set a queryparam "Constraint" with value "unknownfield LIKE '%de.dwd.geoserver.fach.RBSN_RR'"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that there is a xpath ".//*[local-name()='ServiceException']/@code" with value "InvalidQuery"
        Then I expect that there is a xpath ".//*[local-name()='ServiceException']/@locator" with value "Constraint"

    Scenario: GetRecords results response with unsupported typeNames
        Given I set a queryparam "REQUEST" with value "GetRecords"
        Given I set a queryparam "version" with value "2.0.2"
        Given I set a queryparam "service" with value "CSW"
        Given I set a queryparam "resultType" with value "results"
        Given I set a queryparam "typeNames" with value "csw:record"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that there is a xpath ".//*[local-name()='ServiceException']/@code" with value "NotSupported"
        Then I expect that there is a xpath ".//*[local-name()='ServiceException']/@locator" with value "typeNames"

    Scenario: GetRecords results response with unsupported outputSchema
        Given I set a queryparam "REQUEST" with value "GetRecords"
        Given I set a queryparam "version" with value "2.0.2"
        Given I set a queryparam "service" with value "CSW"
        Given I set a queryparam "resultType" with value "results"
        Given I set a queryparam "outputSchema" with value "http://www.opengis.net/cat/csw/2.0.2"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that there is a xpath ".//*[local-name()='ServiceException']/@code" with value "NotSupported"
        Then I expect that there is a xpath ".//*[local-name()='ServiceException']/@locator" with value "outputSchema"



    Scenario: GetRecordById results response
        Given I set a queryparam "REQUEST" with value "GetRecords"
        Given I set a queryparam "version" with value "2.0.2"
        Given I set a queryparam "service" with value "CSW"
        Given I set a queryparam "Id" with value "d8b50d33-2ad7-4a41-bd0d-2d518ea10fd4"
        When I send the request with GET method
        Then I expect the response status is 200