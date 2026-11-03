"""DescribeRecord and the dispatch around it (#907).

DescribeRecord is mandatory for a CSW 2.0.2 catalogue (OGC 07-006r1, Table 60)
and was not implemented: it fell into the fallback for unknown operations, whose
constructor call raised before #908 and answered a raw HTTP 500. The tests drive
the endpoint through the test client and pin down what the audit's probes are
answered with now: the ``DescribeRecordResponse`` for the operation itself, the
OWS Common ``ExceptionReport`` for an operation which stays unimplemented, and
the case-insensitive comparison of the KVP binding's REQUEST value (Table 65
note a).

The validation runs against a reduced copy of the cswDiscovery schema: the full
schema resolves its includes through http schema locations, which no test may
request, while the DescribeRecordResponse and SchemaComponent declarations of
10.2.4 reference nothing outside themselves -- so the copy carries exactly the
constraints this endpoint's answer has to satisfy.
"""

from django.test import SimpleTestCase, TestCase
from lxml import etree
from tests.django.test_csw_exception_reports import OWS_NS, \
    AssertsExceptionReport

CSW_NS = "http://www.opengis.net/cat/csw/2.0.2"
GMD_NS = "http://www.isotc211.org/2005/gmd"
XS_NS = "http://www.w3.org/2001/XMLSchema"
XML_SCHEMA_LANGUAGE = "http://www.w3.org/XML/Schema"
GMD_SCHEMA_LOCATION = "http://www.isotc211.org/2005/gmd/gmd.xsd"

DESCRIBE_RECORD = {
    "SERVICE": "CSW",
    "REQUEST": "DescribeRecord",
    "VERSION": "2.0.2",
}

DESCRIBE_RECORD_RESPONSE_XSD = b"""<?xml version="1.0" encoding="UTF-8"?>
<xs:schema targetNamespace="http://www.opengis.net/cat/csw/2.0.2"
  xmlns:csw="http://www.opengis.net/cat/csw/2.0.2"
  xmlns:xs="http://www.w3.org/2001/XMLSchema" elementFormDefault="qualified">
  <xs:element name="DescribeRecordResponse">
    <xs:complexType>
      <xs:sequence>
        <xs:element name="SchemaComponent" minOccurs="0" maxOccurs="unbounded">
          <xs:complexType mixed="true">
            <xs:sequence>
              <xs:any namespace="##any" processContents="lax"/>
            </xs:sequence>
            <xs:attribute name="targetNamespace" type="xs:anyURI" use="required"/>
            <xs:attribute name="parentSchema" type="xs:anyURI" use="optional"/>
            <xs:attribute name="schemaLanguage" type="xs:anyURI" use="required"/>
          </xs:complexType>
        </xs:element>
      </xs:sequence>
    </xs:complexType>
  </xs:element>
</xs:schema>"""


class CswDescribeRecordTests(AssertsExceptionReport, SimpleTestCase):
    """The DescribeRecord answers of the endpoint; like the refusals of
    dispatch() these are answered before any record is read."""

    def assertDescribesTheGmdSchema(self, response):
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response["Content-Type"], "application/xml")

        root = etree.fromstring(response.content)
        self.assertEqual(etree.QName(root).namespace, CSW_NS)
        self.assertEqual(etree.QName(root).localname, "DescribeRecordResponse")

        components = root.findall(f"{{{CSW_NS}}}SchemaComponent")
        self.assertEqual(len(components), 1, response.content)
        component = components[0]
        self.assertEqual(component.get("targetNamespace"), GMD_NS)
        self.assertEqual(component.get("schemaLanguage"), XML_SCHEMA_LANGUAGE)
        self.assertEqual(component.get("parentSchema"), GMD_SCHEMA_LOCATION)

        # the xs:schema of the component is the Table 13 fragment which
        # references the published ISO 19139 schema instead of redeclaring its
        # components beside them
        schema = component.find(f"{{{XS_NS}}}schema")
        self.assertIsNotNone(schema, response.content)
        self.assertEqual(schema.get("targetNamespace"), GMD_NS)
        include = schema.find(f"{{{XS_NS}}}include")
        self.assertIsNotNone(include, response.content)
        self.assertEqual(include.get("schemaLocation"), GMD_SCHEMA_LOCATION)

        xmlschema = etree.XMLSchema(
            etree.fromstring(DESCRIBE_RECORD_RESPONSE_XSD))
        self.assertTrue(xmlschema.validate(root),
                        str(xmlschema.error_log.last_error))

    def test_answers_the_advertised_record_schema_without_a_type_name(self):
        # an absent TYPENAME asks for the whole information model (10.2.4.1),
        # which is the one type this catalogue advertises
        self.assertDescribesTheGmdSchema(
            self.client.get("/csw", DESCRIBE_RECORD))

    def test_answers_a_requested_advertised_type_name(self):
        response = self.client.get(
            "/csw", {**DESCRIBE_RECORD, "TYPENAME": "gmd:MD_Metadata"})
        self.assertDescribesTheGmdSchema(response)

    def test_the_operation_value_is_compared_case_insensitively(self):
        # Table 65 note a; the audit reproduced request=getrecords, this is the
        # DescribeRecord spelling of it -- dispatch reaches the operation
        # instead of the fallback
        response = self.client.get(
            "/csw", {**DESCRIBE_RECORD, "REQUEST": "describerecord"})
        self.assertDescribesTheGmdSchema(response)

    def test_refuses_a_type_this_catalogue_does_not_serve(self):
        response = self.client.get(
            "/csw", {**DESCRIBE_RECORD, "TYPENAME": "csw:Record"})
        self.assertExceptionReport(response, "NotSupported", "typeName")

    def test_refuses_a_type_list_naming_a_type_this_catalogue_does_not_serve(self):
        response = self.client.get(
            "/csw",
            {**DESCRIBE_RECORD, "TYPENAME": "gmd:MD_Metadata,csw:Record"})
        self.assertExceptionReport(response, "NotSupported", "typeName")

    def test_an_unknown_operation_answers_an_exception_report_and_not_a_500(self):
        # the audit's probe GET /csw?service=CSW&request=GetDomain: the fallback
        # raised a TypeError -> raw 500 until #908 gave the report its identity
        # out of the request itself
        response = self.client.get(
            "/csw", {**DESCRIBE_RECORD, "REQUEST": "GetDomain"})

        self.assertExceptionReport(
            response, "OperationNotSupported", "GetDomain")
        text = etree.fromstring(response.content).find(
            f"{{{OWS_NS}}}Exception/{{{OWS_NS}}}ExceptionText")
        self.assertEqual(text.text, "No such operation: GetDomain")


class CswCaseInsensitiveDispatchTests(TestCase):
    """Table 65 note a on the operations which read the database: an empty
    catalogue still answers their response document, which is what tells a
    dispatched operation from a refused one."""

    def test_a_lower_case_get_records_request_is_dispatched(self):
        response = self.client.get("/csw", {
            "SERVICE": "CSW", "REQUEST": "getrecords", "VERSION": "2.0.2"})

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(
            etree.QName(etree.fromstring(response.content)).localname,
            "GetRecordsResponse")

    def test_a_lower_case_get_record_by_id_request_is_dispatched(self):
        response = self.client.get("/csw", {
            "SERVICE": "CSW", "REQUEST": "getrecordbyid", "VERSION": "2.0.2"})

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(
            etree.QName(etree.fromstring(response.content)).localname,
            "GetRecordByIdResponse")
