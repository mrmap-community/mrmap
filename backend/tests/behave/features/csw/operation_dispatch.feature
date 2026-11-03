# New with #907. Everything the /csw endpoint does not implement falls into the
# dispatch fallback; that fallback used to raise a TypeError and answer a raw
# HTTP 500 HTML page. Since #908 it renders the ows:ExceptionReport of OWS Common
# at HTTP 400 (registry/ows_lib/response/exceptions.py); these scenarios pin the
# fallback down for the operations the #907 audit probed live, beside the
# made-up GetCatalogueDigest which get_capabilities.feature already carries.
#
# The outline covers Table 65 note a of OGC 07-006r1: the KVP binding compares
# the value of REQUEST case-insensitively, so request=getrecords is a GetRecords
# request -- it used to reach the fallback and hear "No such operation" at the
# earliest, a raw 500 before #908.
@no_fixtures
Feature: CSW Operation Dispatch Endpoint
    As an API client,
    I want the /csw endpoint to answer every operation request with a document,
    so that I can tell a missing operation from a broken one.

    Background: Setup base url
        Given I use the endpoint http://localhost:8000/csw

    Scenario: An operation of the CSW profile which is not implemented is refused
        Given I set a queryparam "service" with value "CSW"
        Given I set a queryparam "version" with value "2.0.2"
        Given I set a queryparam "request" with value "GetDomain"
        When I send the request with GET method
        Then I expect the response status is 400
        Then I expect that there is a xpath "/*[local-name()='ExceptionReport']/@version" with value "1.2.0"
        Then I expect that there is a xpath ".//*[local-name()='Exception']/@exceptionCode" with value "OperationNotSupported"
        Then I expect that there is a xpath ".//*[local-name()='Exception']/@locator" with value "GetDomain"
        Then I expect that there is a xpath ".//*[local-name()='Exception']/*[local-name()='ExceptionText']/text()" with value "No such operation: GetDomain"

    # GetCapabilities is the one operation whose answer needs a stored service,
    # so the rows below carry the other three implemented operations: an empty
    # catalogue still answers their (empty) response documents.
    Scenario Outline: <operation> is dispatched whatever the spelling of its REQUEST value is
        Given I set a queryparam "service" with value "CSW"
        Given I set a queryparam "version" with value "2.0.2"
        Given I set a queryparam "request" with value "<request>"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that there is a xpath "/*[local-name()='<response>']"

        Examples: One row per operation, one row per the spellings the audit reproduced
            | operation                       | request          | response             |
            | GetRecords (the audit row)      | getrecords       | GetRecordsResponse   |
            | GetRecordById                   | getrecordbyid    | GetRecordByIdResponse |
            | DescribeRecord                  | describerecord   | DescribeRecordResponse |
