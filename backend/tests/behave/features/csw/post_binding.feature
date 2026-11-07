# New with #912. The /csw endpoint advertises the POST binding (OGC 07-006r1,
# 10.3.2), and every POST answered a raw HTTP 500: OGCRequest's POST branch read a
# `service_type` attribute which no request document carries (the XML binding spells
# that parameter `service`), a posted filter died on the AttributeError of the
# `fes_filter`/`cql_filter` reads nothing defined anymore, and malformed XML raised its
# XMLSyntaxError out of the request analysis. A well-formed posted GetRecords is
# answered with its SearchResults and a broken POST with the ows:ExceptionReport
# naming what is broken.
#
# The XML POST steps are the generic vocabulary: the payload docstring, the content
# type step and the POST send step send the document, the xpath steps read the answer.
#
# The fixture answers the same two dataset records as get_records.feature; both
# documents are stored by tests/behave/environment.py and cover the same box over
# Germany (5.87 47.27 to 15.04 55.06).
@fixtures:test_keywords.json @fixtures:test_csw.json @fixtures:test_datasetmetadata.json
Feature: MrMap CatalogueService POST Binding Endpoint
    As an API client,
    I want to send CSW requests as XML over POST,
    so that I can use the binding a catalogue registration client sends.

    Background: Setup base url
        Given I use the endpoint http://localhost:8000/csw
        Given I set the content type of the request to application/xml

    Scenario: Posted GetRecords without a constraint answers the catalogue
        Given I set the request payload to:
        """
        <?xml version="1.0" encoding="UTF-8"?>
        <csw:GetRecords xmlns:csw="http://www.opengis.net/cat/csw/2.0.2"
                        service="CSW" version="2.0.2" resultType="hits" maxRecords="10">
          <csw:Query typeNames="gmd:MD_Metadata">
            <csw:ElementSetName>full</csw:ElementSetName>
          </csw:Query>
        </csw:GetRecords>
        """
        When I send the request with POST method
        Then I expect the response status is 200
        Then I expect that there is a xpath ".//*[local-name()='SearchResults']/@numberOfRecordsMatched" with value "2"

    Scenario: Posted GetRecords applies an ogc:Filter
        Given I set the request payload to:
        """
        <?xml version="1.0" encoding="UTF-8"?>
        <csw:GetRecords xmlns:csw="http://www.opengis.net/cat/csw/2.0.2"
                        xmlns:ogc="http://www.opengis.net/ogc"
                        service="CSW" version="2.0.2" resultType="hits" maxRecords="10">
          <csw:Query typeNames="gmd:MD_Metadata">
            <csw:ElementSetName>full</csw:ElementSetName>
            <csw:Constraint version="1.1.0">
              <ogc:Filter>
                <ogc:PropertyIsLike wildCard="%" singleChar="_" escapeChar="\" matchCase="false">
                  <ogc:PropertyName>title</ogc:PropertyName>
                  <ogc:Literal>%Feuchte%</ogc:Literal>
                </ogc:PropertyIsLike>
              </ogc:Filter>
            </csw:Constraint>
          </csw:Query>
        </csw:GetRecords>
        """
        When I send the request with POST method
        Then I expect the response status is 200
        Then I expect that there is a xpath ".//*[local-name()='SearchResults']/@numberOfRecordsMatched" with value "1"

    Scenario: Posted GetRecords applies a csw:CqlText constraint
        Given I set the request payload to:
        """
        <?xml version="1.0" encoding="UTF-8"?>
        <csw:GetRecords xmlns:csw="http://www.opengis.net/cat/csw/2.0.2"
                        service="CSW" version="2.0.2" resultType="hits" maxRecords="10">
          <csw:Query typeNames="gmd:MD_Metadata">
            <csw:ElementSetName>full</csw:ElementSetName>
            <csw:Constraint version="1.1.0">
              <csw:CqlText>identifier = 'de.dwd.geoserver.fach.RBSN_RR'</csw:CqlText>
            </csw:Constraint>
          </csw:Query>
        </csw:GetRecords>
        """
        When I send the request with POST method
        Then I expect the response status is 200
        Then I expect that there is a xpath ".//*[local-name()='SearchResults']/@numberOfRecordsMatched" with value "1"

    Scenario: Posted GetRecords applies a bounding box filter
        Given I set the request payload to:
        """
        <?xml version="1.0" encoding="UTF-8"?>
        <csw:GetRecords xmlns:csw="http://www.opengis.net/cat/csw/2.0.2"
                        xmlns:ogc="http://www.opengis.net/ogc"
                        xmlns:gml="http://www.opengis.net/gml"
                        service="CSW" version="2.0.2" resultType="hits" maxRecords="10">
          <csw:Query typeNames="gmd:MD_Metadata">
            <csw:ElementSetName>full</csw:ElementSetName>
            <csw:Constraint version="1.1.0">
              <ogc:Filter>
                <ogc:BBOX>
                  <ogc:PropertyName>ows:BoundingBox</ogc:PropertyName>
                  <gml:Envelope srsName="urn:ogc:def:crs:EPSG::4326">
                    <gml:lowerCorner>0.0 40.0</gml:lowerCorner>
                    <gml:upperCorner>20.0 60.0</gml:upperCorner>
                  </gml:Envelope>
                </ogc:BBOX>
              </ogc:Filter>
            </csw:Constraint>
          </csw:Query>
        </csw:GetRecords>
        """
        When I send the request with POST method
        Then I expect the response status is 200
        Then I expect that there is a xpath ".//*[local-name()='SearchResults']/@numberOfRecordsMatched" with value "2"

    # The refusals of the binding: the report names the part of the document
    # which failed (the locator) -- HTTP 500 HTML is nothing a client can read.
    Scenario: Posted GetRecords naming no queryable is refused
        Given I set the request payload to:
        """
        <?xml version="1.0" encoding="UTF-8"?>
        <csw:GetRecords xmlns:csw="http://www.opengis.net/cat/csw/2.0.2"
                        xmlns:ogc="http://www.opengis.net/ogc"
                        service="CSW" version="2.0.2" resultType="hits" maxRecords="10">
          <csw:Query typeNames="gmd:MD_Metadata">
            <csw:ElementSetName>full</csw:ElementSetName>
            <csw:Constraint version="1.1.0">
              <ogc:Filter>
                <ogc:PropertyIsEqualTo>
                  <ogc:PropertyName>unknownfield</ogc:PropertyName>
                  <ogc:Literal>x</ogc:Literal>
                </ogc:PropertyIsEqualTo>
              </ogc:Filter>
            </csw:Constraint>
          </csw:Query>
        </csw:GetRecords>
        """
        When I send the request with POST method
        Then I expect the response status is 400
        Then I expect that there is a xpath ".//*[local-name()='Exception']/@exceptionCode" with value "InvalidQuery"
        Then I expect that there is a xpath ".//*[local-name()='Exception']/@locator" with value "csw:Query"

    Scenario: Posted GetRecords with an unparsable filter is refused
        Given I set the request payload to:
        """
        <?xml version="1.0" encoding="UTF-8"?>
        <csw:GetRecords xmlns:csw="http://www.opengis.net/cat/csw/2.0.2"
                        xmlns:ogc="http://www.opengis.net/ogc"
                        service="CSW" version="2.0.2" resultType="hits" maxRecords="10">
          <csw:Query typeNames="gmd:MD_Metadata">
            <csw:ElementSetName>full</csw:ElementSetName>
            <csw:Constraint version="1.1.0">
              <ogc:Filter>
                <ogc:ThisIsNoComparisonOperator/>
              </ogc:Filter>
            </csw:Constraint>
          </csw:Query>
        </csw:GetRecords>
        """
        When I send the request with POST method
        Then I expect the response status is 400
        Then I expect that there is a xpath ".//*[local-name()='Exception']/@exceptionCode" with value "InvalidParameterValue"
        Then I expect that there is a xpath ".//*[local-name()='Exception']/@locator" with value "csw:Constraint"

    # The paging attributes belong to the request element of either binding;
    # #1149 refuses a value which is no value of their type with the report
    # naming the attribute, where the bare int() of the read answered a raw
    # HTTP 500. The refusals of the same attributes on the KVP binding are in
    # get_records.feature.
    Scenario: Posted GetRecords with a non-numeric maxRecords is refused
        Given I set the request payload to:
        """
        <?xml version="1.0" encoding="UTF-8"?>
        <csw:GetRecords xmlns:csw="http://www.opengis.net/cat/csw/2.0.2"
                        service="CSW" version="2.0.2" resultType="hits" maxRecords="abc">
          <csw:Query typeNames="gmd:MD_Metadata"/>
        </csw:GetRecords>
        """
        When I send the request with POST method
        Then I expect the response status is 400
        Then I expect that there is a xpath ".//*[local-name()='Exception']/@exceptionCode" with value "InvalidParameterValue"
        Then I expect that there is a xpath ".//*[local-name()='Exception']/@locator" with value "maxRecords"

    Scenario: Posted request document which is not well-formed XML is refused
        Given I set the request payload to:
        """
        <?xml version="1.0" encoding="UTF-8"?>
        <csw:GetRecords xmlns:csw="http://www.opengis.net/cat/csw/2.0.2"
                        service="CSW" version="2.0.2" resultType="hits">
          <csw:Query typeNames="gmd:MD_Metadata"><broken>
        """
        When I send the request with POST method
        Then I expect the response status is 400
        Then I expect that there is a xpath "/*[local-name()='ExceptionReport']/@version" with value "1.2.0"
        Then I expect that there is a xpath ".//*[local-name()='Exception']/@exceptionCode" with value "ParsingError"
        Then I expect that there is a xpath ".//*[local-name()='Exception']/@locator" with value "request"

    Scenario: Posted GetCapabilities answers the capabilities document
        Given I set the request payload to:
        """
        <?xml version="1.0" encoding="UTF-8"?>
        <csw:GetCapabilities xmlns:csw="http://www.opengis.net/cat/csw/2.0.2"
                             service="CSW" version="2.0.2"/>
        """
        When I send the request with POST method
        Then I expect the response status is 200
        Then I expect that there is a xpath "/*[local-name()='Capabilities']/@version" with value "2.0.2"
        Then I expect that there is a xpath ".//*[local-name()='ServiceIdentification']/*[local-name()='ServiceType']/text()" with value "CSW"

    Scenario: Posted DescribeRecord answers the record schema
        Given I set the request payload to:
        """
        <?xml version="1.0" encoding="UTF-8"?>
        <csw:DescribeRecord xmlns:csw="http://www.opengis.net/cat/csw/2.0.2"
                            service="CSW" version="2.0.2">
          <csw:TypeName>gmd:MD_Metadata</csw:TypeName>
        </csw:DescribeRecord>
        """
        When I send the request with POST method
        Then I expect the response status is 200
        Then I expect that there is a xpath "/*[local-name()='DescribeRecordResponse']/*[local-name()='SchemaComponent']/@targetNamespace" with value "http://www.isotc211.org/2005/gmd"
