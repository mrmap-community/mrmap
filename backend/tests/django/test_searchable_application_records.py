"""A harvested application record answers the searchable vocabulary of the catalogue.

#828 as epic #851 re-scoped it: there is no ``SearchableApplicationMetadataRecord``
anymore -- the searchable representation of a record is the record itself, its stored
vector and its maintained keywords, and the endpoints search the record tables
directly (see ``csw/queryables.py``). The machinery landed with the model itself
(#975); what this module pins is the acceptance of the story end to end, for the one
kind of record which was missing from the search until now:

*   a record written the way a harvesting run writes one -- with its ``origin`` and
    its ``origin_url`` (the contract of #980) -- is found by the same filter
    vocabulary the dataset and the service records are found by (``AnyText`` words,
    ``subject`` keywords, a bounding box, the ``type``), without any rebuild step;
*   both endpoints which search records answer it -- ``GetRecords`` and the MapBender
    compatibility search; the ``GetRecordById`` lookup asks its table too and names
    the record by its stored document in the response (that body became answerable
    when #909 fixed the builder which used to drop it);
*   an update of the record replaces its words in the answer and a delete takes the
    record out of it, on the very next request.
"""

from django.contrib.gis.geos import MultiPolygon, Polygon
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from lxml import etree

from registry.enums.metadata import MetadataOriginEnum
from registry.models.metadata import (ApplicationMetadataRecord, Keyword,
                                      MetadataContact)
from registry.ows_lib.xml.consts import NAMESPACE_LOOKUP

GET_RECORDS = {
    'SERVICE': 'CSW',
    'REQUEST': 'GetRecords',
    'VERSION': '2.0.2',
}

GET_RECORD_BY_ID = {
    'SERVICE': 'CSW',
    'REQUEST': 'GetRecordById',
    'VERSION': '2.0.2',
}

MATCHED = '/csw:GetRecordsResponse/csw:SearchResults/@numberOfRecordsMatched'

ORIGIN_URL = 'https://example.org/csw/GetRecordById?id=de.beispiel.anwendung-1'


def gmd_document(identifier: str) -> bytes:
    """The stored document of a record, naming it as a response answers it."""
    return (
        '<gmd:MD_Metadata xmlns:gmd="http://www.isotc211.org/2005/gmd"'
        ' xmlns:gco="http://www.isotc211.org/2005/gco">'
        '<gmd:fileIdentifier>'
        f'<gco:CharacterString>{identifier}</gco:CharacterString>'
        '</gmd:fileIdentifier>'
        '</gmd:MD_Metadata>'
    ).encode('utf-8')


class HarvestedApplicationRecordIsSearchableTest(TestCase):
    """One application record, written like a harvest writes it, asked of the search."""

    def setUp(self):
        self.contact = MetadataContact.objects.create(
            name='Application searchable contact')
        # the values a harvesting run hands over beside the mapped fields -- the
        # origin and the origin url of the document -- are written onto the record
        # as well (#980), and the record below carries them the way md_metadata_
        # file_to_db does
        self.record = ApplicationMetadataRecord.objects.create(
            metadata_contact=self.contact,
            application_contact=self.contact,
            file_identifier='de.beispiel.anwendung-1',
            code_space='de.beispiel.',
            code='anwendung-1',
            title='Luftbeobachtung NRW',
            origin=MetadataOriginEnum.CATALOGUE.value,
            origin_url=ORIGIN_URL,
            bounding_geometry=MultiPolygon(Polygon.from_bbox(
                (6.0, 50.5, 7.5, 52.0))),
            xml_backup_file=SimpleUploadedFile(
                'anwendung-1.xml', gmd_document('de.beispiel.anwendung-1'),
                content_type='application/xml'))
        self.record.keywords.add(
            Keyword.objects.get_or_create(keyword='Klimaschutz')[0])

    def xml_of(self, *, result_type='hits', **query_params):
        response = self.client.get('/csw', {
            **GET_RECORDS,
            'resultType': result_type,
            **query_params,
        })
        self.assertEqual(response.status_code, 200, response.content)
        return etree.fromstring(response.content)

    def matched(self, constraint=None, **query_params):
        """The number of records a constraint matches, as the response names it."""
        if constraint:
            query_params.update({
                'CONSTRAINTLANGUAGE': 'CQL_TEXT',
                'Constraint': constraint,
            })
        content = self.xml_of(**query_params)
        return int(content.xpath(
            MATCHED, namespaces={'csw': NAMESPACE_LOOKUP['csw_2_0_2']})[0])

    def test_the_row_written_is_the_searchable_row(self):
        """What a projection used to carry, the record carries as its own columns.

        The vector answers the words of the title and of the keyword the moment the
        row is written, the keywords column answers the keyword as the relation
        does, and the provenance of the harvesting run stands on the row -- there
        is no second table to appear in and no refresh to wait for.
        """
        stored = ApplicationMetadataRecord.objects.get(pk=self.record.pk)
        self.assertEqual(['Klimaschutz'], stored.keywords_list)
        self.assertEqual(MetadataOriginEnum.CATALOGUE.value, stored.origin)
        self.assertEqual(ORIGIN_URL, stored.origin_url)
        self.assertTrue(stored.search_vector)

    def test_the_record_is_found_by_the_vocabulary_of_the_catalogue(self):
        """AnyText word, subject keyword, extent and kind -- the acceptance of #828."""
        self.assertEqual(1, self.matched("AnyText = 'luftbeobachtung'"))
        self.assertEqual(1, self.matched("AnyText = 'klimaschutz'"))
        self.assertEqual(1, self.matched("subject = 'Klimaschutz'"))
        self.assertEqual(1, self.matched(
            'BBOX(coverage, 5.0, 50.0, 8.0, 53.0)'))
        self.assertEqual(1, self.matched("type = 'application'"))

    def test_the_response_ships_the_stored_document_of_the_record(self):
        content = self.xml_of(result_type='results')
        identifiers = content.xpath(
            '//gmd:fileIdentifier/gco:CharacterString/text()',
            namespaces={
                'gmd': NAMESPACE_LOOKUP['gmd'],
                'gco': NAMESPACE_LOOKUP['gco']})
        self.assertEqual(['de.beispiel.anwendung-1'], identifiers)

    def test_get_record_by_id_finds_the_application_record(self):
        """The by-id lookup asks the application table and ships its document.

        This pin used to run over the stored-document-gone refusal of #912: the
        body of a ``GetRecordById`` response carried nothing for any kind of
        record while the builder dropped the matched documents, so the report
        of a lost backup was the only answer naming the application table
        (#909's tracked gap). Since that fix the document itself pins the
        lookup; the refusal of a record whose document the storage owes stays
        pinned in ``test_csw_missing_backup.py``.
        """
        response = self.client.get('/csw', {
            **GET_RECORD_BY_ID, 'Id': 'de.beispiel.anwendung-1'})
        self.assertEqual(response.status_code, 200, response.content)
        identifiers = etree.fromstring(response.content).xpath(
            '//gmd:fileIdentifier/gco:CharacterString/text()',
            namespaces={
                'gmd': NAMESPACE_LOOKUP['gmd'],
                'gco': NAMESPACE_LOOKUP['gco']})
        self.assertEqual(['de.beispiel.anwendung-1'], identifiers,
                         response.content)

    def test_the_mapbender_search_answers_the_application_record(self):
        """The branch of #828: the application kind is a browsable resource kind."""
        response = self.client.get('/mapbender/search', {
            'searchResources': 'application',
            'searchText': 'klimaschutz'})
        self.assertEqual(response.status_code, 200, response.content)
        answer = response.json()['application']

        self.assertEqual(1, answer['md']['nresults'])
        [entry] = answer['srv']
        self.assertEqual(str(self.record.pk), entry['id'])
        self.assertEqual('Luftbeobachtung NRW', entry['title'])
        self.assertEqual('6.0,50.5,7.5,52.0', entry['bbox'])

    def test_an_update_replaces_the_words_the_record_is_found_by(self):
        """The vector is computed for every written row -- nothing is rebuilt."""
        self.record.title = 'Wasserspiegel NRW'
        self.record.save()

        self.assertEqual(0, self.matched("AnyText = 'luftbeobachtung'"))
        self.assertEqual(1, self.matched("AnyText = 'wasserspiegel'"))
        # the keywords of the record survive a write which brings the default of the
        # maintained column (the guard of 0024, which #975 attached to this table)
        self.assertEqual(1, self.matched("subject = 'Klimaschutz'"))

    def test_a_delete_takes_the_record_out_of_every_answer(self):
        self.record.delete()

        self.assertEqual(0, self.matched("type = 'application'"))
        self.assertEqual(
            0, self.matched("AnyText = 'luftbeobachtung'"))

        response = self.client.get('/mapbender/search', {
            'searchResources': 'application',
            'searchText': 'klimaschutz'})
        self.assertEqual(0, response.json()['application']['md']['nresults'])
