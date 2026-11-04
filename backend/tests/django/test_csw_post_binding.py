"""The POST XML binding of the /csw endpoint (#912).

OGC 07-006r1, 10.3.2 leaves the POST binding optional -- but this endpoint
advertises it, and every POST answered a raw HTTP 500: the POST branch of
``OGCRequest.__init__`` read a ``service_type`` attribute which no request
document carries (the XML binding spells that parameter ``service``, Table 65),
so every posted request lost the service identity its dispatch and its reports
are answered from, a posted filter died on the AttributeError of the
``fes_filter``/``cql_filter`` reads nothing had defined since the request class
became the ``requests`` based one, and malformed XML raised its XMLSyntaxError
straight out of the request analysis.

These tests drive the binding through the test client and pin down both sides:
a well-formed posted GetRecords/GetCapabilities/DescribeRecord/GetRecordById is
answered as the KVP binding answers it -- the response document, the constraint
of the request applied -- and a broken POST is refused with the
``ows:ExceptionReport`` naming what is broken, never with HTTP 500 HTML.

The GetRecordById response content -- which is what #909 tracks (the builder
silently dropped the matched records) -- is deliberately not asserted here;
what this module pins is that the POST binding reaches the operation and reads
the ``csw:Id`` elements of the request out of the XML.
"""

from django.contrib.gis.geos import GEOSGeometry
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from lxml import etree

from registry.models.metadata import (DatasetMetadataRecord, MetadataContact)
from tests.django.test_csw_exception_reports import AssertsExceptionReport

CSW = {'csw': 'http://www.opengis.net/cat/csw/2.0.2'}
GMD = {'gmd': 'http://www.isotc211.org/2005/gmd',
       'gco': 'http://www.isotc211.org/2005/gco'}
OWS_NS = "http://www.opengis.net/ows"

XML_DECLARATION = '<?xml version="1.0" encoding="UTF-8"?>'
CSW_NAMESPACES = (
    'xmlns:csw="http://www.opengis.net/cat/csw/2.0.2"'
    ' xmlns:ogc="http://www.opengis.net/ogc"'
    ' xmlns:fes="http://www.opengis.net/fes/2.0"'
    ' xmlns:gml="http://www.opengis.net/gml"'
)

FILE_IDENTIFIERS = '//gmd:fileIdentifier/gco:CharacterString/text()'


def gmd_document(identifier: str) -> bytes:
    """The document a metadata record is answered with; same shape as in
    ``test_csw_get_records_response.py``."""
    return (
        '<gmd:MD_Metadata xmlns:gmd="http://www.isotc211.org/2005/gmd"'
        ' xmlns:gco="http://www.isotc211.org/2005/gco">'
        '<gmd:fileIdentifier>'
        f'<gco:CharacterString>{identifier}</gco:CharacterString>'
        '</gmd:fileIdentifier>'
        '</gmd:MD_Metadata>'
    ).encode('utf-8')


def get_records(constraint: str = "", **attributes) -> str:
    """A posted GetRecords; the keyword arguments become attributes of the
    request element and `constraint` the csw:Query's constraint."""
    attributes.setdefault("resultType", "results")
    attribute_string = " ".join(
        f'{name}="{value}"' for name, value in attributes.items())
    return f"""{XML_DECLARATION}
<csw:GetRecords {CSW_NAMESPACES} service="CSW" version="2.0.2"
    {attribute_string}>
  <csw:Query typeNames="gmd:MD_Metadata">
    <csw:ElementSetName>full</csw:ElementSetName>
    {constraint}
  </csw:Query>
</csw:GetRecords>"""


CQL_CONSTRAINT = """
    <csw:Constraint version="1.1.0">
      <csw:CqlText>identifier = 'de.mrmap.humidity'</csw:CqlText>
    </csw:Constraint>"""

OGC_FILTER_CONSTRAINT = """
    <csw:Constraint version="1.1.0">
      <ogc:Filter>
        <ogc:PropertyIsLike wildCard="%" singleChar="_" escapeChar="\\" matchCase="false">
          <ogc:PropertyName>title</ogc:PropertyName>
          <ogc:Literal>%Humidity%</ogc:Literal>
        </ogc:PropertyIsLike>
      </ogc:Filter>
    </csw:Constraint>"""

BBOX_CONSTRAINT = """
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
    </csw:Constraint>"""


class CswPostTests(AssertsExceptionReport, TestCase):
    """The binding itself: which document a posted request is answered with."""

    def setUp(self):
        self.contact = MetadataContact.objects.create(name='CSW POST contact')
        # every record answers the same box over Germany, so the BBOX probe
        # below asks the constraint machinery and not the geometry column
        geometry = GEOSGeometry(
            'SRID=4326;MULTIPOLYGON(((5 46, 15 46, 15 56, 5 56, 5 46)))')
        self.records = {}
        for identifier, title in (
                ('de.mrmap.rain', 'Rain Gauge Stations'),
                ('de.mrmap.humidity', 'Humidity Gauge Stations'),
                ('de.mrmap.wind', 'Wind Gauge Stations')):
            self.records[identifier] = DatasetMetadataRecord.objects.create(
                metadata_contact=self.contact,
                dataset_contact=self.contact,
                code_space='de.mrmap.',
                code=identifier.split('.')[-1],
                file_identifier=identifier,
                title=title,
                bounding_geometry=geometry,
                xml_backup_file=SimpleUploadedFile(
                    f'{identifier}.xml', gmd_document(identifier),
                    content_type='application/xml'))

    def post(self, xml: str):
        return self.client.post(
            "/csw", data=xml, content_type="application/xml")

    def matched(self, response) -> list:
        """The numberOfRecordsMatched the response answers, and nothing else
        is read out of a response this way."""
        self.assertEqual(response.status_code, 200, response.content)
        return etree.fromstring(response.content).xpath(
            "/csw:GetRecordsResponse/csw:SearchResults/@numberOfRecordsMatched",
            namespaces=CSW)

    # -- the operations of the minimal profile (Table 60), posted ------------

    def test_a_posted_get_records_without_constraint_answers_the_records(self):
        response = self.post(get_records(maxRecords="10"))

        self.assertEqual(response["Content-Type"], "application/xml")
        self.assertEqual(['3'], self.matched(response))
        identifiers = etree.fromstring(response.content).xpath(
            FILE_IDENTIFIERS, namespaces=GMD)
        self.assertEqual(
            sorted(self.records), sorted(identifiers))

    def test_a_posted_get_records_applies_an_ogc_filter(self):
        response = self.post(
            get_records(constraint=OGC_FILTER_CONSTRAINT, maxRecords="10"))

        self.assertEqual(['1'], self.matched(response))
        self.assertEqual(
            ['de.mrmap.humidity'],
            etree.fromstring(response.content).xpath(
                FILE_IDENTIFIERS, namespaces=GMD))

    def test_a_posted_get_records_applies_a_cql_text_constraint(self):
        response = self.post(
            get_records(constraint=CQL_CONSTRAINT, maxRecords="10"))

        self.assertEqual(['1'], self.matched(response))
        self.assertEqual(
            ['de.mrmap.humidity'],
            etree.fromstring(response.content).xpath(
                FILE_IDENTIFIERS, namespaces=GMD))

    def test_a_posted_get_records_applies_a_bbox_filter(self):
        response = self.post(
            get_records(constraint=BBOX_CONSTRAINT, maxRecords="10"))

        self.assertEqual(['3'], self.matched(response))

    def test_a_posted_get_capabilities_answers_the_capabilities_document(self):
        response = self.post(f"""{XML_DECLARATION}
<csw:GetCapabilities {CSW_NAMESPACES} service="CSW" version="2.0.2"/>""")

        self.assertEqual(response.status_code, 200, response.content)
        root = etree.fromstring(response.content)
        self.assertEqual(
            etree.QName(root).localname, "Capabilities")
        self.assertEqual(
            root.get("version"), "2.0.2", response.content)

    def test_a_posted_describe_record_answers_the_record_schema(self):
        # the POST branch of csw/views.CswServiceView.requested_type_names
        # which #907 wired but no request ever reached: every POST died in
        # OGCRequest.__init__ before the operation was dispatched (#912)
        response = self.post(f"""{XML_DECLARATION}
<csw:DescribeRecord {CSW_NAMESPACES} service="CSW" version="2.0.2">
  <csw:TypeName>gmd:MD_Metadata</csw:TypeName>
</csw:DescribeRecord>""")

        self.assertEqual(response.status_code, 200, response.content)
        root = etree.fromstring(response.content)
        self.assertEqual(
            etree.QName(root).localname, "DescribeRecordResponse")
        components = root.findall("{%s}SchemaComponent" % CSW['csw'])
        self.assertEqual(len(components), 1, response.content)
        self.assertEqual(
            components[0].get("targetNamespace"),
            "http://www.isotc211.org/2005/gmd")

    def test_a_posted_get_record_by_id_reaches_the_operation(self):
        # the response content -- which records the response ships -- is
        # #909's tracked defect; what the binding has to answer is that the
        # posted csw:Id elements are read out of the XML and the operation
        # is dispatched with them
        response = self.post(f"""{XML_DECLARATION}
<csw:GetRecordById {CSW_NAMESPACES} service="CSW" version="2.0.2">
  <csw:Id>de.mrmap.humidity</csw:Id>
</csw:GetRecordById>""")

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(
            etree.QName(etree.fromstring(response.content)).localname,
            "GetRecordByIdResponse")

    # -- broken POSTs: reports, never HTTP 500 HTML ---------------------------

    def test_malformed_posted_xml_is_refused_with_a_parsing_error(self):
        response = self.post(f"""{XML_DECLARATION}
<csw:GetRecords {CSW_NAMESPACES} service="CSW" version="2.0.2">
  <csw:Query typeNames="gmd:MD_Metadata"><broken>""")

        self.assertExceptionReport(response, "ParsingError", "request")

    def test_a_posted_filter_naming_no_queryable_is_refused(self):
        response = self.post(get_records(constraint="""
    <csw:Constraint version="1.1.0">
      <ogc:Filter>
        <ogc:PropertyIsEqualTo>
          <ogc:PropertyName>unknownfield</ogc:PropertyName>
          <ogc:Literal>x</ogc:Literal>
        </ogc:PropertyIsEqualTo>
      </ogc:Filter>
    </csw:Constraint>""", maxRecords="10"))

        self.assertExceptionReport(response, "InvalidQuery", "csw:Query")

    def test_a_posted_constraint_which_cannot_be_parsed_is_refused(self):
        response = self.post(get_records(constraint="""
    <csw:Constraint version="1.1.0">
      <ogc:Filter>
        <ogc:ThisIsNoComparisonOperator/>
      </ogc:Filter>
    </csw:Constraint>""", maxRecords="10"))

        self.assertExceptionReport(
            response, "InvalidParameterValue", "csw:Constraint")

    def test_a_posted_cql_text_which_cannot_be_parsed_is_refused(self):
        # the ampersands are the CQL garbage itself, fully XML-escaped -- the
        # document stays well-formed so the CQL parser, not the XML parser, is
        # the one refusing the constraint
        response = self.post(get_records(constraint="""
    <csw:Constraint version="1.1.0">
      <csw:CqlText>&amp;&amp;&amp; not a cql expression &amp;&amp;&amp;</csw:CqlText>
    </csw:Constraint>""", maxRecords="10"))

        self.assertExceptionReport(
            response, "InvalidParameterValue", "csw:Constraint")

    def test_a_post_without_the_service_attribute_names_the_service(self):
        # the XML binding requires the service attribute (Table 65); reading
        # the never-existing service_type attribute answered every posted
        # request as this refusal while the real attribute went unread (#912)
        response = self.client.post(
            "/csw",
            data=f"""{XML_DECLARATION}
<csw:GetRecords {CSW_NAMESPACES} version="2.0.2" resultType="results">
  <csw:Query typeNames="gmd:MD_Metadata"/>
</csw:GetRecords>""",
            content_type="application/xml")

        self.assertExceptionReport(response, "MissingParameter", "service")

    def test_an_unknown_posted_operation_names_the_operation(self):
        response = self.post(f"""{XML_DECLARATION}
<csw:GetDomain {CSW_NAMESPACES} service="CSW" version="2.0.2"/>""")

        self.assertExceptionReport(
            response, "OperationNotSupported", "GetDomain")
