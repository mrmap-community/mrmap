"""The keywords of a metadata record as a column which the database maintains.

The array is what allows a searchable representation of a record to be a column of
the record itself, so what matters here is that it is never behind, ahead of or
shaped differently than the keywords relation it stands in for.
"""

from importlib import import_module

from django.core import serializers
from django.db import connection
from django.test import TestCase

from registry.mappers.persistence.custom import _defaults_of_instance
from registry.models.metadata import (ApplicationMetadataRecord,
                                      DatasetMetadataRecord, Keyword,
                                      MetadataContact, ServiceMetadataRecord)

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
        cls.application = ApplicationMetadataRecord.objects.create(
            metadata_contact=cls.contact, application_contact=cls.contact,
            title='Application')
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

    def test_every_record_type_is_maintained(self):
        """One sync trigger per keywords relation, so every record type which
        declares the array is answered by its own -- including the one whose
        trigger a later migration attached (0033)."""
        for record in (self.service_metadata, self.application):
            with self.subTest(record=record.__class__.__name__):
                record.keywords.set([self.beta, self.alpha])
                self.assertEqual(self.keywords_of(record), ['alpha', 'beta'])

    def test_a_renamed_keyword_updates_the_records_holding_it(self):
        """The rename does not pass through a keywords relation, so its fan-out
        names the record tables -- every table which holds the array, not only the
        ones the first migration knew."""
        self.dataset.keywords.set([self.alpha, self.beta])
        self.service_metadata.keywords.set([self.alpha])
        self.application.keywords.set([self.alpha])

        self.alpha.keyword = 'alpha renamed'
        self.alpha.save()

        self.assertEqual(self.keywords_of(self.dataset), ['alpha renamed', 'beta'])
        self.assertEqual(self.keywords_of(self.service_metadata), ['alpha renamed'])
        self.assertEqual(self.keywords_of(self.application), ['alpha renamed'])


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
        for model in (DatasetMetadataRecord, ServiceMetadataRecord,
                      ApplicationMetadataRecord):
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


class WrittenKeywordsListTest(TestCase):
    """A write which never read the array does not answer for its content.

    The array has a default, so an instance which was built instead of loaded -- a
    fixture, a partial document -- carries an empty one, and a full ``UPDATE`` of it
    overwrites what the trigger maintains. The consequence is not a wrong column but a
    record which is no longer findable by its own keywords, because the vector of
    0022 is tokenized out of the array.

    ``loaddata`` is the writer which cannot be guarded from python: it saves what it
    deserialized through ``Model.save_base(raw=True)``, bypassing ``save()``, and a
    fixture never names a column it does not know about. So the guard is a
    ``BEFORE UPDATE`` trigger (0024) and this asks it through the same deserializer.
    """

    @classmethod
    def setUpTestData(cls):
        cls.contact = MetadataContact.objects.create(name='Keywords contact')
        cls.dataset = DatasetMetadataRecord.objects.create(
            metadata_contact=cls.contact, dataset_contact=cls.contact,
            file_identifier='holds a keyword', title='Dataset')
        cls.application = ApplicationMetadataRecord.objects.create(
            metadata_contact=cls.contact, application_contact=cls.contact,
            file_identifier='holds a keyword as well', title='Application')
        cls.keyword = Keyword.objects.create(keyword='alpha')
        cls.dataset.keywords.add(cls.keyword)
        cls.application.keywords.add(cls.keyword)

    #: the fields a fixture of a record has to name for its row to be writable
    FIELDS = ('title', 'file_identifier', 'metadata_contact', 'dataset_contact')

    #: the same for a record type which names its own contact
    APPLICATION_FIELDS = ('title', 'file_identifier', 'metadata_contact',
                          'application_contact')

    def keywords_of(self, record):
        return list(record.__class__.objects.values_list(
            'keywords_list', flat=True).get(pk=record.pk))

    def vector_of(self, record):
        with connection.cursor() as cursor:
            cursor.execute(
                'SELECT "search_vector" FROM ' + record._meta.db_table
                + ' WHERE "id" = %s', [record.pk])
            return cursor.fetchone()[0]

    def save_as_fixture(self, record, fields=FIELDS):
        """What ``loaddata`` writes for a fixture naming some fields of a row.

        Serialize and deserialize instead of a fixture file: the deserialized instance
        is the object whose save loses the array, and naming it here keeps the fields
        which lose it out of a test fixture.
        """
        document = serializers.serialize('json', [record], fields=fields)
        next(serializers.deserialize('json', document)).save()

    def test_a_write_of_an_instance_which_never_read_the_array_keeps_it(self):
        before = self.keywords_of(self.dataset)

        self.save_as_fixture(self.dataset)

        self.assertEqual(before, self.keywords_of(self.dataset))

    def test_a_write_of_an_instance_which_never_read_the_array_keeps_the_vector(self):
        """The keyword is still a word the record is found by."""
        vector = self.vector_of(self.dataset)

        self.save_as_fixture(self.dataset)

        self.assertEqual(vector, self.vector_of(self.dataset))

    def test_a_write_which_names_the_array_is_answered_by_the_relation(self):
        """The column belongs to the database, so no writer owns its value."""
        record = DatasetMetadataRecord.objects.get(pk=self.dataset.pk)
        record.keywords_list = ['written by hand']

        record.save()

        self.assertEqual(self.keywords_of(self.dataset), ['alpha'])

    def test_a_write_of_an_application_record_which_never_read_the_array_keeps_it(self):
        """The guard is one trigger per record table, so the table which arrived
        after 0024 needs its own -- the second half of the migration which added
        the record type."""
        before = self.keywords_of(self.application)

        self.save_as_fixture(self.application, self.APPLICATION_FIELDS)

        self.assertEqual(before, self.keywords_of(self.application))


class PgtriggerOwnershipTest(TestCase):
    """After the transfer of 0035 the package owns the maintenance objects.

    The point of #1009 is that every keyword rule is exactly one trigger which
    the migrations of pgtrigger know. Both halves are asked here: that nothing
    of the hand written legacy objects survives, and that no rule is installed
    twice -- a duplicated keep trigger would answer a write twice and a
    duplicated sync trigger would pay for the aggregate twice on every harvest
    write.
    """

    def catalog(self, predicate):
        with connection.cursor() as cursor:
            cursor.execute(
                'SELECT tgname FROM pg_trigger t JOIN pg_class c ON c.oid = t.tgrelid'
                ' WHERE NOT tgisinternal AND ' + predicate + ' ORDER BY tgname')
            return [row[0] for row in cursor.fetchall()]

    def test_the_maintenance_triggers_are_the_objects_of_the_package(self):
        own = self.catalog(
            "(tgname LIKE 'pgtrigger\\_%' AND (tgname LIKE '%\\_keywords\\_list\\_%'"
            " OR tgname LIKE '%\\_metadatarecords%'))"
            " OR (tgname NOT LIKE 'pgtrigger\\_%' AND (tgname LIKE '%keywords\\_list%'"
            " OR tgname = 'registry_keyword_sync_to_metadatarecords'))")
        self.assertEqual(len(own), 7, own)
        self.assertTrue(all(name.startswith('pgtrigger_') for name in own), own)

    def test_the_legacy_functions_are_gone(self):
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT proname FROM pg_proc WHERE proname IN ("
                "'registry_sync_metadatarecord_keywords_list',"
                "'registry_keep_metadatarecord_keywords_list',"
                "'registry_sync_keyword_rename_to_metadatarecords')")
            self.assertEqual([row[0] for row in cursor.fetchall()], [])

    def test_every_rule_is_installed_exactly_once(self):
        """One function per trigger, no orphans of earlier installs."""
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT count(*) FROM pg_proc WHERE proname LIKE 'pgtrigger\\_%'"
                " AND (proname LIKE '%keywords\\_list%' OR proname LIKE '%metadatarecords%')")
            self.assertEqual(cursor.fetchone()[0], 7)
