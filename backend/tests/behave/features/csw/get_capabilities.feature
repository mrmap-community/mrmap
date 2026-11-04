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
#
# The scenarios at the end of this feature are new with #910: they answer the
# Sections, AcceptVersions and AcceptFormats parameters of the request, which the
# endpoint ignored before (OGC 07-006r1, 10.8.3 obliges a CSW to implement them).
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

    # OGC 07-006r1, 10.8.3 obliges a CSW to implement the Sections, AcceptVersions
    # and AcceptFormats request parameters of GetCapabilities. All three were
    # ignored: every variant of them answered the byte identical full document
    # (#910). The scenarios below answer what each of them negotiates and name the
    # refusal each of them answers for a value this catalogue does not speak.
    #
    # The vocabulary has no step which asserts the absence of a node, so the counts
    # of the sections are turned into the one string it can read (the concat of the
    # get_records feature says why two arguments are needed).
    Scenario Outline: GetCapabilities answers <case> for the sections parameter <requested>
        Given I set a queryparam "service" with value "CSW"
        Given I set a queryparam "request" with value "GetCapabilities"
        Given I set a queryparam "sections" with value "<requested>"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that there is a xpath "concat(count(/*[local-name()='Capabilities']/*), '')" with value "<sections>"
        Then I expect that there is a xpath "concat(count(/*[local-name()='Capabilities']/*[local-name()='ServiceIdentification']), '')" with value "<identification>"
        Then I expect that there is a xpath "concat(count(/*[local-name()='Capabilities']/*[local-name()='ServiceProvider']), '')" with value "<provider>"
        Then I expect that there is a xpath "concat(count(/*[local-name()='Capabilities']/*[local-name()='OperationsMetadata']), '')" with value "<operations>"
        Then I expect that there is a xpath "concat(count(/*[local-name()='Capabilities']/*[local-name()='Filter_Capabilities']), '')" with value "<filter>"

        Examples: The sections a client can ask for
            | case                        | requested                       | sections | identification | provider | operations | filter |
            | one section alone           | ServiceIdentification           | 1        | 1              | 0        | 0          | 0      |
            | the provider alone          | ServiceProvider                 | 1        | 0              | 1        | 0          | 0      |
            | the operations alone        | OperationsMetadata              | 1        | 0              | 0        | 1          | 0      |
            | the filter capabilities     | Filter_Capabilities             | 1        | 0              | 0        | 0          | 1      |
            | the reserved value for all  | All                             | 4        | 1              | 1        | 1          | 1      |
            | two sections                | Filter_Capabilities,ServiceProvider | 2    | 0              | 1        | 0          | 1      |

    Scenario: GetCapabilities refuses a section it builds no part of the document for
        Given I set a queryparam "service" with value "CSW"
        Given I set a queryparam "request" with value "GetCapabilities"
        Given I set a queryparam "sections" with value "Harvesting_Capabilities"
        When I send the request with GET method
        Then I expect the response status is 400
        Then I expect that there is a xpath ".//*[local-name()='Exception']/@exceptionCode" with value "InvalidParameterValue"
        Then I expect that there is a xpath ".//*[local-name()='Exception']/@locator" with value "sections"
        Then I expect that there is a xpath ".//*[local-name()='Exception']/*[local-name()='ExceptionText']/text()" with value "Unsupported sections: Harvesting_Capabilities. This catalogue answers ServiceIdentification, ServiceProvider, OperationsMetadata, Filter_Capabilities and All."

    Scenario Outline: GetCapabilities negotiates <case> for acceptVersions <requested>
        Given I set a queryparam "service" with value "CSW"
        Given I set a queryparam "request" with value "GetCapabilities"
        Given I set a queryparam "acceptversions" with value "<requested>"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that there is a xpath "/*[local-name()='Capabilities']/@version" with value "2.0.2"
        Then I expect that there is a xpath "concat(count(/*[local-name()='Capabilities']/*), '')" with value "4"

        Examples: The lists which hold a version this catalogue speaks
            | case                  | requested   |
            | its own version       | 2.0.2       |
            | preferred version     | 2.0.2,1.0.0 |
            | version beside others | 1.0.0,2.0.2 |

    Scenario: GetCapabilities refuses an acceptVersions list without a version it speaks
        Given I set a queryparam "service" with value "CSW"
        Given I set a queryparam "request" with value "GetCapabilities"
        Given I set a queryparam "acceptversions" with value "1.0.0"
        When I send the request with GET method
        Then I expect the response status is 400
        Then I expect that there is a xpath ".//*[local-name()='Exception']/@exceptionCode" with value "VersionNegotiationFailed"
        Then I expect that there is a xpath ".//*[local-name()='Exception']/@locator" with value "acceptVersions"
        Then I expect that there is a xpath ".//*[local-name()='Exception']/*[local-name()='ExceptionText']/text()" with value "None of the requested versions is supported: 1.0.0. This catalogue speaks 2.0.2."

    Scenario Outline: GetCapabilities accepts <case> for acceptFormats <requested>
        Given I set a queryparam "service" with value "CSW"
        Given I set a queryparam "request" with value "GetCapabilities"
        Given I set a queryparam "acceptformats" with value "<requested>"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that there is a xpath "/*[local-name()='Capabilities']"

        Examples: The lists which hold the media type of the document
            | case                       | requested                 |
            | its own media type         | application/xml           |
            | preferred media type       | application/xml,text/html |
            | media type beside others   | text/html,application/xml |

    Scenario: GetCapabilities refuses an acceptFormats list without the media type it answers
        Given I set a queryparam "service" with value "CSW"
        Given I set a queryparam "request" with value "GetCapabilities"
        Given I set a queryparam "acceptformats" with value "text/html"
        When I send the request with GET method
        Then I expect the response status is 400
        Then I expect that there is a xpath ".//*[local-name()='Exception']/@exceptionCode" with value "InvalidParameterValue"
        Then I expect that there is a xpath ".//*[local-name()='Exception']/@locator" with value "acceptFormats"
        Then I expect that there is a xpath ".//*[local-name()='Exception']/*[local-name()='ExceptionText']/text()" with value "None of the requested formats is supported: text/html. This catalogue answers application/xml."

    # The one row of the audit which is not a refusal: Table 64 gives a
    # GetCapabilities no `version` parameter at all -- the version it answers is
    # negotiated by acceptVersions -- so the value a client puts there keeps
    # answering the document of the version this catalogue profiles.
    Scenario: GetCapabilities is not refused by a version parameter it does not define
        Given I set a queryparam "service" with value "CSW"
        Given I set a queryparam "request" with value "GetCapabilities"
        Given I set a queryparam "version" with value "9.9.9"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that there is a xpath "/*[local-name()='Capabilities']/@version" with value "2.0.2"
