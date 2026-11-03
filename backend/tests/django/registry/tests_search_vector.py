"""The searchable representation of a metadata record as a column of the record.

What matters here is that a record is findable by what it says and by what it is tagged
with the moment it is written: the vector is computed by the database for every row, so
nothing has to be rebuilt for a record to be found and no window exists in which a
stored record is not. The vector is also only what a search *hits*, never a value an
answer reads, which the tests about the API and the read cost pin.
"""

from django.contrib.postgres.search import SearchQuery
from django.core.management import call_command
from django.db import connection
from django.test import TestCase, TransactionTestCase

from registry.expressions.search import TEXT_CONFIGURATION_NAME
from registry.mappers.persistence.custom import _defaults_of_instance
from registry.models.metadata import (DatasetMetadataRecord, Keyword, MetadataContact,
                                      ServiceMetadataRecord)
from registry.serializers.metadata import (DatasetMetadataRecordSerializer,
                                           ServiceMetadataRecordSerializer)
from registry.views.metadata import (DatasetMetadataViewSetMixin,
                                     ServiceMetadataViewSetMixin)

RECORDS = (DatasetMetadataRecord, ServiceMetadataRecord)


class RecordVectorMixin:
    """Reading the vector back from the database, never from an instance."""

    def vector_of(self, record):
        return record.__class__.objects.values_list(
            'search_vector', flat=True).get(pk=record.pk)

    def lexemes_of(self, record):
        """The lexemes of the vector, which is what a query is matched against.

        The text of a tsvector quotes and orders its lexemes in a way which is not
        worth asserting on; the array of its lexemes says the same thing readable.
        """
        with connection.cursor() as cursor:
            cursor.execute(
                f'SELECT tsvector_to_array(search_vector) FROM {record._meta.db_table}'
                ' WHERE id = %s',
                [record.pk])
            return cursor.fetchone()[0]

    def found_by(self, record, words):
        """Whether a search for the words selects the record.

        This is the very comparison a consumer of the column makes: a tsvector is
        matched against a tsquery by the database, in the configuration the vector is
        built with. Asserting on the lexemes of a word instead would pin the stemming of
        that configuration, which the column does not promise.
        """
        return record.__class__.objects.filter(
            pk=record.pk,
            search_vector=SearchQuery(words, config=TEXT_CONFIGURATION_NAME),
        ).exists()


class SearchVectorGenerationTest(TestCase):
    """The expression the database computes the column from.

    A stored generated column is stored in the catalog and evaluated again for every
    written row, which rules out the two things these expressions are written around:
    parameters and functions which are not immutable. Both rules are of postgres, so
    they are asserted here against the statement django hands to it.
    """

    def test_the_generation_expression_of_both_records_needs_no_parameters(self):
        for model in RECORDS:
            with self.subTest(model=model.__name__):
                sql, params = model._meta.get_field(
                    'search_vector').generated_sql(connection)
                self.assertEqual(params, ())
                self.assertNotIn('%s', sql)

    def test_the_generation_expression_of_both_records_is_the_same(self):
        """One record is found by the same words the other is found by."""
        vectors = {
            model._meta.get_field('search_vector').generated_sql(connection)[0]
            for model in RECORDS}
        self.assertEqual(len(vectors), 1)

    def test_the_vector_is_built_from_every_text_a_record_answers_with(self):
        """The words a record is found by are the ones its projection concatenated.

        Named here and not read from the expression: a column which stops feeding the
        vector silently stops being searchable, which is what the searchable
        projection of the record used to answer.
        """
        sql = next(iter(
            model._meta.get_field('search_vector').generated_sql(connection)[0]
            for model in RECORDS))
        for column in ('title', 'abstract', 'file_identifier', 'code', 'code_space',
                       'keywords_list'):
            self.assertIn(f'"{column}"', sql)


class SearchVectorContentTest(TestCase, RecordVectorMixin):
    """What a record's vector answers a search with."""

    @classmethod
    def setUpTestData(cls):
        cls.contact = MetadataContact.objects.create(name='Search contact')
        cls.dataset = DatasetMetadataRecord.objects.create(
            metadata_contact=cls.contact, dataset_contact=cls.contact,
            title='Wasserversorgung Hamburg')
        cls.service_metadata = ServiceMetadataRecord.objects.create(
            metadata_contact=cls.contact, title='Bodenrichtwerte Schleswig-Holstein')
        cls.keyword = Keyword.objects.create(keyword='Bauen & Wohnen')

    def test_a_record_is_found_by_the_words_of_its_title(self):
        self.assertTrue(self.found_by(self.dataset, 'Wasserversorgung'))
        self.assertTrue(self.found_by(self.dataset, 'Hamburg'))
        self.assertFalse(self.found_by(self.dataset, 'Bodenrichtwerte'))

    def test_a_record_is_found_by_its_file_identifier(self):
        """The identifier of a record is one of the texts it is found by.

        A harvesting client looks a record up by its identifier, and the searchable
        projection of a record answered the identifier in its vector before the vector
        was a column of the record.
        """
        self.assertTrue(self.found_by(self.dataset, str(self.dataset.file_identifier)))

    def test_the_words_of_a_keyword_are_found(self):
        """A keyword is searchable by its words and not only as one term.

        The words of a keyword are the only place a word which never appeared in the
        text of a record can come from, so this is what a record is findable by.
        """
        self.dataset.keywords.set([self.keyword])
        self.assertTrue(self.found_by(self.dataset, 'wohnen'))
        self.assertNotIn('Bauen & Wohnen', self.lexemes_of(self.dataset))

    def test_a_record_is_found_by_the_words_at_the_end_of_a_long_keyword(self):
        """The tail of a long keyword is as findable as its beginning (#894).

        A catalogue which joins its plan names into one keyword asks two things of the
        storage: that the keyword is storable at all, and that the words of it reach
        the vector of the record. The array of a fixed width refused the first on the
        write of the record row, and a truncation to that width would have dropped the
        words of the tail in silence. The keyword here names one plan at its end which
        nothing else of the record names.
        """
        keyword = Keyword.objects.create(
            keyword='Flächennutzungsplan WN Remshalden,' * 12 + 'Rudersberg')
        self.dataset.keywords.set([keyword])
        self.assertTrue(self.found_by(self.dataset, 'rudersberg'))
        stored = DatasetMetadataRecord.objects.values_list(
            'keywords_list', flat=True).get(pk=self.dataset.pk)
        self.assertEqual(stored, [keyword.keyword],
                         'the array of the record answers another text than the '
                         'keyword relation of the very same record')

    def test_the_vector_of_a_service_metadata_record_is_built_the_same_way(self):
        self.service_metadata.keywords.set([self.keyword])
        self.assertTrue(self.found_by(self.service_metadata, 'Bodenrichtwerte'))
        self.assertTrue(self.found_by(self.service_metadata, 'wohnen'))

    def test_a_changed_text_replaces_its_words(self):
        DatasetMetadataRecord.objects.filter(pk=self.dataset.pk).update(
            title='Abwasser Hamburg')
        self.assertTrue(self.found_by(self.dataset, 'Abwasser'))
        self.assertFalse(self.found_by(self.dataset, 'Wasserversorgung'))

    def test_a_keyword_written_without_the_orm_reaches_the_vector(self):
        """The chain which makes a harvested record findable is all in the database.

        The keywords of a record are maintained by a trigger and the vector is a
        generated column of it, so a relation written by plain sql - which is how the
        harvesting persists what a document carries - is searchable without anything
        refreshed afterwards.
        """
        with connection.cursor() as cursor:
            cursor.execute(
                f'INSERT INTO {DatasetMetadataRecord.keywords.through._meta.db_table}'
                ' (datasetmetadatarecord_id, keyword_id) VALUES (%s, %s)',
                [self.dataset.pk, self.keyword.pk])
        self.assertTrue(self.found_by(self.dataset, 'wohnen'))

    def test_a_record_without_anything_to_index_answers_an_empty_vector(self):
        """An empty vector is empty and not a null.

        Every text of a record is answered without a value here: a record which was
        only created carries a generated file identifier, and the fragments of it are
        part of the vector like the words of any other text of the record.
        """
        empty = DatasetMetadataRecord.objects.create(
            metadata_contact=self.contact, dataset_contact=self.contact, title='',
            abstract='', file_identifier='', code='', code_space='')
        self.assertIsNotNone(self.vector_of(empty))
        self.assertEqual(self.lexemes_of(empty), [])

    def test_saving_a_record_never_writes_the_column(self):
        """The vector belongs to the database: an instance cannot hand it in."""
        self.dataset.title = 'Abwasser Hamburg'
        self.dataset.search_vector = 'hacked'
        self.dataset.save()
        self.assertFalse(self.found_by(self.dataset, 'hacked'))
        self.assertTrue(self.found_by(self.dataset, 'Abwasser'))


class SearchVectorQueryTest(TestCase, RecordVectorMixin):
    """A record is selected through the column, as a search does it."""

    @classmethod
    def setUpTestData(cls):
        cls.contact = MetadataContact.objects.create(name='Search contact')
        cls.water = DatasetMetadataRecord.objects.create(
            metadata_contact=cls.contact, dataset_contact=cls.contact,
            title='Wasserversorgung Hamburg')
        cls.soil = DatasetMetadataRecord.objects.create(
            metadata_contact=cls.contact, dataset_contact=cls.contact,
            title='Bodenrichtwerte Schleswig-Holstein')
        cls.soil.keywords.set([
            Keyword.objects.create(keyword='Bauen & Wohnen'),
            Keyword.objects.create(keyword='Wasser'),
        ])

    def search(self, value):
        return DatasetMetadataRecord.objects.filter(
            search_vector=SearchQuery(
                value, config=TEXT_CONFIGURATION_NAME)).values_list('id', flat=True)

    def test_a_word_of_the_text_selects_the_record_holding_it(self):
        self.assertEqual(list(self.search('wasserversorgung')), [self.water.pk])

    def test_a_word_of_a_keyword_selects_the_record_tagged_with_it(self):
        self.assertEqual(list(self.search('wasser')), [self.soil.pk])

    def test_a_word_of_a_multi_word_keyword_selects_the_record_tagged_with_it(self):
        """A record is findable by a word which only ever appeared in a keyword."""
        self.assertEqual(list(self.search('wohnen')), [self.soil.pk])

    def test_a_word_no_record_holds_selects_none(self):
        self.assertEqual(list(self.search('bohrung')), [])

    def test_a_word_is_selected_with_the_index_of_the_column(self):
        """The column is only worth having if a search is answered by its index.

        A tsquery is a containment over a tsvector which no btree comparison answers,
        so the index is a GIN index and the planner only chooses it while a sequential
        scan is ruled out.
        """
        table = DatasetMetadataRecord._meta.db_table
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT indexname FROM pg_indexes WHERE tablename = %s"
                " AND indexdef ILIKE %s",
                [table, '%using gin%search_vector%'])
            names = [row[0] for row in cursor.fetchall()]
        self.assertEqual(len(names), 1, f'expected one gin index on {table}')
        with connection.cursor() as cursor:
            cursor.execute('SET LOCAL enable_seqscan = OFF')
            cursor.execute(
                f'EXPLAIN (COSTS OFF) SELECT id FROM {table}'
                " WHERE search_vector @@ plainto_tsquery('english', 'wasser')")
            plan = '\n'.join(row[0] for row in cursor.fetchall())
        self.assertIn(names[0], plan)


class SearchVectorBulkWriteTest(TestCase, RecordVectorMixin):
    """Records written at once are findable at once."""

    @classmethod
    def setUpTestData(cls):
        cls.contact = MetadataContact.objects.create(name='Search contact')

    def test_a_bulk_created_record_is_findable_immediately(self):
        """The write path of an import does not have to rebuild anything.

        An import stores what a document carries with one bulk write; the vector of
        every row is computed by the insert itself, so the records answer a search the
        moment they are stored.
        """
        records = [
            DatasetMetadataRecord(
                metadata_contact=self.contact, dataset_contact=self.contact,
                title=f'Wasserversorgung Hamburg {number}')
            for number in range(3)
        ]
        DatasetMetadataRecord.objects.bulk_create(records)

        found = DatasetMetadataRecord.objects.filter(
            search_vector=SearchQuery(
                'wasserversorgung', config=TEXT_CONFIGURATION_NAME)).count()
        self.assertEqual(found, 3)


class SearchVectorNotHistorizedTest(TestCase):
    """The vector is derived from the record, so it is not a state of its own."""

    def test_the_history_of_a_record_has_no_search_vector(self):
        for model in RECORDS:
            with self.subTest(model=model.__name__):
                fields = {field.name for field in model.change_log.model._meta.get_fields()}
                self.assertNotIn('search_vector', fields)

    def test_the_mapper_does_not_hand_in_the_column(self):
        contact = MetadataContact(name='Search contact')
        instance = DatasetMetadataRecord(
            metadata_contact=contact, dataset_contact=contact, title='Dataset')
        defaults = _defaults_of_instance(instance)
        self.assertNotIn('search_vector', defaults)
        self.assertIn('title', defaults)


class SearchVectorReadCostTest(TestCase):
    """The column is what a search hits, not something an answer reads."""

    def test_the_record_serializers_do_not_answer_the_vector(self):
        for serializer in (DatasetMetadataRecordSerializer, ServiceMetadataRecordSerializer):
            with self.subTest(serializer=serializer.__name__):
                self.assertNotIn('search_vector', serializer().get_fields())

    def test_the_record_endpoints_do_not_read_the_vector(self):
        for mixin in (DatasetMetadataViewSetMixin, ServiceMetadataViewSetMixin):
            with self.subTest(viewset=mixin.__name__):
                deferred, is_deferred = mixin.queryset.query.deferred_loading
                self.assertTrue(is_deferred)
                self.assertIn('search_vector', deferred)

    def test_the_manager_still_answers_the_vector(self):
        """Deferring is a decision of the read path, not of the model.

        The CSW and the MapBender search select a record through the default manager of
        it and match their search against the vector of it (#855); a manager which
        deferred the column would take it out of their statement with it.
        """
        for model in RECORDS:
            with self.subTest(model=model.__name__):
                deferred, is_deferred = model.objects.all().query.deferred_loading
                self.assertFalse(is_deferred and 'search_vector' in deferred)


class SearchableViewsMigrationTest(TransactionTestCase):
    """Going back over the migration which dropped the searchable projections.

    The projections of a record are what a search was answered from before a record
    answered its keywords and its vector as columns of its own; the CSW and the MapBender
    search answer the record tables themselves since #855. A projection is not part of
    the migration state -- django-pgviews creates it from the model, see
    ``system.apps.sync_pg_views_if_missing`` -- and the models which answered it are gone
    from the code, so the hook which creates missing projections cannot help on the way
    back either: the migration carries the statement of both itself, and that statement is
    what this test asks for.

    Rolling further back, below the migration which gave a record its vector, drops both
    projections again -- 0022 answers that -- and nothing creates them anymore, because
    the column they answer is gone with it. That is what a rollback below that revision
    means.
    """

    MIGRATE_BACK_TO = '0022_datasetmetadatarecord_search_vector_and_more'

    VIEWS = ('registry_searchabledatasetmetadatarecord',
             'registry_searchableservicemetadatarecord')

    def view_exists(self, view):
        with connection.cursor() as cursor:
            cursor.execute(
                'SELECT 1 FROM pg_matviews WHERE schemaname = %s AND matviewname = %s',
                ['public', view])
            return bool(cursor.fetchone())

    def migrate(self, *args):
        call_command('migrate', *args, verbosity=0, interactive=False)

    def setUp(self):
        # the way back is only worth something if the projection it creates is the one
        # the code of that revision can read a record out of, so a record is here while
        # the migration answers it
        self.contact = MetadataContact.objects.create(name='Migration contact')
        self.dataset = DatasetMetadataRecord.objects.create(
            metadata_contact=self.contact, dataset_contact=self.contact,
            title='Wasserversorgung Migration')
        self.service = ServiceMetadataRecord.objects.create(
            metadata_contact=self.contact, title='Bodenrichtwerte Migration')
        self.addCleanup(self.migrate)
        for view in self.VIEWS:
            self.assertFalse(self.view_exists(view), f'{view} survived the migration')
        self.migrate('registry', self.MIGRATE_BACK_TO)

    def vector_of(self, record):
        """The vector the record itself answers, which the projection has to answer too."""
        with connection.cursor() as cursor:
            cursor.execute(
                'SELECT "search_vector" FROM ' + record._meta.db_table
                + ' WHERE "id" = %s', [record.pk])
            return cursor.fetchone()[0]

    def hits(self, view, word):
        """The records of a projection a search for a word matches.

        A rolled back deployment searches the projection, so the words of a record have
        to be searchable in it; the word is not compared as text because a tsvector
        holds the stemmed word, which is the whole point of searching a vector.
        """
        with connection.cursor() as cursor:
            cursor.execute(
                'SELECT count(*) FROM ' + view
                + ' WHERE "search_vector" @@ plainto_tsquery(%s, %s)',
                [TEXT_CONFIGURATION_NAME, word])
            return cursor.fetchone()[0]

    def test_the_projection_comes_back_and_answers_the_record_it_projects(self):
        """The statement of the way back is a projection of a record, with its data."""
        for view, record, level in (
                (self.VIEWS[0], self.dataset, 'dataset'),
                (self.VIEWS[1], self.service, 'service')):
            with self.subTest(view=view):
                with connection.cursor() as cursor:
                    cursor.execute(
                        'SELECT "title", "search_vector", "keywords_list",'
                        ' "hierarchy_level" FROM ' + view + ' WHERE "id" = %s',
                        [record.pk])
                    row = cursor.fetchone()
                self.assertIsNotNone(row, f'{record.pk} is not in {view}')
                title, vector, keywords, hierarchy_level = row
                self.assertEqual(title, record.title)
                self.assertEqual(self.vector_of(record), vector,
                                 f'{view} does not answer the vector of the record')
                self.assertEqual(1, self.hits(view, record.title.split()[0]),
                                 f'{view} does not answer a search for its title')
                self.assertEqual([], keywords)
                self.assertEqual(level, hierarchy_level)

    def test_the_projection_is_gone_again_on_the_way_forward(self):
        self.migrate()
        for view in self.VIEWS:
            with self.subTest(view=view):
                self.assertFalse(self.view_exists(view), f'{view} came back for good')
