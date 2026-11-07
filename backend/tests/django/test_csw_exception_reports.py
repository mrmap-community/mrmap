"""Exception reports of the /csw endpoint (#908, completed by #866).

OGC 07-006r1, 10.3.7 obliges a CSW to answer a refused request with the
ExceptionReport of OWS Common (OGC 05-008, clause 8): an
``<ows:ExceptionReport version="1.2.0">`` whose ``<ows:Exception>`` names
``exceptionCode`` and ``locator`` and carries an ``<ows:ExceptionText>``. The
tests drive the error paths of the endpoint through the test client and pin
down what carries a refusal -- the HTTP status and the three parts of the
report -- and validate the report against the exception schema.

Two sweeps belong to #866, the defect of the 500 and the empty document:
every exception class has to build a report out of the refused request alone
(no positional identity it could be called without), and every exception
report ``XSD_LOOKUP`` registers a skeleton for has to answer a FILLED report
-- never the childless root of a skeleton which declares no element the
builder asked for.

The validation runs against a reduced copy of that schema: the full
``owsExceptionReport.xsd`` pulls its includes through http schema locations,
which no test may request, while the ExceptionReport and Exception
declarations it defines reference nothing outside themselves -- so the copy
carries exactly the constraints a report of this endpoint has to satisfy.
"""

from django.test import SimpleTestCase, TestCase
from lxml import etree
from registry.ows_lib.response import exceptions as ows_exceptions
from registry.ows_lib.response.exceptions import (
    LayerNotDefined, OGCServiceException)
from registry.ows_lib.response.exceptions import \
    RuntimeError as OgcRuntimeError
from registry.ows_lib.xml.consts import XSD_LOOKUP

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


class CswPagingRefusalTests(AssertsExceptionReport, TestCase):
    """The paging attributes of a GetRecords (#1149).

    Table 65 hands ``startPosition`` and ``maxRecords`` as attributes of the
    request element: a position of a result set is a positiveInteger (the
    first position is 1), the size of a page a nonNegativeInteger. A value
    which is neither names no page and is refused with the report naming the
    attribute -- the bare ``int()`` these reads used raised its ValueError out
    of the handler, which answered the request with HTTP 500 and an HTML error
    page. Both bounds belong to the same refusal: a negative page offset would
    reach the record sources as a negative slice, a position beyond the value
    space of xsd:integer as a LIMIT the database can not carry.

    The refusal answers before any record of the result set is read; the
    handler runs the operation inside a transaction, so the class is asked
    with a database.
    """

    def get_records(self, **params):
        return self.client.get("/csw", {**GET_RECORDS, **params})

    def test_non_numeric_max_records_names_the_attribute(self):
        # the probe of the issue, on the KVP binding: maxrecords=abc
        response = self.get_records(resultType="results", maxRecords="abc")

        self.assertExceptionReport(
            response, "InvalidParameterValue", "maxRecords")
        # the text names the refused value so the client can correct it
        text = etree.fromstring(response.content).find(
            f"{{{OWS_NS}}}Exception/{{{OWS_NS}}}ExceptionText")
        self.assertIn("'abc'", text.text)

    def test_non_numeric_start_position_names_the_attribute(self):
        response = self.get_records(resultType="results",
                                    startPosition="1,5")

        self.assertExceptionReport(
            response, "InvalidParameterValue", "startPosition")

    def test_negative_max_records_names_the_attribute(self):
        response = self.get_records(resultType="results", maxRecords="-1")

        self.assertExceptionReport(
            response, "InvalidParameterValue", "maxRecords")

    def test_start_position_below_the_first_position_names_the_attribute(self):
        # Table 65 counts positions from 1; position 0 names no record of the
        # set and its offset would reach the record sources as a negative slice
        response = self.get_records(resultType="results", startPosition="0")

        self.assertExceptionReport(
            response, "InvalidParameterValue", "startPosition")

    def test_start_position_beyond_the_value_space_names_the_attribute(self):
        # xsd:integer bounds its value space at 10^18; a position beyond it is
        # no page and would reach the sources as a LIMIT the database can not
        # carry
        response = self.get_records(
            resultType="results", startPosition="1" + "0" * 18)

        self.assertExceptionReport(
            response, "InvalidParameterValue", "startPosition")


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

    def test_wfs_profile_is_answered_by_the_common_report_not_the_empty_skeleton(self):
        # ("wfs", "Exception", "2.0.0") registers the OWS ExceptionReport
        # schema, which declares no ServiceExceptionReport; asking it for that
        # WMS spelling answered the childless
        # <ows:ServiceExceptionReport xmlns:ows="http://www.opengis.net/ows/2.0"/>
        # at HTTP 200 until #866 routed ExceptionReport-shaped skeletons to the
        # common report -- the same empty-document defect the CSW key of the
        # issue had, on the profile the skeleton path actually reaches
        response = LayerNotDefined(service_type="wfs", service_version="2.0.0")
        self.assertExceptionReport(response, "LayerNotDefined", "LAYERS")


class ExceptionSkeletonShapeTests(SimpleTestCase):
    """No registered exception report skeleton may answer empty (#866)."""

    def test_every_registered_exception_key_answers_a_filled_report(self):
        for key in sorted(k for k in XSD_LOOKUP if k[1] == "Exception"):
            service_type, _, service_version = key
            with self.subTest(key=key):
                response = OGCServiceException(
                    service_type=service_type,
                    service_version=service_version,
                    message="what the client did wrong",
                    locator="the parameter")
                root = etree.fromstring(response.content)

                # either report shape names the exception, its code and the
                # refused parameter -- an empty root names nothing
                exceptions = root.findall(".//{*}Exception") \
                    + root.findall(".//{*}ServiceException")
                self.assertEqual(len(exceptions), 1, response.content)
                code = exceptions[0].get("exceptionCode") \
                    or exceptions[0].get("code")
                self.assertEqual(code, "NoApplicableCode")
                self.assertEqual(exceptions[0].get("locator"),
                                 "the parameter")
                # the OWS shape carries the text in an ExceptionText child, the
                # WMS skeleton as the text of the ServiceException itself
                text = next(
                    (t.text for t in
                     exceptions[0].findall(".//{*}ExceptionText")),
                    exceptions[0].text)
                self.assertEqual((text or "").strip(),
                                 "what the client did wrong")


class _StubbedOgcRequest:
    """The attributes OGCServiceException reads out of the refused request."""

    service_type = "CSW"
    service_version = "2.0.2"
    operation = "GetRecords"
    ogc_query_params = {"REQUEST": "GetRecords"}


class ExceptionArityTests(SimpleTestCase):
    """Every exception builds its report out of the refused request alone.

    The three refusals of ``csw/views.py`` which used to answer a raw 500 were
    raised with nothing but the request while the exception demanded
    ``service_type`` and ``service_version`` as positional arguments
    (#866); the #908 machinery reads that identity out of the request, and this
    sweep keeps every class of both exception modules constructible the way the
    endpoint calls it -- a class which demands the identity again raises
    TypeError out of dispatch and answers 500, which is exactly the defect.
    """

    @staticmethod
    def _refusal_classes():
        from csw import exceptions as csw_exceptions
        classes = []
        for module in (ows_exceptions, csw_exceptions):
            classes.extend(
                klass for name, klass in vars(module).items()
                if isinstance(klass, type)
                and issubclass(klass, OGCServiceException)
                and klass is not OGCServiceException
                and klass.__module__ == module.__name__)
        return classes

    def test_every_refusal_class_answers_a_report_from_the_request_alone(self):
        classes = self._refusal_classes()
        # the classes the issue names must be in the sweep, not silently absent
        self.assertTrue(classes)
        for klass in classes:
            with self.subTest(klass=klass.__name__):
                exception = klass(ogc_request=_StubbedOgcRequest())
                root = etree.fromstring(exception.content)
                self.assertEqual(
                    etree.QName(root).localname, "ExceptionReport")
                children = root.findall(f"{{{OWS_NS}}}Exception")
                self.assertEqual(len(children), 1, exception.content)
                self.assertEqual(
                    children[0].get("exceptionCode"), klass.code)
                if klass.locator:
                    self.assertEqual(children[0].get("locator"),
                                     klass.locator)
