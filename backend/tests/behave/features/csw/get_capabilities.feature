# Un-skipped with #908. Both scenarios of this feature assert the exception report of a
# refused request, and the endpoint answers one now: the ows:ExceptionReport of OWS Common
# (OGC 05-008, clause 8) at HTTP 400, built by registry/ows_lib/response/exceptions.py.
# Before, a request without REQUEST or SERVICE answered a 500 -- MissingRequestParameter-
# Exception and MissingServiceParameterException were built without the identity the
# report is answered from -- and the report itself never rendered: the skeleton of
# ("csw", "Exception", "2.0.2") carries no ServiceException element, so the client got an
# empty <ows:ServiceExceptionReport/> at HTTP 200. The XML comparison the old scenarios
# carried pinned exactly that never-rendered document; the assertions below name what
# carries the refusal: the report's version and the exceptionCode, locator and text of
# its Exception.
@fixtures:test_keywords.json @fixtures:test_csw.json @fixtures:test_datasetmetadata.json
Feature: CSW Endpoint
    As an API client,
    I want to retreive the capabilities document,
    so that I know all features of the csw service.

    The mandatory GetCapabilities operation allows CSW clients to retrieve service metadata from a server.

    Background: Setup base url
        Given I use the endpoint http://localhost:8000/csw

    Scenario: Missing SERVICE query param
        Given I set a queryparam "REQUEST" with value "GetCapabilities"
        Given I set a queryparam "version" with value "2.0.2"
        When I send the request with GET method
        Then I expect the response status is 400
        Then I expect that there is a xpath "/*[local-name()='ExceptionReport']/@version" with value "1.2.0"
        Then I expect that there is a xpath ".//*[local-name()='Exception']/@exceptionCode" with value "MissingParameter"
        Then I expect that there is a xpath ".//*[local-name()='Exception']/@locator" with value "service"
        Then I expect that there is a xpath ".//*[local-name()='Exception']/*[local-name()='ExceptionText']"

    Scenario: Missing REQUEST query param
        Given I set a queryparam "version" with value "2.0.2"
        Given I set a queryparam "service" with value "CSW"
        When I send the request with GET method
        Then I expect the response status is 400
        Then I expect that there is a xpath ".//*[local-name()='Exception']/@exceptionCode" with value "MissingParameter"
        Then I expect that there is a xpath ".//*[local-name()='Exception']/@locator" with value "request"
        Then I expect that there is a xpath ".//*[local-name()='Exception']/*[local-name()='ExceptionText']"

    Scenario: An unknown operation is refused naming the operation
        Given I set a queryparam "service" with value "CSW"
        Given I set a queryparam "version" with value "2.0.2"
        Given I set a queryparam "request" with value "GetCatalogueDigest"
        When I send the request with GET method
        Then I expect the response status is 400
        Then I expect that there is a xpath ".//*[local-name()='Exception']/@exceptionCode" with value "OperationNotSupported"
        Then I expect that there is a xpath ".//*[local-name()='Exception']/@locator" with value "GetCatalogueDigest"
        Then I expect that there is a xpath ".//*[local-name()='Exception']/*[local-name()='ExceptionText']/text()" with value "No such operation: GetCatalogueDigest"
