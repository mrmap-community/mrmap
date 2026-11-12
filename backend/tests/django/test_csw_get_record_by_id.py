"""The ``GetRecordById`` operation: its documents and its mandatory ``Id`` (#909).

OGC 07-006r1, 10.9 names this the operation which "retrieves the default
representation of catalogue records using their identifier" -- and the audit of
2026-11-03 found it retrieving nothing at all: every known identifier, the
comma separated list and the repeated ``Id`` parameters included, answered a
200 ``GetRecordByIdResponse`` of 378 bytes and zero children. The builder
passed the parsed documents through ``children_attributes``, a description
``build_element`` reads off the schema skeleton to CREATE children -- a
pre-built lxml element put through it is silently dropped, so the response
never carried a record (#908 of the issue: the unit repro is pinned below).
The second defect is the same operation's parameter discipline: Table 67 makes
``Id`` One (Mandatory), and a request which names no identifier -- or only
identifiers no record has -- was answered 200-empty instead of refused.

Which identifier-list shape answers which documents, and the two refusals, are
pinned here at the endpoint. Adjacent pins elsewhere: the lost backup file of
a FOUND record is the ``DocumentUnavailable`` refusal of #912
(``test_csw_missing_backup.py``), the POST binding reaches the operation in
``test_csw_post_binding.py``, and the application table's membership of the
lookup ships its own document in ``test_searchable_application_records.py``.
"""

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import RequestFactory, SimpleTestCase, TestCase
from lxml import etree

from registry.models.metadata import (ApplicationMetadataRecord,
                                      DatasetMetadataRecord,
                                      MetadataContact,
                                      ServiceMetadataRecord)
from registry.ows_lib.csw.builder import CSWBuilder
from registry.ows_lib.request.ogc_request import OGCRequest
from registry.ows_lib.xml.consts import NAMESPACE_LOOKUP
from tests.django.test_csw_exception_reports import AssertsExceptionReport

CSW = {'csw': NAMESPACE_LOOKUP['csw_2_0_2']}
GMD = {'gmd': NAMESPACE_LOOKUP['gmd'], 'gco': NAMESPACE_LOOKUP['gco']}

GET_RECORD_BY_ID = {
    'SERVICE': 'CSW',
    'REQUEST': 'GetRecordById',
    'VERSION': '2.0.2',
}

FILE_IDENTIFIERS = '//gmd:fileIdentifier/gco:CharacterString/text()'


def gmd_document(identifier: str) -> bytes:
    """The stored document of a record; same shape as in
    ``test_csw_get_records_response.py``, plus a ``dateStamp`` which proves the
    response ships the document as stored rather than a pruned view."""
    return (
        '<gmd:MD_Metadata xmlns:gmd="http://www.isotc211.org/2005/gmd"'
        ' xmlns:gco="http://www.isotc211.org/2005/gco">'
        '<gmd:fileIdentifier>'
        f'<gco:CharacterString>{identifier}</gco:CharacterString>'
        '</gmd:fileIdentifier>'
        f'<gmd:dateStamp><gco:DateTime>2026-11-03T00:00:00</gco:DateTime></gmd:dateStamp>'
        '</gmd:MD_Metadata>'
    ).encode('utf-8')


class CswGetRecordByIdBuilderTests(SimpleTestCase):
    """The builder of the response element, unit level."""

    def test_the_issue_repro_ships_the_record_as_a_child(self):
        # the in-container repro of the issue verbatim: len(xml) was 0, the
        # pre-built document went into children_attributes and disappeared
        rec = etree.fromstring(
            b'<gmd:MD_Metadata xmlns:gmd="http://www.isotc211.org/2005/gmd">'
            b'<gmd:id>x</gmd:id></gmd:MD_Metadata>')

        xml = CSWBuilder().build_get_records_by_id_response(gmd_records=[rec])

        self.assertEqual(1, len(xml), 'the builder dropped the record it was given')
        self.assertEqual('GetRecordByIdResponse', etree.QName(xml).localname)
        self.assertEqual('MD_Metadata', etree.QName(xml[0]).localname)

    def test_a_response_without_records_stays_the_empty_element(self):
        # the empty GetRecordByIdResponse is no longer an answer the endpoint
        # reaches (a request with no match is refused), but an empty list is
        # still no reason to fabricate a child
        xml = CSWBuilder().build_get_records_by_id_response(gmd_records=[])
        self.assertEqual([], list(xml))

        xml = CSWBuilder().build_get_records_by_id_response(gmd_records=None)
        self.assertEqual([], list(xml))

    def test_the_kvp_request_synthesis_carries_the_identifiers(self):
        # build_get_record_by_id handed "Id" to add_foreign_child as the
        # namespace and no name at all -- a TypeError waiting for the first
        # reader of the synthesized request element
        root = CSWBuilder().build_get_record_by_id(
            ids=['de.mrmap.rain', 'de.mrmap.humidity'])

        ids = root.xpath('csw:Id/text()', namespaces=CSW)
        self.assertEqual(['de.mrmap.rain,de.mrmap.humidity'], ids)

    def test_a_kvp_get_record_by_id_request_element_is_synthesized(self):
        # the property path of the same synthesis: reading xml_request of a KVP
        # GetRecordById used to raise out of the builder
        django_request = RequestFactory().get(
            '/csw', {**GET_RECORD_BY_ID, 'Id': 'de.mrmap.rain'})
        ogc_request = OGCRequest.from_django_request(django_request)

        ids = ogc_request.xml_request.xpath('csw:Id/text()', namespaces=CSW)
        self.assertEqual(['de.mrmap.rain'], ids)


class CswGetRecordByIdResponseTests(AssertsExceptionReport, TestCase):
    """The endpoint answer for the identifier-list shapes of the issue."""

    def setUp(self):
        self.contact = MetadataContact.objects.create(name='by-id contact')
        self.rain = self.dataset('de.mrmap.rain')
        self.humidity = self.dataset('de.mrmap.humidity')
        # one record per remaining source: the ids of the catalogue live in
        # three tables and the lookup asks all of them (#988)
        self.service = ServiceMetadataRecord.objects.create(
            metadata_contact=self.contact,
            code_space='de.mrmap.',
            code='wms',
            file_identifier='de.mrmap.wms',
            title='CSW by-id service record',
            xml_backup_file=SimpleUploadedFile(
                'wms.xml', gmd_document('de.mrmap.wms'),
                content_type='application/xml'))
        self.application = ApplicationMetadataRecord.objects.create(
            metadata_contact=self.contact,
            application_contact=self.contact,
            code_space='de.mrmap.',
            code='anwendung',
            file_identifier='de.mrmap.anwendung',
            title='CSW by-id application record',
            xml_backup_file=SimpleUploadedFile(
                'anwendung.xml', gmd_document('de.mrmap.anwendung'),
                content_type='application/xml'))

    def dataset(self, identifier):
        return DatasetMetadataRecord.objects.create(
            metadata_contact=self.contact,
            dataset_contact=self.contact,
            code_space='de.mrmap.',
            code=identifier.split('.')[-1],
            file_identifier=identifier,
            title=identifier,
            xml_backup_file=SimpleUploadedFile(
                f'{identifier}.xml', gmd_document(identifier),
                content_type='application/xml'))

    def get_by_id(self, **query_params):
        return self.client.get('/csw', {**GET_RECORD_BY_ID, **query_params})

    def identifiers(self, response) -> list:
        """The fileIdentifiers of the documents the response carries, and the
        shape around them: every document a direct child of the response."""
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response['Content-Type'], 'application/xml')
        root = etree.fromstring(response.content)
        self.assertEqual('GetRecordByIdResponse', etree.QName(root).localname)
        self.assertEqual('2.0.2', root.get('version'))
        for child in root:
            self.assertEqual(
                NAMESPACE_LOOKUP['gmd'], etree.QName(child).namespace,
                f'{etree.QName(child)} is no gmd document child')
        return root.xpath(FILE_IDENTIFIERS, namespaces=GMD)

    def test_a_single_id_answers_the_stored_document(self):
        # the demo-box repro of the issue: 200 and 378 bytes of nothing for a
        # known identifier; since the fix the stored document stands in it
        self.assertEqual(
            ['de.mrmap.rain'],
            self.identifiers(self.get_by_id(Id='de.mrmap.rain')))

    def test_comma_separated_ids_answer_all_their_documents(self):
        self.assertEqual(
            ['de.mrmap.humidity', 'de.mrmap.rain'],
            sorted(self.identifiers(self.get_by_id(
                Id='de.mrmap.rain,de.mrmap.humidity'))))

    def test_repeated_id_parameters_answer_all_their_documents(self):
        # the third shape of the issue's audit: the list handed over as one
        # parameter per member; the request analysis keeps them as the comma
        # separated list of Table 67
        self.assertEqual(
            ['de.mrmap.humidity', 'de.mrmap.rain'],
            sorted(self.identifiers(self.get_by_id(
                **{'Id': ['de.mrmap.rain', 'de.mrmap.humidity']}))))

    def test_ids_across_the_three_record_kinds_answer_all_documents(self):
        self.assertEqual(
            ['de.mrmap.anwendung', 'de.mrmap.rain', 'de.mrmap.wms'],
            sorted(self.identifiers(self.get_by_id(
                Id='de.mrmap.rain,de.mrmap.wms,de.mrmap.anwendung'))))

    def test_the_full_document_answers_and_an_element_set_name_changes_nothing(self):
        # the capabilities advertise "full" as the only ElementSetName of this
        # operation; the stored document IS the full view, so the request
        # parameter asks what the operation answers anyway and prunes nothing
        # (documented in the #909 PR; the pruned views of #911 are the
        # GetRecords mechanism, read off its own request element)
        response = self.get_by_id(Id='de.mrmap.rain', ElementSetName='brief')

        self.assertEqual(['de.mrmap.rain'], self.identifiers(response))
        root = etree.fromstring(response.content)
        self.assertEqual(
            ['2026-11-03T00:00:00'],
            root.xpath('//gmd:dateStamp/gco:DateTime/text()', namespaces=GMD))

    # -- the mandatory Id of Table 67 ---------------------------------------

    def test_a_request_without_an_id_is_refused_naming_the_parameter(self):
        # 200-empty asked for nothing; Table 67 makes Id One (Mandatory), so
        # the refusal names the parameter the request left out
        self.assertExceptionReport(
            self.get_by_id(), 'MissingParameterValue', 'Id')

    def test_an_empty_id_is_the_missing_id(self):
        self.assertExceptionReport(
            self.get_by_id(Id=''), 'MissingParameterValue', 'Id')

    def test_an_unknown_id_is_refused_naming_the_identifier(self):
        # the NoSuchRecord-style refusal of the issue's root cause: the code
        # this endpoint's OWS Common profile answers a value it has none of
        # with, carrying the value in the text so the client can correct it
        response = self.get_by_id(Id='cf92dc62-13bb-4424-ad7c-3ec40beefad7')

        self.assertExceptionReport(response, 'InvalidParameterValue', 'Id')
        text = etree.fromstring(response.content).xpath(
            "//*[local-name()='Exception']/*[local-name()='ExceptionText']")[0]
        self.assertIn('cf92dc62-13bb-4424-ad7c-3ec40beefad7', text.text,
                      response.content)

    def test_an_id_list_with_nothing_known_is_refused_naming_all_values(self):
        response = self.get_by_id(Id='de.mrmap.nope,de.mrmap.never')

        self.assertExceptionReport(response, 'InvalidParameterValue', 'Id')
        text = etree.fromstring(response.content).xpath(
            "//*[local-name()='Exception']/*[local-name()='ExceptionText']")[0]
        for identifier in ('de.mrmap.nope', 'de.mrmap.never'):
            self.assertIn(identifier, text.text, response.content)

    def test_an_id_list_answers_the_records_it_found(self):
        # "Returns a representation of the matching entries" -- a request which
        # names at least one known identifier is a present operation and is
        # answered with the entries it matched
        self.assertEqual(
            ['de.mrmap.rain'],
            self.identifiers(self.get_by_id(
                Id='de.mrmap.rain,de.mrmap.nobody')))
