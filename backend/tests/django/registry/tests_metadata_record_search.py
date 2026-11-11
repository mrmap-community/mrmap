"""A searched metadata record list is answered by the vector of the records.

Both metadata record lists searched their title, their abstract and the keywords of
a record with ``UPPER(...) LIKE '%word%'`` (#1029). Two of those three texts are
columns of the record, but the third is a word of a keyword behind the m2m relation
of it, so postgres hash-joined the keyword relation of the whole catalogue, applied
the patterns to the joined rows and collapsed the duplicate ids the join produced.
DRF's pagination asks that very statement for the number of rows of the answer,
which made the count of a searched list the most expensive statement of the request
-- 92 % of it in dump 517b1602, 52 s at its worst in dump b11ebfbc.

A record answers its searchable representation as a column with a GIN index since
#854, so what is pinned here is the shape of the statements a searched list makes:
one containment over the vector, for the rows as for their count, and no keyword
relation in either. That the column is indexed and what its vector holds is pinned
by ``tests_search_vector.py``; what a search finds is pinned as it changes here.
"""

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

from registry.expressions.search import TEXT_CONFIGURATION_NAME
from registry.models.metadata import (DatasetMetadataRecord, Keyword,
                                      MetadataContact, ServiceMetadataRecord)

JSONAPI = 'application/vnd.api+json'

# the statement DRF's paginator asks for the number of rows of an answer
COUNT = 'COUNT(*) AS "__count"'

# the words the records below hold: every search word of these tests is one of them
# or a deliberate piece or none of them
WATER = 'wasserversorgung'
GROUNDWATER = 'grundwasser'
GEOTHERMY = 'geothermie'
BOTH = 'karten'
NO_WORD = 'bohrung'


class RecordListMixin:
    """One metadata record list endpoint, asked of the search.

    A subclass names the endpoint, the table of its records, the table of their
    keyword relation and how a record of that kind is written; everything below is
    asserted for both of them, because both lists paid the same cost.
    """

    endpoint = None
    model = None
    keywords_through = None

    @classmethod
    def record(cls, title, abstract='', keywords=()):
        raise NotImplementedError

    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.get(username='User1')
        cls.contact = MetadataContact.objects.create(name='Search contact')
        cls.water = cls.record(
            title='Wasserversorgung Hamburg', abstract='Karten zum Grundwasser')
        cls.hydrology = cls.record(
            title='Bodenrichtwerte Kiel', abstract='Karten zur Hydrologie',
            keywords=[GEOTHERMY])

    def request(self, **params):
        """The searched list, as (status, body, statements of the request)."""
        client = APIClient()
        client.force_authenticate(user=self.user)
        with CaptureQueriesContext(connection) as context:
            response = client.get(self.endpoint, params, HTTP_ACCEPT=JSONAPI)
            if not response.is_rendered:
                response.render()
        return response.status_code, response.json(), list(context)

    def count_of(self, queries):
        """The statement the paginator asked for the number of rows."""
        counts = [query['sql'] for query in queries if COUNT in query['sql']]
        self.assertEqual(
            len(counts), 1,
            msg=f'expected exactly one count statement, got {counts}')
        return counts[0]

    def page_of(self, queries):
        """The statement which asked for the rows of the page itself."""
        table = self.model._meta.db_table
        pages = [query['sql'] for query in queries
                 if f'"{table}"' in query['sql'] and 'LIMIT' in query['sql'].upper()]
        self.assertEqual(
            len(pages), 1,
            msg=f'expected exactly one statement reading {table}, got {pages}')
        return pages[0]

    def test_a_word_of_the_title_finds_the_record(self):
        _status, body, _queries = self.request(**{'filter[search]': WATER})
        self.assertEqual(
            [resource['id'] for resource in body['data']], [str(self.water.pk)])

    def test_a_word_of_the_abstract_finds_the_record(self):
        """The abstract is searchable, as it was before the vector answered it."""
        _status, body, _queries = self.request(**{'filter[search]': GROUNDWATER})
        self.assertEqual(
            [resource['id'] for resource in body['data']], [str(self.water.pk)])

    def test_a_word_of_a_keyword_finds_the_record(self):
        """A word which only ever appeared in a keyword of a record finds it.

        This is the search which used to join the keyword relation of the whole
        catalogue and which the vector of the record answers from its own column.
        """
        _status, body, _queries = self.request(**{'filter[search]': GEOTHERMY})
        self.assertEqual(
            [resource['id'] for resource in body['data']],
            [str(self.hydrology.pk)])

    def test_a_word_no_record_holds_finds_nothing(self):
        _status, body, _queries = self.request(**{'filter[search]': NO_WORD})
        self.assertEqual(body['data'], [])
        self.assertEqual(body['meta']['pagination']['count'], 0)

    def test_words_of_different_records_find_nothing(self):
        """Every word of a search has to be a word of the record, as before."""
        _status, body, _queries = self.request(
            **{'filter[search]': f'{WATER} {GEOTHERMY}'})
        self.assertEqual(body['data'], [])

    def test_a_piece_of_a_word_finds_nothing(self):
        """A record is found by its words and not by pieces of them.

        This is the price of the index: a tsquery holds words, so what the LIKE
        construction answered for a piece of a word is not answered by the vector.
        It is the same vocabulary the CSW and the MapBender search of this api
        answer with, and it is pinned so that the tradeoff of a word for a piece
        of one is a decision of this code and not an accident.
        """
        # the word of the record without its first letter: a piece which no
        # stemming can produce, because stemming only takes letters off the
        # end
        _status, body, _queries = self.request(
            **{'filter[search]': 'asserversorgung'})
        self.assertEqual(body['data'], [])

    def test_an_empty_search_does_not_filter(self):
        """Without a word the client browses, which is not a search.

        An empty tsquery matches nothing, so an empty search parameter must not
        reach it -- the search of DRF does not filter for an empty term either.
        """
        _status, body, _queries = self.request(**{'filter[search]': '   '})
        self.assertEqual(
            body['meta']['pagination']['count'], self.model.objects.count())

    def test_a_searched_list_answers_the_count_of_the_records_it_holds(self):
        _status, body, _queries = self.request(**{'filter[search]': BOTH})
        self.assertEqual(body['meta']['pagination']['count'], 2)
        self.assertEqual(len(body['data']), 2)

    def test_a_searched_list_is_counted_by_a_containment_over_the_vector(self):
        """The count is the statement #1029 is about; it may not search texts.

        Pinned on the statement and not on a duration: what costs is the shape of
        the statement -- a pattern over a text is answered by scanning the table and
        joining the keywords, a containment over the vector by its index.
        """
        _status, _body, queries = self.request(**{'filter[search]': GEOTHERMY})
        count = self.count_of(queries)
        self.assertIn('@@', count)
        self.assertIn('plainto_tsquery', count)
        self.assertNotIn(
            'LIKE', count.upper(), msg=f'the count still searches texts: {count}')
        self.assertNotIn(
            self.keywords_through, count,
            'the count still asks the keyword relation of the records')

    def test_a_searched_list_is_read_by_a_containment_over_the_vector(self):
        """The rows of the page are selected the same way as they are counted."""
        _status, _body, queries = self.request(**{'filter[search]': GEOTHERMY})
        page = self.page_of(queries)
        self.assertIn('@@', page)
        self.assertNotIn(
            'LIKE', page.upper(), msg=f'the page still searches texts: {page}')
        self.assertNotIn(
            self.keywords_through, page,
            'the page still asks the keyword relation of the records')

    def test_a_search_which_is_not_a_word_is_still_only_a_word(self):
        """The probe of dump b11ebfbc costs one index probe and not four scans.

        The string is not an injection -- the search was parameterised before -- but
        every word of it used to be one more wildcard pattern over the joined
        keyword relation, which is what the 52 s of that dump were.
        """
        _status, body, queries = self.request(**{'filter[search]': "' OR 1=1 --"})
        self.assertEqual(_status, 200)
        self.assertEqual(body['data'], [])
        count = self.count_of(queries)
        self.assertIn('@@', count)
        self.assertNotIn('LIKE', count.upper())

    def test_the_count_of_a_searched_list_is_answered_by_the_index(self):
        """The count of a searched list is answered by the index of the vector.

        The shape of the statement is pinned above; this asks the planner which
        index answers it. The sequential scan is ruled out because a test database
        is small and would be scanned anyway, which is what
        ``tests_search_vector.py`` does for the same column.
        """
        table = self.model._meta.db_table
        with connection.cursor() as cursor:
            cursor.execute(
                'SELECT indexname FROM pg_indexes WHERE tablename = %s'
                " AND indexdef ILIKE %s", [table, '%using gin%search_vector%'])
            names = [row[0] for row in cursor.fetchall()]
        self.assertEqual(len(names), 1, f'expected one gin index on {table}')
        with connection.cursor() as cursor:
            cursor.execute('SET LOCAL enable_seqscan = OFF')
            cursor.execute(
                f'EXPLAIN (COSTS OFF) SELECT COUNT(*) AS "__count" FROM "{table}"'
                f' WHERE "{table}"."search_vector" @@'
                f" plainto_tsquery('{TEXT_CONFIGURATION_NAME}'::regconfig,"
                f" '{GEOTHERMY}')")
            plan = '\n'.join(row[0] for row in cursor.fetchall())
        self.assertIn(
            names[0], plan,
            msg=f'the count is not answered by the index of the vector:\n{plan}')


class DatasetMetadataListSearchTest(RecordListMixin, TestCase):
    """The list of dataset metadata records, one entry point of the search screen."""

    endpoint = '/api/registry/dataset-metadata'
    model = DatasetMetadataRecord
    keywords_through = 'registry_datasetmetadatarecord_keywords'

    fixtures = ['test_users.json']

    @classmethod
    def record(cls, title, abstract='', keywords=()):
        record = DatasetMetadataRecord.objects.create(
            metadata_contact=cls.contact, dataset_contact=cls.contact,
            title=title, abstract=abstract)
        record.keywords.set([Keyword.objects.create(keyword=word)
                             for word in keywords])
        return record


class ServiceMetadataListSearchTest(RecordListMixin, TestCase):
    """The list of service metadata records, which paid the same cost as the other."""

    endpoint = '/api/registry/service-metadata'
    model = ServiceMetadataRecord
    keywords_through = 'registry_servicemetadatarecord_keywords'

    fixtures = ['test_users.json']

    @classmethod
    def record(cls, title, abstract='', keywords=()):
        record = ServiceMetadataRecord.objects.create(
            metadata_contact=cls.contact, title=title, abstract=abstract)
        record.keywords.set([Keyword.objects.create(keyword=word)
                             for word in keywords])
        return record


class TextSearchStillSearchesTextsTest(TestCase):
    """A list which searches a plain text keeps the substring search of DRF.

    The vector is the searchable representation of a *metadata record*; every other
    endpoint is searched by the base of this filter, which is how a single text
    column of a keyword or a service is searched.
    """

    fixtures = ['test_users.json']

    def test_a_keyword_is_found_by_a_piece_of_its_word(self):
        Keyword.objects.create(keyword='Wasserversorgung')
        client = APIClient()
        client.force_authenticate(
            user=get_user_model().objects.get(username='User1'))
        response = client.get(
            '/api/registry/keywords', {'filter[search]': 'sserversorg'},
            HTTP_ACCEPT=JSONAPI)
        if not response.is_rendered:
            response.render()
        body = response.json()
        self.assertEqual(body['meta']['pagination']['count'], 1, msg=body)
