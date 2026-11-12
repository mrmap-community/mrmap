"""The queryables of a ``GetRecords``, answered by the metadata records themselves.

The scenarios of ``tests/behave/features/csw/get_records.feature`` ask the endpoint as a
client does; this asks it one queryable at a time. The reason is what a wrong answer of a
queryable looks like: a filter which is answered by the wrong column of a record answers
200 with the wrong hits, which no status code tells apart. So everything here counts the
records a filter matches, and the paging tests name the records a page answers.

The three queryables a record does not answer as a column of its own, and why ``AnyText``
is a search of words and not a pattern over a tsvector, are the subject of
``csw/queryables.py``; the records below are named so that a word only appears where the
test which searches for it means it to.
"""

from django.contrib.gis.geos import MultiPolygon, Polygon
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db.models import Q
from django.test import TestCase
from lxml import etree

from csw.queryables import dataset_records, search_filter
from registry.models.metadata import (ApplicationMetadataRecord,
                                      DatasetMetadataRecord, Keyword,
                                      MetadataContact, ServiceMetadataRecord)
from registry.ows_lib.xml.consts import NAMESPACE_LOOKUP

GET_RECORDS = {
    'SERVICE': 'CSW',
    'REQUEST': 'GetRecords',
    'VERSION': '2.0.2',
}

MATCHED = '/csw:GetRecordsResponse/csw:SearchResults/@numberOfRecordsMatched'


def gmd_document(identifier: str) -> bytes:
    """The document a metadata record is answered with by a ``GetRecords`` response.

    The response embeds the stored document of a record as it is, so the identifier
    below is what names a record in the response of the paging tests.
    """
    return (
        '<gmd:MD_Metadata xmlns:gmd="http://www.isotc211.org/2005/gmd"'
        ' xmlns:gco="http://www.isotc211.org/2005/gco">'
        '<gmd:fileIdentifier>'
        f'<gco:CharacterString>{identifier}</gco:CharacterString>'
        '</gmd:fileIdentifier>'
        '</gmd:MD_Metadata>'
    ).encode('utf-8')


class CswQueryablesTest(TestCase):
    """Every queryable of the catalogue, asked of the records it answers."""

    def setUp(self):
        self.contact = MetadataContact.objects.create(name='CSW queryables contact')

        # one record of each kind which is found by the same word, so that a filter on
        # the text of a record and a filter on the kind of a record can be told apart;
        # the codes are words on purpose, they are part of the vector of a record too
        self.alpha = self.record(
            DatasetMetadataRecord, 'alpha',
            title='Wasserversorgung Hamburg',
            keywords=['Wasser', 'wässrig', 'Wasserversorgung'])
        self.beta = self.record(
            DatasetMetadataRecord, 'beta',
            title='Bodenrichtwerte Schleswig-Holstein',
            keywords=['Bauen & Wohnen'])
        self.gamma = self.record(
            ServiceMetadataRecord, 'gamma',
            title='Wasserversorgung Berlin',
            keywords=['Boden'])

        # the application record of the mix: found by words no other record holds,
        # so its presence in every answer below is always the application kind's
        # doing and never the echo of another record
        self.zeta = self.record(
            ApplicationMetadataRecord, 'zeta',
            title='Anwendung Wartung Dresden',
            keywords=['Anwendung'])

        # the document of a record names it in the response of a page, its primary key
        # is the order the pages answer them in
        self.by_pk = {self.alpha.pk: 'alpha', self.beta.pk: 'beta',
                      self.gamma.pk: 'gamma', self.zeta.pk: 'zeta'}

    def record(self, model, identifier, keywords=(), **fields):
        """A metadata record with a document of its own and its keywords.

        The file identifier and the code of a record are named after the identifier the
        response names it with, which is what ``resource_identifier`` -- the stored
        generated column of ``code_space`` and ``code`` -- is written down from. Both are
        words of the vector of the record, so the identifier is deliberately a word no
        search of this module asks for.
        """
        if model is DatasetMetadataRecord:
            # the dataset contact is the one invariant a dataset record has and a
            # service record does not
            fields.setdefault('dataset_contact', self.contact)
        elif model is ApplicationMetadataRecord:
            # ... and the application contact is the same invariant of an
            # application record
            fields.setdefault('application_contact', self.contact)
        record = model.objects.create(
            metadata_contact=self.contact,
            code_space='de.mrmap.',
            code=identifier,
            file_identifier=f'de.mrmap.{identifier}',
            xml_backup_file=SimpleUploadedFile(
                f'{identifier}.xml', gmd_document(identifier),
                content_type='application/xml'),
            **fields)
        for keyword in keywords:
            # a keyword is a lookup row which every record carrying it shares (#817)
            record.keywords.add(
                Keyword.objects.get_or_create(keyword=keyword)[0])
        return record

    def xml_of(self, *, result_type='hits', **query_params):
        response = self.client.get('/csw', {
            **GET_RECORDS,
            'resultType': result_type,
            **query_params,
        })
        self.assertEqual(response.status_code, 200, response.content)
        return etree.fromstring(response.content)

    def matched(self, constraint=None, *, result_type='hits', **query_params):
        """The number of records a constraint matches, as the response names it."""
        if constraint:
            query_params.update({
                'CONSTRAINTLANGUAGE': 'CQL_TEXT',
                'Constraint': constraint,
            })
        return int(self.xml_of(
            result_type=result_type, **query_params).xpath(
                MATCHED, namespaces={'csw': NAMESPACE_LOOKUP['csw_2_0_2']})[0])

    def returned(self, constraint=None, **query_params):
        """The records a page answers, as the response names them, in that order."""
        if constraint:
            query_params.update({
                'CONSTRAINTLANGUAGE': 'CQL_TEXT',
                'Constraint': constraint,
            })
        content = self.xml_of(result_type='results', **query_params)
        return list(content.xpath(
            '//gmd:fileIdentifier/gco:CharacterString/text()',
            namespaces={
                'gmd': NAMESPACE_LOOKUP['gmd'],
                'gco': NAMESPACE_LOOKUP['gco']}))

    def test_without_a_filter_every_kind_of_record_is_answered(self):
        self.assertEqual(4, self.matched())

    def test_anytext_without_a_wildcard_is_a_word_a_record_holds(self):
        """The acceptance criterion of #855: ``AnyText`` as a real tsquery.

        ``wohnen`` is a word of the keyword ``Bauen & Wohnen`` of one record, which is
        what the vector of that record holds; a pattern lookup over the vector itself is
        what postgres refuses with ``function lower(tsvector) does not exist``.
        """
        self.assertEqual(1, self.matched("AnyText = 'wohnen'"))

    def test_anytext_with_a_wildcard_is_answered_by_the_texts_of_a_record(self):
        """A pattern is asked of the texts, and ECQL ``LIKE`` is case sensitive.

        ``ILIKE`` is the spelling a client uses to ask for the same pattern without
        case, see the ``like`` / ``ilike`` rules of the ECQL grammar; the rewrite of
        ``csw/queryables.search_filter`` keeps whichever of the two the client chose.
        """
        self.assertEqual(2, self.matched("AnyText LIKE '%Wasser%'"))
        self.assertEqual(0, self.matched("AnyText LIKE '%wasser%'"))
        self.assertEqual(2, self.matched("AnyText ILIKE '%wasser%'"))

    def test_a_pattern_of_anytext_is_rewritten_onto_the_texts_of_a_record(self):
        """The statement a wildcarded ``AnyText`` compiles to names the texts.

        Asked here instead of through a request, because what the request answers is the
        same 200 the test above counts; what has to be pinned is that the pattern never
        reaches the vector -- postgres has no ``upper(tsvector)`` and the endpoint
        answered 500 on every wildcarded search because of that.
        """
        _, _, condition = str(dataset_records().filter(
            search_filter(Q(search_vector__icontains='wasser'))).query).partition(
            ' WHERE ')

        self.assertNotIn('search_vector', condition)
        for text_field in ('"title"', '"abstract"', '"keyword"'):
            self.assertIn(
                text_field, condition,
                f'a pattern does not ask {text_field} of a record')

    def test_subject_is_a_keyword_of_a_record(self):
        self.assertEqual(1, self.matched("subject = 'Bauen & Wohnen'"))
        self.assertEqual(1, self.matched("subject LIKE '%Wohn%'"))

    def test_subject_matched_by_several_keywords_still_matches_one_record(self):
        """A record holding two matching keywords is one record, not two hits.

        A filter on a keyword joins the keywords of a record, so the same record comes
        back once per matching keyword; the response names the number of *records*
        matched, see ``csw/queryables.search_records``.
        """
        self.assertEqual(1, self.matched("subject LIKE '%asser%'"))

    def test_type_is_the_kind_of_record_a_queryset_answers(self):
        self.assertEqual(2, self.matched("type = 'dataset'"))
        self.assertEqual(1, self.matched("type = 'service'"))
        self.assertEqual(1, self.matched("type = 'application'"))

    def test_an_application_record_is_found_by_its_words_and_its_keywords(self):
        """The vocabulary of #828: an application record answers it like the others.

        The searchable projection of #828 was re-scoped by epic #851: the record
        itself answers the vector and the keywords, so these counts are the whole
        of what the story asked for the view.
        """
        self.assertEqual(1, self.matched("AnyText = 'wartung'"))
        self.assertEqual(1, self.matched("AnyText = 'anwendung'"))
        self.assertEqual(1, self.matched("subject = 'Anwendung'"))

    def test_the_queryables_narrow_each_other(self):
        # the word is a keyword of the service record ...
        self.assertEqual(1, self.matched("AnyText = 'boden' AND type = 'service'"))
        # ... and no dataset record holds it as a word: 'Bodenrichtwerte' is another word
        self.assertEqual(0, self.matched("AnyText = 'boden' AND type = 'dataset'"))
        self.assertEqual(0, self.matched(
            "type = 'service' AND subject = 'Bauen & Wohnen'"))

    def test_a_bounding_box_selects_the_records_inside_it(self):
        """``coverage`` and ``ows:BoundingBox`` are the geometry of a record."""
        self.alpha.bounding_geometry = MultiPolygon(Polygon.from_bbox(
            (5.0, 47.0, 10.0, 55.0)))
        self.alpha.save()
        self.zeta.bounding_geometry = MultiPolygon(Polygon.from_bbox(
            (6.0, 48.0, 9.0, 51.0)))
        self.zeta.save()

        self.assertEqual(2, self.matched('BBOX(coverage, 4.0, 46.0, 11.0, 56.0)'))
        # the application record answers the extent like the others (#828)
        self.assertEqual(
            1, self.matched(
                "BBOX(coverage, 4.0, 46.0, 11.0, 56.0) AND type = 'application'"))
        self.assertEqual(0, self.matched('BBOX(coverage, -10.0, 30.0, -5.0, 35.0)'))

    def test_resource_identifier_and_identifier_are_columns_of_a_record(self):
        self.assertEqual(1, self.matched("ResourceIdentifier = 'de.mrmap.alpha'"))
        self.assertEqual(1, self.matched("identifier = 'de.mrmap.beta'"))

    def test_a_record_written_between_two_requests_is_in_the_second_one(self):
        """A record is findable the moment it is stored, which is the point of #854.

        The searchable projections were refreshed by a periodic task and by the bulk
        write hooks of the record managers, so a record which was written by either path
        was not findable until the next rebuild.
        """
        self.record(DatasetMetadataRecord, 'delta',
                    title='Frisch geerntete Metadaten', keywords=['Ernte'])
        self.assertEqual(5, self.matched())

    def test_a_record_deleted_between_two_requests_is_gone_from_the_second_one(self):
        self.beta.delete()
        self.assertEqual(3, self.matched())
        self.assertEqual(0, self.matched("identifier = 'de.mrmap.beta'"))

    def test_a_record_which_is_not_answered_by_the_request_is_not_matched(self):
        self.assertEqual(0, self.matched("AnyText = 'wald'"))

    def test_two_requests_for_the_second_page_answer_the_same_records(self):
        """The paging which the skipped scenarios of #837 could not ask for."""
        page = {'maxRecords': 2, 'startPosition': 3}
        self.assertEqual(self.returned(**page), self.returned(**page))

    def test_the_pages_of_a_query_answer_every_record_once_in_one_order(self):
        ordered = [self.by_pk[pk] for pk in sorted(self.by_pk)]

        first = self.returned(maxRecords=2, startPosition=1)
        second = self.returned(maxRecords=2, startPosition=3)

        self.assertEqual(ordered, first + second)
        self.assertEqual(2, len(first), 'the first page does not answer two records')
        self.assertEqual(2, len(second), 'the second page does not answer two records')

    def test_every_page_answers_the_number_of_records_the_query_matches(self):
        """The second number of the response is the size of the whole result set."""
        for start_position in ('1', '3', '5'):
            with self.subTest(startPosition=start_position):
                self.assertEqual(4, self.matched(
                    result_type='results',
                    maxRecords='2',
                    startPosition=start_position))

    def test_a_record_without_a_keyword_is_answered_by_its_text_only(self):
        self.record(DatasetMetadataRecord, 'epsilon',
                    title='Ohne Stichworte nur Text')
        self.assertEqual(1, self.matched("AnyText = 'stichworte'"))
        self.assertEqual(0, self.matched("subject = 'stichworte'"))

    # -- the identity of the ``type`` filter and the merged paging of #829 --
    #
    # The counts above say HOW MANY records a kind matches; these name WHICH
    # records a query answers. A type filter wired to the wrong source answers
    # the same count with the wrong documents -- only the identifiers a page
    # ships tell the three kinds apart, since all of them share one document
    # type (gmd:MD_Metadata) on the wire.

    def identifiers(self, *names):
        """The named records in the paging (primary key) order the response answers."""
        pk_of = {name: pk for pk, name in self.by_pk.items()}
        return sorted(names, key=pk_of.__getitem__)

    def test_the_type_filter_answers_only_the_records_of_the_kind_it_names(self):
        """#829: a kind asked for answers its records and none of the others.

        The application query answers the application record and nothing else;
        the two kinds which were answered before it arrived keep answering
        exactly their own records -- the union of the third source must not
        leak into either.
        """
        self.assertEqual(['zeta'],
                         self.returned("type = 'application'"))
        self.assertEqual(self.identifiers('alpha', 'beta'),
                         self.returned("type = 'dataset'"))
        self.assertEqual(['gamma'],
                         self.returned("type = 'service'"))

    def test_an_or_over_all_three_kinds_answers_one_paged_stream(self):
        """#829: dataset OR service OR application pages as one result set.

        The harvesting client of #827 requests exactly this shape when it asks
        a remote catalogue for all three kinds in one query; a page boundary
        in the merged stream must neither drop a record nor answer it twice.
        """
        every_kind = "type = 'dataset' OR type = 'service' OR type = 'application'"
        self.assertEqual(4, self.matched(every_kind))

        ordered = self.identifiers('alpha', 'beta', 'gamma', 'zeta')
        self.assertEqual(
            ordered, self.returned(every_kind, maxRecords=10))

        first = self.returned(every_kind, maxRecords=2, startPosition=1)
        second = self.returned(every_kind, maxRecords=2, startPosition=3)
        self.assertEqual(2, len(first))
        self.assertEqual(2, len(second))
        self.assertEqual(ordered, first + second)

        # every page of the OR names the size of the whole merged set
        self.assertEqual(4, self.matched(
            every_kind, result_type='results', maxRecords='2', startPosition='3'))

    def test_an_or_over_two_kinds_keeps_the_third_kind_out_of_the_pages(self):
        """The OR is selective: the kind it does not name answers nothing.

        The dataset-and-application pair is the shape which pages across the
        boundary of the merged stream -- two records of the one source in
        front of the record of the other -- so a wrong merge order or a wrong
        page cut on the merged sources shows up in its pages.
        """
        pair = "type = 'dataset' OR type = 'application'"
        self.assertEqual(3, self.matched(pair))

        ordered = self.identifiers('alpha', 'beta', 'zeta')
        first = self.returned(pair, maxRecords=2, startPosition=1)
        second = self.returned(pair, maxRecords=2, startPosition=3)

        self.assertEqual(ordered, first + second)
        self.assertNotIn('gamma', first + second)
