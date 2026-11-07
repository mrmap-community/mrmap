"""Paging of a ``GetRecords`` over the merged record sources (#1151).

The endpoint answers one result set paged over three record tables. The
response-level shape of a page -- the three attributes of ``SearchResults`` --
is pinned by ``test_csw_get_records_response.py``, the merged order a page
answers by ``test_csw_elementset_sortby.py`` and ``test_csw_queryables.py``
asks the queryables one at a time. What this module pins is the live defect of
#1151: on the demo deployment a page at ``startPosition=340000`` took half a
minute because the paging was done in python, which read every record in front
of the page out of every source first. So here:

* a page of any depth answers exactly the records it is the page of, cut
  through the merged sources -- the merge and its order must survive being
  pushed into the database;
* the offset of a deep page is skipped by the database (the page query
  carries ``OFFSET``, is one query over all three sources, and the request
  issues the same number of queries at every depth);
* a page past the end is refused work itself: the ``numberOfRecordsMatched``
  already counted says the page is empty before any record is read;
* a record the filter matches through two keywords is still one record of the
  page -- the deduplication the merged query must keep in the union.
"""

from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from lxml import etree

from registry.models.metadata import (ApplicationMetadataRecord,
                                      DatasetMetadataRecord, Keyword,
                                      MetadataContact, ServiceMetadataRecord)
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

#: The three tables the merged page query reads.
RECORD_TABLES = (
    'registry_datasetmetadatarecord',
    'registry_servicemetadatarecord',
    'registry_applicationmetadatarecord',
)


def gmd_document(identifier: str) -> bytes:
    """The stored document of a record; its identifier names it in a page."""
    return (
        '<gmd:MD_Metadata xmlns:gmd="http://www.isotc211.org/2005/gmd"'
        ' xmlns:gco="http://www.isotc211.org/2005/gco">'
        '<gmd:fileIdentifier>'
        f'<gco:CharacterString>{identifier}</gco:CharacterString>'
        '</gmd:fileIdentifier>'
        '</gmd:MD_Metadata>'
    ).encode('utf-8')


class CswGetRecordsPagingTests(TestCase):
    """What a page of the merged set costs and what it answers."""

    @classmethod
    def setUpTestData(cls):
        cls.contact = MetadataContact.objects.create(name='CSW paging contact')
        # eight records across all three tables; the titles are ASCII so that
        # the LOWER order of the database and the plain text order of the
        # expected lists below are one and the same order
        # created rows: (pk, source rank, file_identifier, title) per record
        cls.created = []
        cls.ds_alpha = cls.record(
            DatasetMetadataRecord, 'ds-alpha', 0, title='Alpha field')
        cls.ds_beta = cls.record(
            DatasetMetadataRecord, 'ds-beta', 0, title='apricot jam',
            keywords=['Wasser', 'Wasserversorgung'])
        cls.ds_gamma = cls.record(
            DatasetMetadataRecord, 'ds-gamma', 0, title='Zebra lake',
            keywords=['Wasser'])
        cls.svc_delta = cls.record(
            ServiceMetadataRecord, 'svc-delta', 1, title='Delta bridge')
        cls.svc_epsilon = cls.record(
            ServiceMetadataRecord, 'svc-epsilon', 1, title='Blossom way')
        cls.app_zeta = cls.record(
            ApplicationMetadataRecord, 'app-zeta', 2, title='Zeta yard',
            keywords=['Wasser'])
        cls.app_eta = cls.record(
            ApplicationMetadataRecord, 'app-eta', 2, title='Cherry court')
        cls.app_theta = cls.record(
            ApplicationMetadataRecord, 'app-theta', 2, title='Dew plateau')

        # the order the endpoint answers a page in: primary key, and the
        # source's place in the chain for records which share a pk across
        # tables (the tie breaker csw/elementsets.merged_page orders by)
        cls.expected = [row[2] for row in sorted(cls.created)]
        # the requested title order: LOWER of the text orders the merged set
        # among the distinct titles of the fixture; the descending request
        # answers that order reversed
        cls.expected_sorted = [
            row[2] for row in sorted(
                cls.created, key=lambda row: (row[3].lower(), row[0], row[1]))]

    @classmethod
    def record(cls, model, name, rank, title, keywords=()):
        identifier = f'de.mrmap.{name}'
        fields = dict(
            metadata_contact=cls.contact,
            title=title,
            code_space='de.mrmap.',
            code=name,
            file_identifier=identifier,
            xml_backup_file=SimpleUploadedFile(
                f'{name}.xml', gmd_document(identifier),
                content_type='application/xml'))
        if model is DatasetMetadataRecord:
            fields['dataset_contact'] = cls.contact
        elif model is ApplicationMetadataRecord:
            fields['application_contact'] = cls.contact
        record = model.objects.create(**fields)
        for keyword in keywords:
            record.keywords.add(
                Keyword.objects.get_or_create(keyword=keyword)[0])
        cls.created.append((record.pk, rank, identifier, title))
        return record

    def page(self, *, max_records='3', start_position=None, constraint=None,
             sortby=None):
        """One ``resultType=results`` request answered as a document."""
        params = {**GET_RECORDS, 'resultType': 'results',
                  'maxRecords': max_records}
        if start_position is not None:
            params['startPosition'] = start_position
        if sortby is not None:
            params['sortby'] = sortby
        if constraint is not None:
            params.update({
                'CONSTRAINTLANGUAGE': 'CQL_TEXT',
                'Constraint': constraint,
            })
        response = self.client.get('/csw', params)
        self.assertEqual(response.status_code, 200, response.content)
        return etree.fromstring(response.content)

    def identifiers(self, root):
        return list(root.xpath(FILE_IDENTIFIERS, namespaces=GMD))

    def attributes(self, root):
        return {
            name: root.xpath(path, namespaces=CSW)[0]
            for name, path in (('matched', MATCHED), ('returned', RETURNED),
                               ('next', NEXT_RECORD))
        }

    def record_table_queries(self, captured):
        """The queries of one request which read one of the record tables."""
        return [
            query['sql'] for query in captured
            if any(table in query['sql'] for table in RECORD_TABLES)]

    def test_the_pages_of_the_merged_set_answer_every_record_once(self):
        """Walk the whole merged set in the paging (primary key) order."""
        for stride, positions in ((3, (1, 4, 7)), (5, (1, 6))):
            with self.subTest(maxRecords=stride):
                answered = []
                for start in positions:
                    answered += self.identifiers(
                        self.page(max_records=str(stride),
                                  start_position=str(start)))
                self.assertEqual(self.expected, answered)

    def test_a_page_deep_in_the_merged_set_answers_the_records_there(self):
        # a page boundary cutting through the sources: no single source
        # answers these positions -- page 8 of 8 is the last record of one
        # particular table of the three
        for start in (2, 5, 8):
            with self.subTest(startPosition=start):
                self.assertEqual(
                    self.expected[start - 1:start + 1],
                    self.identifiers(self.page(
                        max_records='2', start_position=str(start))))

    def test_a_deep_page_skips_its_offset_in_the_database(self):
        """The page query is one query over all sources and carries the OFFSET.

        The python merge had to read every record in front of the page from
        every source -- three materialisations growing with the position; a
        database which skips the offset answers the same page from one query
        no matter where the page starts.
        """
        def record_queries_at(start_position):
            with CaptureQueriesContext(connection) as context:
                self.page(max_records='2', start_position=start_position)
            record_queries = self.record_table_queries(
                context.captured_queries)
            # the three counts of numberOfRecordsMatched read every source
            # regardless of the position -- the page is what must not
            page_queries = [
                sql for sql in record_queries if 'COUNT(' not in sql.upper()]
            return record_queries, page_queries

        shallow_all, shallow_page = record_queries_at('1')
        deep_all, deep_page = record_queries_at('8')

        self.assertEqual(
            1, len(deep_page),
            'the merged page is not one query over all three sources')
        for sql in deep_page:
            self.assertIn('LIMIT', sql.upper(), sql)
            self.assertIn('OFFSET', sql.upper(),
                          'the page does not skip its offset in the database')
        self.assertEqual(
            len(shallow_all), len(deep_all),
            'a deeper page asks the record tables more often')

    def test_a_page_past_the_end_is_answered_without_reading_a_record(self):
        """The empty page is known from the count; nothing else is read.

        Table 66 answers a page whose records ran out with zero returned and
        no next record. Asking the database for a page the
        ``numberOfRecordsMatched`` already knows to be empty is pure cost --
        on the demo deployment it cost the same half minute as the last real
        page in front of it.
        """
        with CaptureQueriesContext(connection) as context:
            root = self.page(max_records='2', start_position='9')

        self.assertEqual(
            {'matched': '8', 'returned': '0', 'next': '0'},
            self.attributes(root))
        self.assertEqual([], list(root.xpath(
            f'{SEARCH_RESULTS}/*', namespaces=CSW)))

        page_queries = [
            sql for sql in self.record_table_queries(context.captured_queries)
            if 'COUNT(' not in sql.upper()]
        self.assertEqual(
            [], page_queries,
            'a page past the end still asked the record tables for records')

    def test_a_record_matched_by_two_keywords_is_answered_once_per_page(self):
        """The union keeps the deduplication of a keyword join.

        ``subject LIKE '%asser%'`` matches the beta record through two of its
        keywords; a page answers records, not keyword rows.
        """
        by_pk = {self.ds_beta.pk: 'de.mrmap.ds-beta',
                 self.ds_gamma.pk: 'de.mrmap.ds-gamma',
                 self.app_zeta.pk: 'de.mrmap.app-zeta'}
        self.assertEqual(
            [by_pk[pk] for pk in sorted(by_pk)],
            self.identifiers(self.page(
                max_records='10',
                constraint="subject LIKE '%asser%'")))

    def test_sortby_pages_the_merged_set_in_the_requested_order(self):
        # the order of the titles above, LOWER-ed -- and its reverse; the
        # deep pages below start where no single source could answer alone
        for sortby, expected in (
                ('title:A', self.expected_sorted),
                ('title:D', list(reversed(self.expected_sorted)))):
            with self.subTest(sortby=sortby):
                answered = []
                for start in (1, 4, 7):
                    answered += self.identifiers(self.page(
                        max_records='3', start_position=str(start),
                        sortby=sortby))
                self.assertEqual(expected, answered)

                self.assertEqual(
                    expected[5:7],
                    self.identifiers(self.page(
                        max_records='2', start_position='6', sortby=sortby)))

    def test_a_start_position_below_one_answers_the_first_record(self):
        """Table 65 leaves no position below 1; such one pages from the front.

        The slice arithmetic of the python merge made a negative position an
        index from the end of the merged list, which answered the request
        with the tail of the result set.
        """
        self.assertEqual(
            self.expected[:3],
            self.identifiers(self.page(
                max_records='3', start_position='0')))
