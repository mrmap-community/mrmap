"""The ``numberOfRecordsMatched`` of a ``GetRecords``, counted over primary keys.

#1172 made the cost of a page independent of its position; what was left was a
flat ~12 s per request, measured on a 680 k-record corpus, spent in the three
``queryset.count()`` calls answering ``numberOfRecordsMatched``. Each of the
three record sources is ``distinct()`` over a join, and Django's count of a
distinct queryset wraps the *whole select list* in the ``SELECT DISTINCT``
subquery it has to build -- for these models every column of the record table,
the stored XML document among them -- so the database hashed full records to
answer a number (7.7 s for one count of the service table). Projecting the
primary key first answers the same number with a hash over ids: ~65x faster
measured, and what the response names is a count of *records* either way --
a record is distinct by its key.

So this module pins both halves:

* the answered number: every source counted once, a record matched through
  two keywords still one record, hits and a page in agreement;
* the statement behind it: every count of a record table projects its
  ``DISTINCT`` onto the primary key and carries no column of a record --
  no document, no text -- into the hash.
"""

import re

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
FILE_IDENTIFIERS = '//gmd:fileIdentifier/gco:CharacterString/text()'

#: The three tables a count of a GetRecords reads, one source each.
RECORD_TABLES = (
    'registry_datasetmetadatarecord',
    'registry_servicemetadatarecord',
    'registry_applicationmetadatarecord',
)

#: The constraint of the measured request: a keyword filter, which joins a
#: record once per matching keyword and is what makes the DISTINCT (and the
#: cost of hashing every column through it) unavoidable in the first place.
KEYWORD_CONSTRAINT = "subject LIKE '%asser%'"


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


class CswGetRecordsCountTests(TestCase):
    """What the count of a GetRecords answers and what it asks the database."""

    @classmethod
    def setUpTestData(cls):
        cls.contact = MetadataContact.objects.create(name='CSW count contact')
        # four records across all three tables; the keyword constraint below
        # matches the dataset record through TWO of its keywords and the
        # service record through one, so the matched records are 2 while the
        # joined rows are 3 -- and the unfiltered answer tells a dropped
        # constraint from a deduplicated one
        cls.ds_beta = cls.record(
            DatasetMetadataRecord, 'ds-beta',
            keywords=['Wasser', 'Wasserversorgung'])
        cls.ds_alpha = cls.record(
            DatasetMetadataRecord, 'ds-alpha', keywords=['Landwirtschaft'])
        cls.svc_epsilon = cls.record(
            ServiceMetadataRecord, 'svc-epsilon', keywords=['Wasser'])
        cls.app_zeta = cls.record(
            ApplicationMetadataRecord, 'app-zeta', keywords=['Anwendung'])

    @classmethod
    def record(cls, model, name, keywords=()):
        identifier = f'de.mrmap.{name}'
        fields = dict(
            metadata_contact=cls.contact,
            title=name.replace('-', ' ').title(),
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
        return record

    def request(self, *, result_type='hits', constraint=None, **params):
        """One ``GetRecords`` answered as a document."""
        query = {**GET_RECORDS, 'resultType': result_type, **params}
        if constraint is not None:
            query.update({
                'CONSTRAINTLANGUAGE': 'CQL_TEXT',
                'Constraint': constraint,
            })
        response = self.client.get('/csw', query)
        self.assertEqual(response.status_code, 200, response.content)
        return etree.fromstring(response.content)

    def matched(self, **kwargs):
        root = self.request(**kwargs)
        return int(root.xpath(MATCHED, namespaces=CSW)[0])

    def count_queries(self, captured):
        """The captured queries of one request which count a record table.

        A ``hits`` request reads no record of the result set: every query
        which names a record table is one of the three counts of
        ``numberOfRecordsMatched``.
        """
        return [
            query['sql'] for query in captured
            if any(table in query['sql'] for table in RECORD_TABLES)]

    def test_the_matched_count_is_records_not_keyword_rows(self):
        """The deduplicated answer the response owes, on every kind of query.

        The beta record is joined twice by the constraint and has to be
        counted once; unfiltered the same request answers all four records.
        """
        self.assertEqual(4, self.matched())
        self.assertEqual(2, self.matched(constraint=KEYWORD_CONSTRAINT))

    def test_hits_and_a_page_answer_one_and_the_same_count(self):
        """The pk projection changed the SQL of the count, not its number.

        A page ships the records and names the whole result set beside them;
        hits name the same number and read no record -- both must agree,
        filtered and unfiltered.
        """
        for constraint in (None, KEYWORD_CONSTRAINT):
            with self.subTest(constraint=constraint):
                expected = self.matched(constraint=constraint)
                self.assertEqual(
                    expected,
                    self.matched(result_type='results', maxRecords='1',
                                 constraint=constraint))

    def test_a_page_after_the_count_still_answers_the_matched_records(self):
        """The page query is untouched: it still ships what the count counted."""
        root = self.request(result_type='results', maxRecords='10',
                            constraint=KEYWORD_CONSTRAINT)
        self.assertEqual(
            ['de.mrmap.ds-beta', 'de.mrmap.svc-epsilon'],
            sorted(root.xpath(FILE_IDENTIFIERS, namespaces=GMD)))
        self.assertEqual(2, int(root.xpath(MATCHED, namespaces=CSW)[0]))

    def test_the_count_projects_only_the_primary_key(self):
        """The statement behind the number: DISTINCT over ids, nothing else.

        The measured 7.7 s were the database hashing ~440 k service rows with
        their stored XML documents -- the full model column list the count of
        a distinct queryset keeps in its subquery. The count of every source
        has to project its DISTINCT onto the primary key and carry no other
        column of the record into it, while the keyword join of the request
        stays what selects the records.
        """
        with CaptureQueriesContext(connection) as context:
            self.assertEqual(2, self.matched(constraint=KEYWORD_CONSTRAINT))

        counts = self.count_queries(context.captured_queries)
        self.assertEqual(
            3, len(counts),
            'a GetRecords does not count the three record sources once each')

        for sql in counts:
            self.assertIn('COUNT(', sql.upper(), sql)
            table = next(table for table in RECORD_TABLES if table in sql)
            projection = sql.partition('SELECT DISTINCT')[2].partition(
                ' FROM ')[0]
            columns = set(re.findall(r'"(\w+)"\."(\w+)"', projection))
            self.assertEqual(
                {(table, 'id')}, columns,
                f'the count of {table} does not project its DISTINCT onto '
                f'the primary key alone: {projection}')
            self.assertNotIn(
                'xml_backup_file', sql,
                'the count still reads the stored document of a record')
            self.assertIn(
                'keyword', sql,
                'the count dropped the keyword join of the constraint')
