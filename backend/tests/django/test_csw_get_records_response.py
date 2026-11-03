"""The response shape of a ``GetRecords`` (#913).

Two response-level conformance obligations of OGC 07-006r1, answered by the
response itself rather than by the records it carries:

* the media type -- 10.3.2.2 answers the response in the advertised
  ``outputFormat``, ``application/xml``, which is also what ``GetCapabilities``
  and ``GetRecordById`` of this endpoint already serve; the response used to
  stand at ``application/xhtml+xml``, which no client may be asked to parse;
* the paging attributes of Table 66 -- a ``resultType=hits`` response answers
  the size of the result set and no record of it: ``numberOfRecordsReturned``
  is 0 and ``nextRecord`` is 0 ("all records have been returned"), so a client
  never pages on a phantom position. A ``results`` response answers both as
  the numbers of the page it ships; those numbers are what a live deployment
  pages by and are pinned here unchanged.

``test_csw_queryables.py`` asks this endpoint one queryable at a time and
counts matches; the paging of a ``results`` response down to the record each
page answers is pinned there. What this module pins is the response around the
records.
"""

import datetime

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, TestCase
from lxml import etree

from registry.models.metadata import (DatasetMetadataRecord, MetadataContact)
from registry.ows_lib.csw.builder import CSWBuilder
from registry.ows_lib.xml.consts import NAMESPACE_LOOKUP

CSW = {'csw': NAMESPACE_LOOKUP['csw_2_0_2']}
GMD = {'gmd': NAMESPACE_LOOKUP['gmd'], 'gco': NAMESPACE_LOOKUP['gco']}

GET_RECORDS = {
    'SERVICE': 'CSW',
    'REQUEST': 'GetRecords',
    'VERSION': '2.0.2',
}

SEARCH_RESULTS = '/csw:GetRecordsResponse/csw:SearchResults'
MATCHED = f'{SEARCH_RESULTS}/@numberOfRecordsMatched'
RETURNED = f'{SEARCH_RESULTS}/@numberOfRecordsReturned'
NEXT_RECORD = f'{SEARCH_RESULTS}/@nextRecord'
FILE_IDENTIFIERS = '//gmd:fileIdentifier/gco:CharacterString/text()'


def gmd_document(identifier: str) -> bytes:
    """The document a metadata record is answered with by a ``GetRecords`` response.

    Same shape as in ``test_csw_queryables.py``: the response embeds the stored
    document of a record as it is, so the identifier names a record in it.
    """
    return (
        '<gmd:MD_Metadata xmlns:gmd="http://www.isotc211.org/2005/gmd"'
        ' xmlns:gco="http://www.isotc211.org/2005/gco">'
        '<gmd:fileIdentifier>'
        f'<gco:CharacterString>{identifier}</gco:CharacterString>'
        '</gmd:fileIdentifier>'
        '</gmd:MD_Metadata>'
    ).encode('utf-8')


class CswHitsResponseTests(TestCase):
    """Table 66: what a response of each ``resultType`` answers around its records."""

    def setUp(self):
        self.contact = MetadataContact.objects.create(name='CSW response contact')
        # five records, so that a hits request with a page smaller than the
        # result set must not leak the page's numbers into the response; the
        # pk of a record is its uuid and the response orders the pages by it,
        # so the expected pages are taken from the sorted pks, not the creation
        # order -- as in test_csw_queryables.py
        self.documents = {
            self.record(f'record{i}').pk: f'record{i}' for i in range(1, 6)}
        self.ordered_names = [self.documents[pk] for pk in sorted(self.documents)]

    def record(self, identifier):
        return DatasetMetadataRecord.objects.create(
            metadata_contact=self.contact,
            dataset_contact=self.contact,
            code_space='de.mrmap.',
            code=identifier,
            file_identifier=f'de.mrmap.{identifier}',
            xml_backup_file=SimpleUploadedFile(
                f'{identifier}.xml', gmd_document(identifier),
                content_type='application/xml'))

    def get_records(self, **query_params):
        response = self.client.get('/csw', {**GET_RECORDS, **query_params})
        self.assertEqual(response.status_code, 200, response.content)
        return response

    def attributes(self, **query_params):
        """The three paging attributes of the SearchResults element, as strings."""
        root = etree.fromstring(self.get_records(**query_params).content)
        return {
            name: root.xpath(path, namespaces=CSW)[0]
            for name, path in (('matched', MATCHED), ('returned', RETURNED),
                               ('next', NEXT_RECORD))
        }

    def test_a_hits_response_answers_the_size_of_the_result_set_and_no_record(self):
        # the live defect of #913: matched 278,117 answered with returned=3
        # and nextRecord=4 while carrying zero records
        self.assertEqual(
            {'matched': '5', 'returned': '0', 'next': '0'},
            self.attributes(resultType='hits', maxRecords='3'))

        root = etree.fromstring(self.get_records(
            resultType='hits', maxRecords='3').content)
        search_results = root.xpath(SEARCH_RESULTS, namespaces=CSW)[0]
        self.assertEqual([], list(search_results),
                         'a hits response carries records')

    def test_a_hits_response_without_any_match_still_answers_the_three_zeros(self):
        response = self.get_records(
            resultType='hits',
            CONSTRAINTLANGUAGE='CQL_TEXT',
            Constraint="identifier = 'de.mrmap.nobody'")
        root = etree.fromstring(response.content)
        self.assertEqual(
            ['0', '0', '0'],
            [root.xpath(path, namespaces=CSW)[0] for path in
             (MATCHED, RETURNED, NEXT_RECORD)])

    def test_a_results_response_answers_the_numbers_of_the_page_it_ships(self):
        """The happy path a live deployment pages by, unchanged: page 1 of 3 of 5."""
        self.assertEqual(
            {'matched': '5', 'returned': '3', 'next': '4'},
            self.attributes(resultType='results', maxRecords='3'))

        identifiers = etree.fromstring(self.get_records(
            resultType='results', maxRecords='3').content).xpath(
                FILE_IDENTIFIERS, namespaces=GMD)
        self.assertEqual(self.ordered_names[:3], identifiers)

    def test_the_last_results_page_answers_no_next_record(self):
        """Table 66 again: 0 in nextRecord means all records have been returned."""
        self.assertEqual(
            {'matched': '5', 'returned': '2', 'next': '0'},
            self.attributes(
                resultType='results', maxRecords='3', startPosition='4'))

        identifiers = etree.fromstring(self.get_records(
            resultType='results', maxRecords='3', startPosition='4').content).xpath(
                FILE_IDENTIFIERS, namespaces=GMD)
        self.assertEqual(self.ordered_names[3:], identifiers)


class CswGetRecordsMediaTypeTests(TestCase):
    """The media type every GetRecords response is served with."""

    def test_every_get_records_response_is_served_as_application_xml(self):
        # 10.3.2.2 answers the response in the outputFormat the capabilities
        # advertise, and it is application/xml there as well as on the other
        # operations of this endpoint; the ExceptionReport of a refusal is
        # pinned by test_csw_exception_reports.py
        for query_params in (
                {'resultType': 'hits'},
                {'resultType': 'results'},
                {'resultType': 'validate'}):
            with self.subTest(**query_params):
                # no records exist, which is fine: the media type is the
                # response's own, empty or not
                response = self.client.get('/csw', {**GET_RECORDS, **query_params})
                self.assertEqual(response.status_code, 200, response.content)
                self.assertEqual(response['Content-Type'], 'application/xml')


class CswBuilderZeroCountsTests(SimpleTestCase):
    """The builder renders an explicit 0, which is what the hits branch hands it."""

    def test_zero_counts_are_attributes_and_not_omitted_values(self):
        # the skeleton builder omits an attribute whose value is None; a hits
        # response must not answer that way -- Table 66 demands the two zeros
        root = CSWBuilder().build_get_records_response(
            total_records=5,
            records_returned=0,
            time_stamp=datetime.datetime(2026, 11, 3),
            next_record=0)

        search_results = root.xpath(SEARCH_RESULTS, namespaces=CSW)[0]
        self.assertEqual('0', search_results.get('numberOfRecordsReturned'))
        self.assertEqual('0', search_results.get('nextRecord'))
        self.assertEqual('5', search_results.get('numberOfRecordsMatched'))
