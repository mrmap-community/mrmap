"""The duplicated delivery of one harvest answers the import task (#1039).

A live catalogue served two of its records a second time within one run. Each
delivery took the DUPLICATED branch of `md_metadata_file_to_db`, which at the
time answered a bare (record, updated, existed) tuple as the whole return value
of the method. The import task iterates what the model answers, so the first
element it saw was the record instance itself and `result[0]` raised
`TypeError: '<Record>' object is not subscriptable`. That error rolled back the
"duplicated" diagnosis the model had just saved - and the DUPLICATED relation
with it - and the task's handler overwrote the diagnosis with the traceback,
leaving the owner of the catalogue a boolean alert naming an internal type
error.

This module is the contract of the fixed shape, for the two record types whose
rows the crash hit:

* a duplicated delivery answers one (record, updated, existed) row in the shape
  the task consumes it, the diagnosis and the DUPLICATED relation survive the
  import, and no traceback reaches the file;
* a file carrying more than one instance and booked as a duplicate on a later
  one keeps the rows of the instances imported before the duplicate in the
  answer - discarding them was the second damage of the bare return.
"""

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.core.files.base import ContentFile
from django.test import TestCase, override_settings

from registry.enums.harvesting import CollectingStatenEnum as State
from registry.enums.harvesting import HarvestingPhaseEnum as Phase
from registry.mappers.factory import MDMetadataXmlMapper
from registry.models.harvest import (HarvestedMetadataRelation, HarvestingJob,
                                     TemporaryMdMetadataFile)
from registry.models.metadata import (DatasetMetadataRecord,
                                      ServiceMetadataRecord)
from registry.tasks.harvest import import_md_metadata_file

ISO_DATA = Path(__file__).parent / '../../test_data/iso_metadata'
DATASET = ISO_DATA / 'dataset.xml'
SERVICE = ISO_DATA / 'service.xml'


class DuplicatedDeliveryHarness:
    """A run, a stored document and its import, the way the harvest task does.

    The documents are the ISO samples of the test data, stored the way the
    harvesting stores a downloaded record, and they are imported by the
    function the import task calls. No catalogue stands behind the run: the
    shape of the import answer does not depend on the service, and the crash
    of #1039 hit the two record types this harness imports.
    """

    def setUp(self):
        media = TemporaryDirectory()
        self.addCleanup(media.cleanup)
        settings = override_settings(MEDIA_ROOT=media.name)
        settings.enable()
        self.addCleanup(settings.disable)

    def new_run(self):
        """A harvesting run which is about to write its records to the database."""
        job = HarvestingJob(total_records=1, phase=Phase.RECORDS_TO_DB)
        HarvestingJob.objects.bulk_create([job])
        return job

    def stored_file(self, run, document):
        """The document of a run, stored and waiting for the import."""
        file = TemporaryMdMetadataFile(
            job=run, requested_url='https://example.com/csw?page=1')
        file.md_metadata_file.save(
            Path(document).name, ContentFile(Path(document).read_bytes()), save=False)
        TemporaryMdMetadataFile.objects.bulk_create([file])
        return file

    def import_document(self, run, document):
        """Store one document of the run and import it through the task.

        Returns:
            tuple: what the task answered and the stored file it imported
        """
        file = self.stored_file(run, document)
        return import_md_metadata_file(file.pk), file


class DuplicatedDeliveryAnswerTest(DuplicatedDeliveryHarness, TestCase):
    """A further delivery of a record the run already booked stays answerable."""

    def assert_duplicated_delivery_answers(self, document, record_model, record_field):
        """The crash of #1039, run to the end through the import task.

        The run books the first delivery as new and the second as existing; the
        third delivery recomputes existing, collides with the unique state of
        the run and takes the DUPLICATED branch - the very path whose bare
        tuple the task iterated as a list of rows.
        """
        run = self.new_run()
        self.import_document(run, document)  # NEW
        self.import_document(run, document)  # EXISTING
        results, file = self.import_document(run, document)  # DUPLICATED

        record = record_model.objects.get()
        self.assertEqual(
            [(pk, existed) for pk, _updated, existed in results],
            [(str(record.pk), True)],
            'the duplicated delivery answers its row to the task in the shape '
            'the task consumes it')

        self.assertTrue(HarvestedMetadataRelation.objects.filter(
            harvesting_job=run, **{record_field: record},
            collecting_state=State.DUPLICATED.value).exists(),
            'the DUPLICATED relation of the delivery survives the import')

        flagged = TemporaryMdMetadataFile.objects.get(pk=file.pk)
        self.assertTrue(flagged.has_import_error)
        self.assertIn('duplicated', flagged.import_error)
        self.assertIn(str(record.pk), flagged.import_error,
                      'the diagnosis names the matching record it duplicates')
        self.assertNotIn('subscriptable', flagged.import_error)
        self.assertNotIn('Traceback', flagged.import_error,
                         'no internal type error overwrites the diagnosis')

    def test_a_duplicated_dataset_delivery_answers_and_keeps_its_diagnosis(self):
        self.assert_duplicated_delivery_answers(
            DATASET, DatasetMetadataRecord, 'dataset_metadata_record')

    def test_a_duplicated_service_delivery_answers_and_keeps_its_diagnosis(self):
        self.assert_duplicated_delivery_answers(
            SERVICE, ServiceMetadataRecord, 'service_metadata_record')


class MultiInstanceDuplicatedAnswerTest(DuplicatedDeliveryHarness, TestCase):
    """A file booked as a duplicate on a later instance keeps its earlier rows.

    Catalogues deliver one record per stored file, which is how #1039 was
    reached. The return contract belongs to the whole file nevertheless: a file
    whose second instance the run books as a duplicate still answers the row of
    the instance imported before it - everything collected in `result` was
    discarded with the bare return. The second instance is delivered here by
    answering the mapped record twice for the file, which is the shape a
    multi-instance document imports as.
    """

    def test_the_rows_before_the_duplicate_stay_in_the_answer(self):
        run = self.new_run()
        self.import_document(run, DATASET)  # the record exists, NEW is booked

        real_xml_to_django = MDMetadataXmlMapper.xml_to_django

        def doubled(self):
            """the real mapping, answering its one instance twice for the file"""
            return list(real_xml_to_django(self)) * 2

        with patch.object(MDMetadataXmlMapper, 'xml_to_django', doubled):
            results, _file = self.import_document(run, DATASET)

        record = DatasetMetadataRecord.objects.get()
        self.assertEqual(
            [(pk, existed) for pk, _updated, existed in results],
            [(str(record.pk), True), (str(record.pk), True)],
            'the instance imported before the duplicate is answered too')

        self.assertEqual(
            list(HarvestedMetadataRelation.objects.filter(
                harvesting_job=run, dataset_metadata_record=record
            ).order_by('id').values_list('collecting_state', flat=True)),
            [State.NEW.value, State.EXISTING.value, State.DUPLICATED.value])
        self.assertTrue(TemporaryMdMetadataFile.objects.filter(
            job=run, has_import_error=True,
            import_error__contains='duplicated').exists(),
            'the file of the duplicate is kept for inspection')
