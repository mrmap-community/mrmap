"""What importing one metadata record costs the database (mrmap#858).

Importing a harvested record used to write its row up to three times: the values
of the document, then the name of its xml backup, and - when the run came from a
catalogue - one more update of the newest history row to name that service. During
the import of 96,000 records that is what kept the writers waiting on WAL (#837).

Since then one imported record is written once, which these tests are the
contract of:

* a record no row carries yet costs one INSERT of the record and one of its
  history row,
* a record the catalogue did not change is not written at all,
* a record the catalogue republished costs one UPDATE and one history row,
* the xml backup of the document is stored with the record and readable, and a
  document which cannot be stored leaves no record behind,
* a harvest does not mark a record as customized, an editor does,
* the history row names the run which wrote it, in the same words as before.
"""

import re
from collections import Counter
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.core.files.base import ContentFile
from django.db import connection
from django.db.models import F
from django.test import TestCase, TransactionTestCase, override_settings
from django.test.utils import CaptureQueriesContext
from lxml import etree
from registry.enums.harvesting import CollectingStatenEnum as State
from registry.enums.harvesting import HarvestingPhaseEnum as Phase
from registry.mappers.factory import MDMetadataXmlMapper
from registry.mappers.persistence.custom import _save_record
from registry.mappers.persistence.handler import PersistenceHandler
from registry.models.harvest import (HarvestedMetadataRelation, HarvestingJob,
                                     TemporaryMdMetadataFile)
from registry.models.metadata import DatasetMetadataRecord
from registry.models.service import CatalogueService

# the ISO record which is imported here
DATASET = Path(__file__).parent / '../../test_data/iso_metadata/dataset.xml'

# a statement which writes: INSERT INTO "<table>" / UPDATE "<table>" SET /
# DELETE FROM "<table>". Reading is not what #858 is about.
WRITE = re.compile(
    r'^\s*(INSERT|UPDATE|DELETE)\s+(INTO\s+|FROM\s+)?"?(?P<table>\w+)"?',
    re.IGNORECASE)


def written_tables(queries):
    """How often a captured run of queries wrote each table.

    Args:
        queries: the captured queries of a CaptureQueriesContext

    Returns:
        collections.Counter: the number of writing statements per table
    """
    return Counter(
        match.group('table').lower()
        for match in (WRITE.match(query['sql']) for query in queries)
        if match)


class ImportHarness:
    """A stored metadata file of a harvesting run, imported the way the task does.

    Nothing is mocked: the document is the ISO record of the test data, it is
    stored like a downloaded record and it is imported by the code which the
    import task calls. Only the page download of a run is missing, because it is
    not part of writing an imported record.
    """

    def setUp(self):
        media = TemporaryDirectory()
        self.addCleanup(media.cleanup)
        settings = override_settings(MEDIA_ROOT=media.name)
        settings.enable()
        self.addCleanup(settings.disable)
        self.document = DATASET.read_bytes()
        self.record_table = DatasetMetadataRecord._meta.db_table
        self.history_table = DatasetMetadataRecord.change_log.model._meta.db_table

    def new_run(self, service=None):
        """A harvesting run which is about to write its records to the database."""
        job = HarvestingJob(total_records=1, phase=Phase.RECORDS_TO_DB, service=service)
        HarvestingJob.objects.bulk_create([job])
        return job

    def stored_file(self, run):
        """The document of a run, stored and waiting for the import.

        Created the way the harvesting stores a downloaded record, without
        publishing the task which imports it.
        """
        file = TemporaryMdMetadataFile(job=run)
        file.md_metadata_file.save('dataset.xml', ContentFile(self.document), save=False)
        TemporaryMdMetadataFile.objects.bulk_create([file])
        return file

    def import_document(self, run):
        """Imports the stored document of a run and answers what it did.

        Returns:
            tuple: the imported record, whether it was updated, whether it already
                existed - as the import task reports it
        """
        return self.stored_file(run).md_metadata_file_to_db()[0]

    def republish(self, record):
        """Makes the stored record older than the document which is imported next.

        A catalogue which republishes a record answers a newer date stamp, and the
        next harvest of that document is what the stored row has to catch up with.
        """
        DatasetMetadataRecord.objects.filter(pk=record.pk).update(
            date_stamp=F('date_stamp') - timedelta(days=1))

    def assertWrites(self, work, **tables):
        """Asserts how often a call writes the tables an imported record is made of.

        Which other tables an import fills with the rows of its document - the
        contacts, the keywords, the bookkeeping of the run - is not what #858
        changed and is therefore not asked here. The row of the record and its
        history row are, and they are asserted even when they are not named: a
        record which is not written is the point of the whole issue.

        Args:
            work: the callable to run
            **tables: the number of writing statements expected per table

        Returns: whatever the callable returned
        """
        expected = {table.lower(): count for table, count in tables.items()}
        expected.setdefault(self.record_table, 0)
        expected.setdefault(self.history_table, 0)
        with CaptureQueriesContext(connection) as context:
            result = work()
        written = written_tables(context.captured_queries)
        for table, count in expected.items():
            self.assertEqual(written[table], count, (
                f'{table} was written {written[table]} times, expected {count}, '
                f'by: {context.captured_queries}'))
        return result


class ImportedRecordWriteCountTest(ImportHarness, TestCase):
    """How often the row of a record is written by an import."""

    def setUp(self):
        super().setUp()
        self.run = self.new_run()

    def record(self):
        return DatasetMetadataRecord.objects.get()

    def test_a_new_record_is_written_once(self):
        """one INSERT of its row and one INSERT of its history row (#858)"""
        imported, updated, existed = self.assertWrites(
            lambda: self.import_document(self.run),
            **{self.record_table: 1, self.history_table: 1})

        self.assertFalse(updated)
        self.assertFalse(existed)
        self.assertEqual(DatasetMetadataRecord.objects.count(), 1)
        self.assertEqual(imported.change_logs.count(), 1)

    def test_a_new_record_carries_the_key_of_the_parsed_instance(self):
        """the relations of a document are set on the parsed instance, so the row
        which is written for a new record has to carry that instance's key"""
        mapper = MDMetadataXmlMapper.from_xml(self.document)[0]
        parsed = mapper.xml_to_django()[0]

        PersistenceHandler(mapper).persist_all()

        self.assertEqual(DatasetMetadataRecord.objects.get().pk, parsed.pk)

    def test_a_record_a_concurrent_import_inserted_first_is_the_one_which_answers(self):
        """two imports of one file identifier run side by side: the row which was
        first must not break the transaction of the other, and from then on it is
        the row which is written - which is what get_or_create returned as well"""
        self.import_document(self.run)
        stored = self.record()
        run = self.new_run()
        file = self.stored_file(run)
        lookups = [None, stored]

        with patch('registry.mappers.persistence.custom._record_of', side_effect=lookups):
            imported, updated, existed = file.md_metadata_file_to_db()[0]

        self.assertEqual(imported.pk, stored.pk)
        self.assertFalse(updated)
        self.assertTrue(existed)
        self.assertEqual(DatasetMetadataRecord.objects.count(), 1)
        self.assertEqual(
            HarvestedMetadataRelation.objects.filter(harvesting_job=run)
            .latest('id').collecting_state, State.EXISTING,
            'the import which lost the race still imports the record')

    def test_an_unchanged_record_is_not_written_at_all(self):
        """the catalogue answered the same record again: nothing of it is newer,
        so its row is left alone - not even its xml backup is rewritten"""
        self.import_document(self.run)
        record = self.record()
        stored_history = record.change_logs.count()
        stored_backup = record.xml_backup_file.name

        imported, updated, existed = self.assertWrites(
            lambda: self.import_document(self.new_run()))

        self.assertFalse(updated)
        self.assertTrue(existed)
        record.refresh_from_db()
        self.assertEqual(record.change_logs.count(), stored_history)
        self.assertEqual(record.xml_backup_file.name, stored_backup)
        self.assertEqual(
            record.harvested_dataset_metadata_relations.latest('id').collecting_state,
            State.EXISTING)

    def test_a_newer_record_is_written_once(self):
        """one UPDATE of its row and one INSERT of its history row (#858)"""
        self.import_document(self.run)
        self.republish(self.record())

        imported, updated, existed = self.assertWrites(
            lambda: self.import_document(self.new_run()),
            **{self.record_table: 1, self.history_table: 1})

        self.assertTrue(updated)
        self.assertTrue(existed)
        self.assertEqual(self.record().change_logs.count(), 2)
        self.assertEqual(
            self.record().harvested_dataset_metadata_relations.latest('id').collecting_state,
            State.UPDATED)

    def test_writing_a_record_is_two_statements(self):
        """the write of the persistence handler is the UPDATE of the row and the
        INSERT of the history row; the xml backup travels with the first of them"""
        self.import_document(self.run)
        record = self.record()
        stored_backup = record.xml_backup_file.name

        with self.assertNumQueries(2):
            _save_record(record, '<xml/>', 'fileimport')

        record.refresh_from_db()
        self.assertNotEqual(record.xml_backup_file.name, stored_backup)

    def test_the_backup_of_the_document_is_stored_and_readable(self):
        self.import_document(self.run)
        record = self.record()

        self.assertTrue(record.xml_backup_file.name.endswith(
            f'xml_documents/{record.pk}/md_metadata.xml'),
            f'the backup of a record is stored below the record: {record.xml_backup_file.name}')
        with record.xml_backup_file.open('rb') as stored:
            document = etree.fromstring(stored.read())
        self.assertEqual(
            record.file_identifier,
            document.xpath('//*[local-name()="fileIdentifier"]/*/text()')[0])
        self.assertIn(b'MD_Metadata', record.xml_backup[:200])

    def test_a_document_which_cannot_be_stored_leaves_no_record_behind(self):
        """the document is stored within the transaction of the import on purpose:
        a record must not point at a file which never arrived, and the run has to
        say that this record could not be imported"""
        file = self.stored_file(self.run)

        with patch('django.core.files.storage.FileSystemStorage._save',
                   side_effect=OSError('no space left on device')):
            with self.assertRaises(OSError):
                file.md_metadata_file_to_db()

        self.assertEqual(DatasetMetadataRecord.objects.count(), 0)
        self.assertTrue(file.has_import_error)
        self.assertIn('no space left on device', file.import_error)

    def test_a_record_a_run_already_booked_stays_a_duplicate(self):
        """the bookkeeping of a run is not part of the write path: a catalogue
        which answers one record in several pages of the same run is booked as
        new, as existing and from the third page on as a duplicate"""
        self.import_document(self.run)
        self.import_document(self.run)
        file = self.stored_file(self.run)

        record, updated, existed = file.md_metadata_file_to_db()

        self.assertTrue(existed)
        self.assertFalse(updated)
        self.assertEqual(
            list(HarvestedMetadataRelation.objects.filter(harvesting_job=self.run)
                 .order_by('id').values_list('collecting_state', flat=True)),
            [State.NEW.value, State.EXISTING.value, State.DUPLICATED.value])
        self.assertTrue(TemporaryMdMetadataFile.objects.filter(pk=file.pk).exists())


class ImportedRecordHistoryTest(ImportHarness, TestCase):
    """What the history row of an imported record says about the write."""

    def setUp(self):
        super().setUp()
        self.run = self.new_run()

    def record(self):
        return DatasetMetadataRecord.objects.get()

    def last_change(self, record=None):
        """The history row which the last write of the record left behind."""
        return (record or self.record()).change_logs.order_by('history_date').last()

    def test_a_run_without_a_catalogue_names_the_file_import_as_its_reason(self):
        """the reason is written with the history row instead of updating that row
        afterwards, and an administrator reads the same words as before"""
        self.import_document(self.run)

        self.assertEqual(self.last_change().history_change_reason, 'fileimport')

    def test_a_harvest_update_does_not_mark_the_record_as_customized(self):
        """the flag answers whether an editor changed the record; a run which
        re-harvests it says nothing about that answer (#858)"""
        self.import_document(self.run)
        self.republish(self.record())

        self.import_document(self.new_run())

        self.assertFalse(self.record().is_customized)

    def test_an_editor_change_marks_the_record_as_customized(self):
        self.import_document(self.run)
        record = self.record()

        record.title = 'What the editor makes of it'
        record.save()

        self.assertTrue(self.record().is_customized)

    def test_a_harvest_update_keeps_a_customized_record_customized(self):
        """the document says nothing about the flag, so a harvest may neither set
        it nor reset it - the answer of the editor is the only one there is"""
        self.import_document(self.run)
        record = self.record()
        record.title = 'What the editor makes of it'
        record.save()
        self.republish(record)

        self.import_document(self.new_run())

        self.assertTrue(self.record().is_customized)


class CatalogueRunHistoryTest(ImportHarness, TestCase):
    """The history row of a record which a run of a catalogue imported.

    The catalogue behind such a run needs to know its own capabilities document,
    because the import asks the service for the url a record was downloaded from.
    One of the fixture catalogues is used which has no run of its own yet, so the
    run of this test may be the unfinished run of that service.
    """

    fixtures = ['test_users.json', 'test_keywords.json', 'test_csw.json']

    CSW_1 = '9cc4889d-0cd4-4c3b-8975-58de6d30db41'
    CAPABILITIES = Path(__file__).parent / '../../test_data/capabilities/csw/2.0.2.xml'

    def setUp(self):
        super().setUp()
        self.service = CatalogueService.objects.get(pk=self.CSW_1)
        self.service.xml_backup_file = ContentFile(
            self.CAPABILITIES.read_bytes(), name='capabilities.xml')
        self.service.save()

    def test_the_history_row_names_the_catalogue_which_was_harvested(self):
        run = self.new_run(service=self.service)

        self.import_document(run)

        change = DatasetMetadataRecord.objects.get(
        ).change_logs.order_by('history_date').last()
        self.assertEqual(change.history_change_reason, f'csw:{self.service}')


class ImportRowWriteStatsTest(ImportHarness, TransactionTestCase):
    """The write counters the database reports for an imported record.

    `pg_stat_user_tables` counts what arrives at a table, which is what the WAL of
    a 96,000 record import is made of. These counters are the counters of
    committed work, so the imports of this test really commit.
    """

    def counters(self, table):
        """How often the database wrote a table, flushed so that committed work is
        counted by the time it is asked for."""
        with connection.cursor() as cursor:
            cursor.execute('SELECT pg_stat_force_next_flush()')
            cursor.execute(
                'SELECT coalesce(n_tup_ins, 0), coalesce(n_tup_upd, 0) '
                'FROM pg_stat_user_tables WHERE relname = %s', [table])
            return cursor.fetchone()

    def delta(self, table, before):
        return tuple(after - was for after, was in zip(self.counters(table), before))

    def test_a_new_record_arrives_as_one_tuple_in_the_record_and_one_in_its_history(self):
        """the import writes the record once: one tuple in its table, one in the
        history table, and no update of either.

        The update counter of the record moves with the INSERT all the same: the
        keywords of the document are rows of a relation, and the trigger which
        keeps the denormalized `keywords_list` of the record in sync (#853)
        rewrites the record once per keyword row it is given. Those writes belong
        to that column and not to the import - which is why the counter is
        compared with the keywords of the record and not with zero.
        """
        before = (self.counters(self.record_table), self.counters(self.history_table))

        self.import_document(self.new_run())

        record = DatasetMetadataRecord.objects.get()
        self.assertEqual(self.delta(self.record_table, before[0]),
                         (1, record.keywords.count()))
        self.assertEqual(self.delta(self.history_table, before[1]), (1, 0))

    def test_an_unchanged_record_arrives_as_nothing(self):
        """the counters do not move at all: the row, its history and its keyword
        relation are left as they are, because nothing of the document is newer"""
        self.import_document(self.new_run())
        before = (self.counters(self.record_table), self.counters(self.history_table))

        self.import_document(self.new_run())

        self.assertEqual(self.delta(self.record_table, before[0]), (0, 0))
        self.assertEqual(self.delta(self.history_table, before[1]), (0, 0))

    def test_a_newer_record_arrives_as_one_update_and_one_history_row(self):
        """one UPDATE of the record and one tuple in its history - and, unlike
        before #858, no second update of the record for the xml backup and no
        update of the history row to name the run"""
        self.import_document(self.new_run())
        self.republish(DatasetMetadataRecord.objects.get())
        before = (self.counters(self.record_table), self.counters(self.history_table))

        self.import_document(self.new_run())

        self.assertEqual(self.delta(self.record_table, before[0]), (0, 1))
        self.assertEqual(self.delta(self.history_table, before[1]), (1, 0))
