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
    # so the rows below carry the other operations whose empty answer IS a
    # response document: an empty catalogue still answers it. GetRecordById is
    # the implemented operation beside those which does not -- its Id is One
    # (Mandatory, Table 67) and an empty catalogue has no record to name with,
    # so it is pinned in its own scenario below.
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
            | DescribeRecord                  | describerecord   | DescribeRecordResponse |

    # GetRecordById answers the refusal of its mandatory Id before anything of
    # the catalogue is read (#909). That operation-specific refusal -- not the
    # "No such operation" of the dispatch fallback -- is what the REQUEST value
    # of the request reached the operation with, so it pins the case-insensitive
    # dispatch of note a the same way the rows above do.
    Scenario: A lower case getrecordbyid request is dispatched to its refusal
        Given I set a queryparam "service" with value "CSW"
        Given I set a queryparam "version" with value "2.0.2"
        Given I set a queryparam "request" with value "getrecordbyid"
        When I send the request with GET method
        Then I expect the response status is 400
        Then I expect that there is a xpath ".//*[local-name()='Exception']/@exceptionCode" with value "MissingParameterValue"
        Then I expect that there is a xpath ".//*[local-name()='Exception']/@locator" with value "Id"

    Scenario: A getrecordbyid request names an identifier the empty catalogue does not have
        Given I set a queryparam "service" with value "CSW"
        Given I set a queryparam "version" with value "2.0.2"
        Given I set a queryparam "request" with value "GetRecordById"
        Given I set a queryparam "Id" with value "de.mrmap.nobody"
        When I send the request with GET method
        Then I expect the response status is 400
        Then I expect that there is a xpath ".//*[local-name()='Exception']/@exceptionCode" with value "InvalidParameterValue"
        Then I expect that there is a xpath ".//*[local-name()='Exception']/@locator" with value "Id"
