"""Exception reports of the /csw endpoint (#908).

OGC 07-006r1, 10.3.7 obliges a CSW to answer a refused request with the
ExceptionReport of OWS Common (OGC 05-008, clause 8): an
``<ows:ExceptionReport version="1.2.0">`` whose ``<ows:Exception>`` names
``exceptionCode`` and ``locator`` and carries an ``<ows:ExceptionText>``. The
tests drive the error paths of the endpoint through the test client and pin
down what carries a refusal -- the HTTP status and the three parts of the
report -- and validate the report against the exception schema.

The validation runs against a reduced copy of that schema: the full
``owsExceptionReport.xsd`` pulls its includes through http schema locations,
which no test may request, while the ExceptionReport and Exception
declarations it defines reference nothing outside themselves -- so the copy
carries exactly the constraints a report of this endpoint has to satisfy.
"""

from django.test import SimpleTestCase, TestCase
from lxml import etree
from registry.ows_lib.response.exceptions import LayerNotDefined
from registry.ows_lib.response.exceptions import \
    RuntimeError as OgcRuntimeError

OWS_NS = "http://www.opengis.net/ows"

EXCEPTION_REPORT_XSD = b"""<?xml version="1.0" encoding="UTF-8"?>
<xs:schema targetNamespace="http://www.opengis.net/ows"
  xmlns:ows="http://www.opengis.net/ows"
  xmlns:xs="http://www.w3.org/2001/XMLSchema" elementFormDefault="qualified">
  <xs:element name="ExceptionReport">
    <xs:complexType>
      <xs:sequence>
        <xs:element ref="ows:Exception" maxOccurs="unbounded"/>
      </xs:sequence>
      <xs:attribute name="version" type="xs:string" use="required"/>
      <xs:attribute name="language" type="xs:language" use="optional"/>
    </xs:complexType>
  </xs:element>
  <xs:element name="Exception" type="ows:ExceptionType"/>
  <xs:complexType name="ExceptionType">
    <xs:sequence>
      <xs:element name="ExceptionText" type="xs:string" minOccurs="0" maxOccurs="unbounded"/>
    </xs:sequence>
    <xs:attribute name="exceptionCode" type="xs:string" use="required"/>
    <xs:attribute name="locator" type="xs:string" use="optional"/>
  </xs:complexType>
</xs:schema>"""

GET_RECORDS = {
    "SERVICE": "CSW",
    "REQUEST": "GetRecords",
    "VERSION": "2.0.2",
}


class AssertsExceptionReport:
    """The parts of an OWS Common ExceptionReport which carry a refusal."""

    def assertExceptionReport(self, response, exception_code, locator=None):
        self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(response["Content-Type"], "application/xml")

        root = etree.fromstring(response.content)
        self.assertEqual(etree.QName(root).namespace, OWS_NS)
        self.assertEqual(etree.QName(root).localname, "ExceptionReport")
        self.assertEqual(root.get("version"), "1.2.0")

        exceptions = root.findall(f"{{{OWS_NS}}}Exception")
        self.assertEqual(len(exceptions), 1, response.content)
        self.assertEqual(exceptions[0].get("exceptionCode"), exception_code)
        if locator is not None:
            self.assertEqual(exceptions[0].get("locator"), locator)

        # the text tells the client what it did wrong; an exception which knows
        # it is never answered without one
        texts = exceptions[0].findall(f"{{{OWS_NS}}}ExceptionText")
        self.assertTrue(len(texts) > 0 and texts[0].text, response.content)

        xmlschema = etree.XMLSchema(etree.fromstring(EXCEPTION_REPORT_XSD))
        self.assertTrue(xmlschema.validate(root),
                        str(xmlschema.error_log.last_error))


class CswParameterRefusalTests(AssertsExceptionReport, SimpleTestCase):
    """The refusals of dispatch(): they answer before any record is read."""

    def test_missing_request_parameter(self):
        response = self.client.get("/csw", {"SERVICE": "CSW", "VERSION": "2.0.2"})
        self.assertExceptionReport(response, "MissingParameter", "request")

    def test_missing_service_parameter(self):
        response = self.client.get(
            "/csw", {"REQUEST": "GetCapabilities", "VERSION": "2.0.2"})
        self.assertExceptionReport(response, "MissingParameter", "service")

    def test_unsupported_output_schema(self):
        response = self.client.get("/csw", {
            **GET_RECORDS,
            "outputSchema": "http://purl.org/dc/elements/1.1/",
        })
        self.assertExceptionReport(response, "NotSupported", "outputSchema")

    def test_unsupported_type_names(self):
        response = self.client.get(
            "/csw", {**GET_RECORDS, "typeNames": "csw:Record"})
        self.assertExceptionReport(response, "NotSupported", "typeNames")

    def test_unknown_operation_names_the_operation(self):
        response = self.client.get(
            "/csw", {**GET_RECORDS, "REQUEST": "GetCatalogueDigest"})

        self.assertExceptionReport(
            response, "OperationNotSupported", "GetCatalogueDigest")
        text = etree.fromstring(response.content).find(
            f"{{{OWS_NS}}}Exception/{{{OWS_NS}}}ExceptionText")
        self.assertEqual(text.text, "No such operation: GetCatalogueDigest")


class CswConstraintRefusalTests(AssertsExceptionReport, TestCase):
    """The refusals inside GetRecords; the database is asked after them."""

    def test_constraint_without_language(self):
        response = self.client.get(
            "/csw", {**GET_RECORDS, "Constraint": "AnyText = 'niederschlag'"})
        self.assertExceptionReport(
            response, "MissingParameter", "CONSTRAINTLANGUAGE")

    def test_malformed_cql_constraint(self):
        response = self.client.get("/csw", {
            **GET_RECORDS,
            "CONSTRAINTLANGUAGE": "CQL_TEXT",
            "Constraint": "&&& not a cql expression &&&",
        })
        # the report locates the failure at the parameter whose value it is
        # (#912; the audit's probe title === bad syntax)
        self.assertExceptionReport(response, "InvalidParameterValue", "Constraint")

    def test_unsupported_constraint_language(self):
        # the audit's probe constraintlanguage=banana
        response = self.client.get("/csw", {
            **GET_RECORDS,
            "CONSTRAINTLANGUAGE": "banana",
            "Constraint": "identifier='x'",
        })
        self.assertExceptionReport(
            response, "InvalidParameterValue", "CONSTRAINTLANGUAGE")

    def test_malformed_filter_constraint(self):
        response = self.client.get("/csw", {
            **GET_RECORDS,
            "CONSTRAINTLANGUAGE": "FILTER",
            "Constraint": "<Filter><broken>",
        })
        self.assertExceptionReport(response, "InvalidParameterValue", "Constraint")

    def test_filter_constraint_of_an_unsupported_namespace(self):
        # pygeofilter picks its parser from the namespace of the Filter
        # element and refuses any other with a ValueError -- that is a value
        # the client chose, not a server error
        response = self.client.get("/csw", {
            **GET_RECORDS,
            "CONSTRAINTLANGUAGE": "FILTER",
            "Constraint": "<Filter xmlns='http://example.com/nope'/>",
        })
        self.assertExceptionReport(response, "InvalidParameterValue", "Constraint")

    def test_constraint_field_which_is_no_queryable(self):
        response = self.client.get("/csw", {
            **GET_RECORDS,
            "resultType": "results",
            "CONSTRAINTLANGUAGE": "CQL_TEXT",
            "Constraint": "unknownfield LIKE 'niederschlag'",
        })

        self.assertExceptionReport(response, "InvalidQuery", "Constraint")
        text = etree.fromstring(response.content).find(
            f"{{{OWS_NS}}}Exception/{{{OWS_NS}}}ExceptionText")
        self.assertIn("unknownfield", text.text)


class OwsExceptionReportFallbackTests(AssertsExceptionReport, SimpleTestCase):
    """The report profiles of the shared exception classes."""

    def test_service_without_report_profile_falls_back_to_the_common_report(self):
        # a request which names a service nobody serves: the refused request is
        # still answered with a report, not with the error of building one
        response = OgcRuntimeError(service_type="gsv", service_version="9.9.9")
        self.assertExceptionReport(response, "RuntimeError")

    def test_wms_profile_keeps_the_service_exception_report(self):
        # the security proxy answers its registered WMS profiles with the
        # ServiceExceptionReport skeleton of the service version -- the report
        # shape and the status code of the proxy are not the CSW obligation of
        # this module and tests_wms_proxy.py pins the rendered document
        response = LayerNotDefined(service_type="wms", service_version="1.3.0")

        self.assertEqual(response.status_code, 200)
        root = etree.fromstring(response.content)
        self.assertEqual(etree.QName(root).localname, "ServiceExceptionReport")
        self.assertEqual(
            root.find(".//{*}ServiceException").get("code"), "LayerNotDefined")
