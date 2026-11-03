"""The MapBender compatibility search, answered by the metadata records themselves.

``/mapbender/search`` is not the CSW endpoint: a MapBender client names its search words
as ``searchText`` and the kind of resource it wants as ``searchResources``, and the answer
is one JSON object per resource kind. Both are answered from the records now, through the
same querysets and the same vector a ``GetRecords`` searches (#855), which is what these
tests are about: the two branches of ``local_search`` and the values of an entry the
client renders.

The entry used to be built out of ``record.xml_backup`` -- the stored document of a record
-- which a record without a document answers as ``b""`` and which is bytes for every
record that has one; the values below are read from the record itself.
"""

from django.contrib.gis.geos import MultiPolygon, Polygon
from django.test import TestCase

from registry.models.metadata import (DatasetMetadataRecord, Keyword,
                                      MetadataContact, ServiceMetadataRecord)


class MapBenderSearchTest(TestCase):
    """The dataset and the service branch of ``/mapbender/search``."""

    def setUp(self):
        self.contact = MetadataContact.objects.create(
            name='MapBender search contact')

        self.wasser = self.record(
            DatasetMetadataRecord, title='Wasserversorgung Hamburg',
            keywords=['Wasser'],
            bounding_geometry=MultiPolygon(Polygon.from_bbox(
                (5.0, 47.0, 10.0, 55.0))))
        self.boden = self.record(
            DatasetMetadataRecord, title='Bodenrichtwerte Kiel',
            keywords=['Bauen & Wohnen'])
        self.berlin = self.record(
            ServiceMetadataRecord, title='Wasserversorgung Berlin',
            keywords=['Wasser'])

    def record(self, model, keywords=(), **fields):
        if model is DatasetMetadataRecord:
            # the dataset contact is the one invariant a dataset record has and a
            # service record does not
            fields.setdefault('dataset_contact', self.contact)
        record = model.objects.create(metadata_contact=self.contact, **fields)
        for keyword in keywords:
            # a keyword is a lookup row which every record carrying it shares (#817)
            record.keywords.add(
                Keyword.objects.get_or_create(keyword=keyword)[0])
        return record

    def search(self, **query_params):
        response = self.client.get('/mapbender/search', query_params)
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()

    def entries(self, resources='dataset', **query_params):
        """The answer of a search, as the client reads it: ``md`` and ``srv``.

        The primary key of a record reaches the client as the string the JSON encoder
        answers it as.
        """
        content = self.search(searchResources=resources, **query_params)
        return content[resources]

    def test_the_dataset_branch_answers_the_dataset_records_a_word_matches(self):
        answer = self.entries(searchText='wasser')

        self.assertEqual(1, answer['md']['nresults'])
        [entry] = answer['srv']
        self.assertEqual(str(self.wasser.pk), entry['id'])
        self.assertEqual('Wasserversorgung Hamburg', entry['title'])
        self.assertEqual(self.contact.name, entry['respOrg'])
        self.assertEqual('5.0,47.0,10.0,55.0', entry['bbox'])

    def test_the_service_branch_answers_the_service_records_a_word_matches(self):
        answer = self.entries('service', searchText='wasser')

        self.assertEqual(1, answer['md']['nresults'])
        [entry] = answer['srv']
        self.assertEqual(str(self.berlin.pk), entry['id'])
        self.assertEqual('Wasserversorgung Berlin', entry['title'])

    def test_a_word_of_a_keyword_is_a_word_of_a_record(self):
        """The words of the keywords are in the vector of a record, not only its text."""
        answer = self.entries(searchText='wohnen')

        self.assertEqual(1, answer['md']['nresults'])
        self.assertEqual('Bodenrichtwerte Kiel', answer['srv'][0]['title'])

    def test_a_star_browses_instead_of_searching_for_nothing(self):
        """``searchText=*`` is the way a MapBender client asks for everything.

        An empty search is not a search which matches nothing, which is what the
        ``SearchQuery("")`` of the searchable projection answered: an empty tsquery, so
        the browse the MapBender widget sends on its first page was always empty.
        """
        self.assertEqual(2, self.entries()['md']['nresults'])
        self.assertEqual(2, self.entries(searchText='*')['md']['nresults'])

    def test_the_second_page_answers_the_next_record(self):
        """The pages of one kind of record, in the order of their primary keys."""
        order = list(DatasetMetadataRecord.objects.order_by('pk')
                     .values_list('pk', flat=True))

        first = self.entries(searchText='*', maxResults=1, searchPages=1)['srv']
        second = self.entries(searchText='*', maxResults=1, searchPages=2)['srv']

        self.assertEqual([str(order[0])], [entry['id'] for entry in first])
        self.assertEqual([str(order[1])], [entry['id'] for entry in second])
        self.assertEqual(
            2, self.entries(searchText='*', maxResults=1,
                            searchPages=2)['md']['nresults'],
            'a page names the size of the whole result set, not of itself')

    def test_a_record_without_a_stored_document_is_answered_as_well(self):
        """Nothing of a search answer reads the stored document of a record anymore."""
        self.assertEqual(b'', self.boden.xml_backup)
        self.assertEqual(1, self.entries(
            searchText='bodenrichtwerte')['md']['nresults'])

    def test_a_resource_kind_no_search_answers_answers_no_records(self):
        """``searchResources`` other than the two kinds of a metadata record."""
        answer = self.entries('layer', searchText='wasser')

        self.assertEqual(0, answer['md']['nresults'])
        self.assertEqual([], answer['srv'])
