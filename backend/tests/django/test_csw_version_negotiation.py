"""VERSION handling of the /csw endpoint (#910).

Two obligations of OGC 07-006r1 are answered here:

* Table 65 makes `version` a mandatory (One) parameter of the KVP GetRecords
  with the fixed value of the CSW version the endpoint profiles. A GetRecords
  without it, or with another value, used to answer a raw HTTP 500: the handler
  asked the request XML, which builds a ``CSWBuilder`` of the requested version,
  and the schema lookup behind that builder raises a ValueError for every version
  but 2.0.2. Both cases are refused requests, so they answer an ExceptionReport.
* 10.8.3 obliges a CSW to implement the Sections, AcceptVersions and
  AcceptFormats request parameters of GetCapabilities. Every variant of them used
  to answer the byte identical full document; they now negotiate the version and
  the media type of the answer and narrow the answer to the sections asked for.

The refusals are the ``ows:ExceptionReport`` of OWS Common at HTTP 400 which
``registry/ows_lib/response/exceptions.py`` builds -- its shape and its schema
are pinned down by ``test_csw_exception_reports.py``, so the tests below name
which parameter each refusal names and what the capabilities document answers.
"""

from csw.views import (CAPABILITIES_FORMATS, CAPABILITIES_SECTIONS,
                       SUPPORTED_CSW_VERSIONS)
from django.test import SimpleTestCase, TestCase
from lxml import etree
from registry.ows_lib.response.exceptions import (
    InvalidParameterValueException, MissingServiceParameterException,
    MissingVersionParameterException, VersionNegotiationFailedException)

OWS_NS = "http://www.opengis.net/ows"

GET_RECORDS = {
    "SERVICE": "CSW",
    "REQUEST": "GetRecords",
    "VERSION": "2.0.2",
}

GET_CAPABILITIES = {
    "SERVICE": "CSW",
    "REQUEST": "GetCapabilities",
}


class AssertsRefusal:
    """The parts of the report which say which parameter was refused and why."""

    def assertRefusal(self, response, exception_class, exception_code,
                      locator, names=()):
        self.assertIsInstance(response, exception_class)
        self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(response["Content-Type"], "application/xml")

        root = etree.fromstring(response.content)
        self.assertEqual(etree.QName(root).localname, "ExceptionReport")

        exceptions = root.findall(f"{{{OWS_NS}}}Exception")
        self.assertEqual(len(exceptions), 1, response.content)
        self.assertEqual(exceptions[0].get("exceptionCode"), exception_code)
        self.assertEqual(exceptions[0].get("locator"), locator)

        # a refusal which does not name the value it refused and the values it
        # does speak leaves the client guessing
        text = exceptions[0].find(f"{{{OWS_NS}}}ExceptionText")
        self.assertTrue(text is not None and text.text, response.content)
        for name in names:
            self.assertIn(name, text.text)


class CswGetRecordsVersionTests(AssertsRefusal, SimpleTestCase):
    """The refusals of dispatch(): no record and no schema is read for them.

    A ``SimpleTestCase`` forbids database access, so these tests answer nothing
    but a refusal -- reaching the metadata records or the schema lookup of the
    builder would raise here instead of answering the 500 of #910.
    """

    def test_version_is_mandatory(self):
        response = self.client.get(
            "/csw", {k: v for k, v in GET_RECORDS.items() if k != "VERSION"})

        self.assertRefusal(
            response, MissingVersionParameterException, "MissingParameter",
            "version", names=SUPPORTED_CSW_VERSIONS)

    def test_a_blank_version_is_no_version(self):
        response = self.client.get("/csw", {**GET_RECORDS, "VERSION": "  "})

        self.assertRefusal(
            response, MissingVersionParameterException, "MissingParameter",
            "version", names=SUPPORTED_CSW_VERSIONS)

    def test_another_version_is_refused_naming_the_parameter(self):
        # the row the audit reproduced: 1.0.0 is the CSW 2.0.0 profile, which
        # this catalogue does not speak
        response = self.client.get(
            "/csw", {**GET_RECORDS, "VERSION": "1.0.0"})

        self.assertRefusal(
            response, InvalidParameterValueException, "InvalidParameterValue",
            "version", names=["1.0.0", *SUPPORTED_CSW_VERSIONS])

    def test_an_unshaped_version_is_refused(self):
        response = self.client.get(
            "/csw", {**GET_RECORDS, "VERSION": "not-a-version"})

        self.assertRefusal(
            response, InvalidParameterValueException, "InvalidParameterValue",
            "version", names=SUPPORTED_CSW_VERSIONS)

    def test_the_parameter_is_read_whatever_its_spelling_is(self):
        # the KVP binding reads parameter names case-insensitively, so the
        # refusal reaches a client which spells the parameter in lower case too
        response = self.client.get("/csw", {
            "SERVICE": "CSW",
            "REQUEST": "GetRecords",
            "version": "9.9.9",
        })

        self.assertRefusal(
            response, InvalidParameterValueException, "InvalidParameterValue",
            "version", names=SUPPORTED_CSW_VERSIONS)

    def test_the_mandatory_parameters_are_refused_first(self):
        # a request which names no service is refused naming the service, even
        # though its version is missing as well: the version refusal follows the
        # refusal of the parameters which identify the request at all
        response = self.client.get("/csw", {"REQUEST": "GetRecords"})

        self.assertRefusal(
            response, MissingServiceParameterException, "MissingParameter",
            "service")

    def test_another_operation_is_answered_without_a_version(self):
        # Table 64 defines no version parameter for GetCapabilities and Table 63
        # no mandatory one for DescribeRecord: this issue refuses the GetRecords
        # parameter of Table 65 and answers the rest as before. DescribeRecord
        # needs no record to answer, so it answers here.
        response = self.client.get("/csw", {
            "SERVICE": "CSW",
            "REQUEST": "DescribeRecord",
        })

        self.assertEqual(response.status_code, 200, response.content)
        root = etree.fromstring(response.content)
        self.assertEqual(
            etree.QName(root).localname, "DescribeRecordResponse")


class CswGetCapabilitiesNegotiationTests(AssertsRefusal, TestCase):
    """The Sections, AcceptVersions and AcceptFormats of GetCapabilities (10.8.3).

    The catalogue of the migrated test database answers the document; no record
    is needed for it.
    """

    def sections_of(self, response):
        """The metadata sections of the answered document, in document order."""
        root = etree.fromstring(response.content)
        self.assertEqual(etree.QName(root).localname, "Capabilities")
        return [etree.QName(element).localname for element in root]

    def assertCapabilities(self, parameters):
        """Answers a GetCapabilities and proves it is the document, not a refusal."""
        response = self.client.get("/csw", {**GET_CAPABILITIES, **parameters})
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response["Content-Type"], "application/xml")
        return response

    def test_the_document_without_the_parameters_carries_every_section(self):
        response = self.client.get("/csw", GET_CAPABILITIES)

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(self.sections_of(response), list(CAPABILITIES_SECTIONS))

    def test_a_requested_section_is_answered_alone(self):
        for section in CAPABILITIES_SECTIONS:
            with self.subTest(section=section):
                response = self.assertCapabilities({"sections": section})

                self.assertEqual(self.sections_of(response), [section])

    def test_the_requested_sections_are_answered_in_document_order(self):
        response = self.assertCapabilities(
            {"sections": "Filter_Capabilities,ServiceIdentification"})

        # the answer is the document with the sections it did not ask for left
        # out, not a document reshaped by the order of the parameter
        self.assertEqual(
            self.sections_of(response),
            ["ServiceIdentification", "Filter_Capabilities"])

    def test_all_asks_for_the_whole_document(self):
        response = self.assertCapabilities({"sections": "All"})

        self.assertEqual(self.sections_of(response), list(CAPABILITIES_SECTIONS))

    def test_an_absent_or_empty_sections_parameter_asks_for_the_whole_document(self):
        for sections in (None, ""):
            with self.subTest(sections=sections):
                parameters = dict(GET_CAPABILITIES)
                if sections is not None:
                    parameters["sections"] = sections
                response = self.client.get("/csw", parameters)

                self.assertEqual(response.status_code, 200, response.content)
                self.assertEqual(
                    self.sections_of(response), list(CAPABILITIES_SECTIONS))

    def test_the_singular_spelling_of_the_parameter_is_honoured_too(self):
        response = self.assertCapabilities({"section": "ServiceProvider"})

        self.assertEqual(self.sections_of(response), ["ServiceProvider"])

    def test_an_unknown_section_is_refused_naming_the_parameter(self):
        response = self.client.get(
            "/csw", {**GET_CAPABILITIES, "sections": "Harvesting_Capabilities"})

        self.assertRefusal(
            response, InvalidParameterValueException, "InvalidParameterValue",
            "sections",
            names=["Harvesting_Capabilities", *CAPABILITIES_SECTIONS])

    def test_a_version_this_catalogue_speaks_is_negotiated(self):
        # the negotiation matrix of 10.8.3: the supported version alone, the
        # supported version first, the supported version last and the parameter
        # without a value all answer the document of the version this catalogue
        # speaks
        for acceptversions in ("2.0.2", "1.0.0,2.0.2", "2.0.2,1.0.0", ""):
            with self.subTest(acceptversions=acceptversions):
                response = self.assertCapabilities(
                    {"acceptversions": acceptversions})

                self.assertEqual(
                    self.sections_of(response), list(CAPABILITIES_SECTIONS))

    def test_no_version_in_common_is_refused_naming_the_supported_ones(self):
        for acceptversions in ("1.0.0", "1.0.0,1.0.1"):
            with self.subTest(acceptversions=acceptversions):
                response = self.client.get(
                    "/csw",
                    {**GET_CAPABILITIES, "acceptversions": acceptversions})

                self.assertRefusal(
                    response, VersionNegotiationFailedException,
                    "VersionNegotiationFailed", "acceptVersions",
                    names=[acceptversions.split(",")[0],
                           *SUPPORTED_CSW_VERSIONS])

    def test_the_version_parameter_of_get_capabilities_is_not_the_negotiation(self):
        # Table 64 gives GetCapabilities no `version` parameter -- negotiation is
        # `acceptVersions` -- so the value a client puts there refuses nothing.
        # Pinned down because it is the row of the audit which is not a refusal.
        response = self.assertCapabilities({"version": "9.9.9"})

        self.assertEqual(
            self.sections_of(response), list(CAPABILITIES_SECTIONS))

    def test_a_media_type_this_catalogue_answers_is_negotiated(self):
        for acceptformats in ("application/xml", "text/html,application/xml",
                              "application/xml,text/html", ""):
            with self.subTest(acceptformats=acceptformats):
                response = self.assertCapabilities(
                    {"acceptformats": acceptformats})

                self.assertEqual(
                    self.sections_of(response), list(CAPABILITIES_SECTIONS))
                self.assertEqual(
                    response["Content-Type"], CAPABILITIES_FORMATS[0])

    def test_no_media_type_in_common_is_refused_naming_the_supported_ones(self):
        response = self.client.get(
            "/csw", {**GET_CAPABILITIES, "acceptformats": "text/html"})

        self.assertRefusal(
            response, InvalidParameterValueException, "InvalidParameterValue",
            "acceptFormats", names=["text/html", *CAPABILITIES_FORMATS])
