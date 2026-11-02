"""The keywords of a metadata record as a column which the database maintains.

The array is what allows a searchable representation of a record to be a column of
the record itself, so what matters here is that it is never behind, ahead of or
shaped differently than the keywords relation it stands in for.
"""

from importlib import import_module

from django.db import connection
from django.test import TestCase

from registry.mappers.persistence.custom import _defaults_of_instance
from registry.models.materialized_views import (SearchableDatasetMetadataRecord,
                                                SearchableServiceMetadataRecord)
from registry.models.metadata import (DatasetMetadataRecord, Keyword, MetadataContact,
                                      ServiceMetadataRecord)

keywords_list_migration = import_module(
    'registry.migrations.0021_metadatarecords_keywords_list')


class KeywordsListTest(TestCase):
    """The array of one record follows its keywords relation."""

    @classmethod
    def setUpTestData(cls):
        cls.contact = MetadataContact.objects.create(name='Keywords contact')
        cls.dataset = DatasetMetadataRecord.objects.create(
            metadata_contact=cls.contact, dataset_contact=cls.contact, title='Dataset')
        cls.service_metadata = ServiceMetadataRecord.objects.create(
            metadata_contact=cls.contact, title='Service metadata')
        cls.alpha = Keyword.objects.create(keyword='alpha')
        cls.beta = Keyword.objects.create(keyword='beta')
        cls.gamma = Keyword.objects.create(keyword='gamma')

    def keywords_of(self, record):
        """Reads the column back from the database, not from the instance."""
        return list(
            record.__class__.objects.values_list('keywords_list', flat=True).get(pk=record.pk))

    def test_a_record_without_keywords_holds_an_empty_array(self):
        self.assertEqual(self.keywords_of(self.dataset), [])

    def test_the_array_holds_the_keywords_of_the_record_ordered_by_keyword(self):
        self.dataset.keywords.set([self.gamma, self.alpha])
        self.assertEqual(self.keywords_of(self.dataset), ['alpha', 'gamma'])

        self.dataset.keywords.add(self.beta)
        self.assertEqual(self.keywords_of(self.dataset), ['alpha', 'beta', 'gamma'])

    def test_removing_a_keyword_removes_it_from_the_array(self):
        self.dataset.keywords.set([self.alpha, self.beta])
        self.dataset.keywords.remove(self.alpha)
        self.assertEqual(self.keywords_of(self.dataset), ['beta'])

    def test_replacing_the_keywords_replaces_the_array(self):
        self.dataset.keywords.set([self.alpha, self.beta])
        self.dataset.keywords.set([self.gamma])
        self.assertEqual(self.keywords_of(self.dataset), ['gamma'])

    def test_clearing_the_keywords_empties_the_array(self):
        self.dataset.keywords.set([self.alpha, self.beta])
        self.dataset.keywords.clear()
        self.assertEqual(self.keywords_of(self.dataset), [])

    def test_a_relation_written_without_the_orm_updates_the_array(self):
        """The sync is not a signal, so plain sql keeps the array honest too."""
        with connection.cursor() as cursor:
            cursor.execute(
                f'INSERT INTO {DatasetMetadataRecord.keywords.through._meta.db_table}'
                ' (datasetmetadatarecord_id, keyword_id) VALUES (%s, %s)',
                [self.dataset.pk, self.beta.pk])
        self.assertEqual(self.keywords_of(self.dataset), ['beta'])

    def test_both_record_types_are_maintained(self):
        self.service_metadata.keywords.set([self.beta, self.alpha])
        self.assertEqual(self.keywords_of(self.service_metadata), ['alpha', 'beta'])

    def test_a_renamed_keyword_updates_the_records_holding_it(self):
        self.dataset.keywords.set([self.alpha, self.beta])
        self.service_metadata.keywords.set([self.alpha])

        self.alpha.keyword = 'alpha renamed'
        self.alpha.save()

        self.assertEqual(self.keywords_of(self.dataset), ['alpha renamed', 'beta'])
        self.assertEqual(self.keywords_of(self.service_metadata), ['alpha renamed'])


class KeywordRenameScopeTest(TestCase):
    """A rename only writes the records which hold the keyword."""

    @classmethod
    def setUpTestData(cls):
        cls.contact = MetadataContact.objects.create(name='Keywords contact')
        cls.holding = DatasetMetadataRecord.objects.create(
            metadata_contact=cls.contact, dataset_contact=cls.contact, title='Holding')
        cls.other = DatasetMetadataRecord.objects.create(
            metadata_contact=cls.contact, dataset_contact=cls.contact, title='Other')
        cls.keyword = Keyword.objects.create(keyword='holds me')
        cls.holding.keywords.add(cls.keyword)

    def test_only_the_records_holding_the_renamed_keyword_are_written(self):
        with self.assertNumQueries(1):
            self.keyword.keyword = 'holds me renamed'
            self.keyword.save()
        self.holding.refresh_from_db()
        self.other.refresh_from_db()
        self.assertEqual(self.holding.keywords_list, ['holds me renamed'])
        self.assertEqual(self.other.keywords_list, [])


class BackfillTest(TestCase):
    """The statement which repairs the rows written before the trigger existed."""

    @classmethod
    def setUpTestData(cls):
        cls.contact = MetadataContact.objects.create(name='Keywords contact')
        cls.dataset = DatasetMetadataRecord.objects.create(
            metadata_contact=cls.contact, dataset_contact=cls.contact, title='Dataset')
        cls.service_metadata = ServiceMetadataRecord.objects.create(
            metadata_contact=cls.contact, title='Service metadata')
        cls.keyword = Keyword.objects.create(keyword='alpha')

    def corrupt(self, record):
        with connection.cursor() as cursor:
            cursor.execute(
                f'UPDATE {record._meta.db_table} SET keywords_list = %s WHERE id = %s',
                [['stale'], record.pk])

    def read(self, record):
        return list(record.__class__.objects.values_list('keywords_list', flat=True).get(pk=record.pk))

    def test_the_backfill_repairs_a_record_which_is_behind(self):
        self.dataset.keywords.set([self.keyword])
        self.service_metadata.keywords.set([self.keyword])
        self.corrupt(self.dataset)
        self.corrupt(self.service_metadata)

        with connection.cursor() as cursor:
            cursor.execute(keywords_list_migration.BACKFILL)

        self.assertEqual(self.read(self.dataset), ['alpha'])
        self.assertEqual(self.read(self.service_metadata), ['alpha'])

    def test_the_backfill_answers_the_very_value_the_trigger_writes(self):
        self.dataset.keywords.set([self.keyword])
        before = self.read(self.dataset)
        with connection.cursor() as cursor:
            cursor.execute(keywords_list_migration.BACKFILL)
        self.assertEqual(self.read(self.dataset), before)


class KeywordsListIsNotHistoryTest(TestCase):
    """The array of a record is derived, so history does not copy it."""

    def test_the_history_of_a_record_has_no_keywords_list(self):
        for model in (DatasetMetadataRecord, ServiceMetadataRecord):
            with self.subTest(model=model.__name__):
                history_fields = {
                    field.name for field in model.change_log.model._meta.get_fields()}
                self.assertNotIn('keywords_list', history_fields)


class MappedDefaultsTest(TestCase):
    """A parsed instance never claims to know the value of a maintained column."""

    def test_the_defaults_of_a_parsed_instance_skip_the_maintained_columns(self):
        contact = MetadataContact(name='Keywords contact')
        instance = DatasetMetadataRecord(
            metadata_contact=contact, dataset_contact=contact, title='Dataset')
        defaults = _defaults_of_instance(instance)
        self.assertNotIn('keywords_list', defaults)
        self.assertIn('title', defaults)


class SearchableViewProjectionTest(TestCase):
    """The searchable projections of a record do not answer the maintained column.

    A materialized view is created from the statement of its queryset, and that
    statement is the column list of the record. A view which selects a column of the
    record depends on that column: the record could not drop it anymore without
    dropping the view first, which is what the down revision of the column does. The
    array would also be stored in the view a second time.
    """

    def test_the_statement_of_a_searchable_view_does_not_select_the_column(self):
        for view in (SearchableDatasetMetadataRecord, SearchableServiceMetadataRecord):
            with self.subTest(view=view.__name__):
                self.assertNotIn('keywords_list', view.get_sql())
