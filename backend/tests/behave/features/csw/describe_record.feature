# New with #907. DescribeRecord is mandatory for a CSW 2.0.2 catalogue (OGC
# 07-006r1, Table 60) and was not implemented at all: it fell into the fallback for
# unknown operations, which answered a raw HTTP 500 until the ExceptionReport
# machinery of #908 made that fallback render an OperationNotSupported report.
#
# The endpoint answers the one record type it serves: gmd:MD_Metadata, the type
# GetCapabilities advertises as typeNames and whose stored documents every
# GetRecords returns. mrmap keeps no copy of the ISO 19139 schema, so the answer
# is the SchemaComponent of Table 13 which references that schema at its normative
# location (xs:include of gmd.xsd) instead of redeclaring its components -- the
# schema description this catalogue can defensibly answer with.
@no_fixtures
Feature: CSW DescribeRecord Endpoint
    As an API client,
    I want to retreive the schema description of the advertised record type,
    so that I can consume the records of the mrmap csw endpoint schema-aware.

    Background: Setup base url
        Given I use the endpoint http://localhost:8000/csw

    Scenario: DescribeRecord answers the schema of the requested type
        Given I set a queryparam "REQUEST" with value "DescribeRecord"
        Given I set a queryparam "version" with value "2.0.2"
        Given I set a queryparam "service" with value "CSW"
        Given I set a queryparam "TYPENAME" with value "gmd:MD_Metadata"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that there is a xpath "/*[local-name()='DescribeRecordResponse']"
        Then I expect that there is a xpath ".//*[local-name()='SchemaComponent']/@targetNamespace" with value "http://www.isotc211.org/2005/gmd"
        Then I expect that there is a xpath ".//*[local-name()='SchemaComponent']/@schemaLanguage" with value "http://www.w3.org/XML/Schema"
        Then I expect that there is a xpath ".//*[local-name()='SchemaComponent']/*[local-name()='schema']/*[local-name()='include']/@schemaLocation" with value "http://www.isotc211.org/2005/gmd/gmd.xsd"

    # Table 13: a DescribeRecord which names no TypeName asks for the whole
    # information model. It stays out of the scenario above because a table
    # column can not make the TYPENAME step optional.
    Scenario: DescribeRecord answers the schema of the whole information model when no type is named
        Given I set a queryparam "REQUEST" with value "DescribeRecord"
        Given I set a queryparam "version" with value "2.0.2"
        Given I set a queryparam "service" with value "CSW"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that there is a xpath "/*[local-name()='DescribeRecordResponse']"
        Then I expect that there is a xpath ".//*[local-name()='SchemaComponent']/@targetNamespace" with value "http://www.isotc211.org/2005/gmd"
        Then I expect that there is a xpath ".//*[local-name()='SchemaComponent']/@schemaLanguage" with value "http://www.w3.org/XML/Schema"
        Then I expect that there is a xpath ".//*[local-name()='SchemaComponent']/*[local-name()='schema']/*[local-name()='include']/@schemaLocation" with value "http://www.isotc211.org/2005/gmd/gmd.xsd"

    Scenario: DescribeRecord refuses a type this catalogue does not serve
        Given I set a queryparam "REQUEST" with value "DescribeRecord"
        Given I set a queryparam "version" with value "2.0.2"
        Given I set a queryparam "service" with value "CSW"
        Given I set a queryparam "TYPENAME" with value "csw:Record"
        When I send the request with GET method
        Then I expect the response status is 400
        Then I expect that there is a xpath "/*[local-name()='ExceptionReport']/@version" with value "1.2.0"
        Then I expect that there is a xpath ".//*[local-name()='Exception']/@exceptionCode" with value "NotSupported"
        Then I expect that there is a xpath ".//*[local-name()='Exception']/@locator" with value "typeName"
        Then I expect that there is a xpath ".//*[local-name()='Exception']/*[local-name()='ExceptionText']"
