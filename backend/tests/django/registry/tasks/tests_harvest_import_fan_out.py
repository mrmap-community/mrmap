"""The import of stored metadata files is bounded by chunks, not by records (#859).

A harvest used to publish one `call_md_metadata_file_to_db` task per record: 70,000 records
meant 70,000 broker messages, task round-trips and result writes, while the database was the
only thing that had to keep up. The tasks are chunked now; what must not change is the
idempotency of a record, the error of a single record and the progress the harvest reports.
"""
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from django.core.files.base import ContentFile
from django.test import TestCase, override_settings
from notify.models import BackgroundProcess
from registry.enums.harvesting import HarvestingPhaseEnum as Phase
from registry.models.harvest import HarvestingJob, TemporaryMdMetadataFile
from registry.tasks.harvest import (call_chord_md_metadata_file_to_db,
                                    call_md_metadata_files_to_db,
                                    iter_md_metadata_file_chunks)

# the fan-out hands this to the tasks instead of asking the job for it, which would
# want the admin user of the deployment to build it
HTTP_REQUEST = {"path": "somepath", "method": "GET",
                "content_type": "application/json", "data": {}, "user_pk": None}


def imports_a_record(record):
    """what `md_metadata_file_to_db` answers for a record: the instance of the metadata record it
    wrote, whether it was updated and whether it was newly created, and it deletes the stored file
    of itself -> the answer must survive that deletion, so it is not the stored row"""
    imported = SimpleNamespace(pk=record.pk)
    record.delete()
    return [(imported, False, False)]


class MetadataFileChunkTest(TestCase):
    """how the ids of stored files are split into the work of a single task"""

    def test_chunks_of_a_batch_size(self):
        with self.subTest(batch_size=2):
            self.assertEqual([[1, 2], [3]],
                             list(iter_md_metadata_file_chunks([1, 2, 3], batch_size=2)))
        with self.subTest(batch_size=3):
            self.assertEqual([[1, 2, 3]],
                             list(iter_md_metadata_file_chunks([1, 2, 3], batch_size=3)))
        with self.subTest(batch_size=4):
            self.assertEqual([[1, 2, 3]], list(iter_md_metadata_file_chunks(
                (pk for pk in [1, 2, 3]), batch_size=4)))

    def test_nothing_to_import_is_no_chunk(self):
        self.assertEqual([], list(iter_md_metadata_file_chunks([])))

    def test_the_setting_answers_the_batch_size(self):
        with override_settings(HARVEST_IMPORT_BATCH_SIZE=2):
            self.assertEqual([[1, 2], [3, 4]], list(iter_md_metadata_file_chunks([1, 2, 3, 4])))

    def test_a_batch_size_below_one_imports_one_record_per_task(self):
        # a misconfiguration must not become an endless loop over the same id
        with override_settings(HARVEST_IMPORT_BATCH_SIZE=0):
            self.assertEqual([[1], [2]], list(iter_md_metadata_file_chunks([1, 2])))


class StoredFilesTestCaseMixin:
    """stored metadata files below a temporary media root"""

    def setUp(self):
        super().setUp()
        self.media = TemporaryDirectory()
        self.addCleanup(self.media.cleanup)
        self.media_root = override_settings(MEDIA_ROOT=self.media.name)
        self.media_root.enable()
        self.addCleanup(self.media_root.disable)

    def _job(self, total_records, phase=Phase.RECORDS_TO_DB):
        return HarvestingJob.objects.create(total_records=total_records, phase=phase)

    def _store(self, job, name, content=b'<record/>'):
        stored = TemporaryMdMetadataFile(job=job)
        stored.md_metadata_file.save(name, ContentFile(content), save=False)
        TemporaryMdMetadataFile.objects.bulk_create([stored])
        return stored

    def _store_many(self, job, count):
        files = []
        for number in range(count):
            stored = TemporaryMdMetadataFile(job=job)
            stored.md_metadata_file.save(
                f'record_{number}.xml', ContentFile(b'<record/>'), save=False)
            files.append(stored)
        return list(TemporaryMdMetadataFile.objects.bulk_create(files))


class HarvestImportFanOutTest(StoredFilesTestCaseMixin, TestCase):
    """the harvest publishes one import task per chunk and still reports steps per record"""

    def _fan_out(self, job):
        with self.captureOnCommitCallbacks(execute=True):
            call_chord_md_metadata_file_to_db.run(harvesting_job_id=job.pk,
                                                  http_request=HTTP_REQUEST)

    @patch('registry.tasks.harvest.chord')
    def test_stored_files_publish_one_task_per_chunk(self, mocked_chord):
        job = self._job(2500)
        stored = self._store_many(job, 2500)
        with override_settings(HARVEST_IMPORT_BATCH_SIZE=1000):
            self._fan_out(job)

        header, callback = mocked_chord.call_args.args
        self.assertEqual(3, len(header), 'ceil(2500 / 1000) chunks are expected')
        self.assertEqual([1000, 1000, 500],
                         [len(task.kwargs['md_metadata_file_ids']) for task in header])
        chunked = [pk for task in header for pk in task.kwargs['md_metadata_file_ids']]
        self.assertEqual(sorted(file.pk for file in stored), sorted(chunked),
                         'every stored file must sit in exactly one chunk')
        self.assertTrue(all(task.kwargs['harvesting_job_id'] == job.pk for task in header),
                        'a chunk has to name its job, that is how it ends a failing harvest')

        # an abort revokes by task id, so it needs the id of every chunk
        job.refresh_from_db()
        self.assertEqual([str(task.options['task_id']) for task in header]
                         + [str(callback.options['task_id'])],
                         [str(task_id) for task_id in job.celery_task_ids])

    @patch('registry.tasks.harvest.chord')
    def test_the_chunks_are_named_by_the_task_they_run(self, mocked_chord):
        job = self._job(1)
        self._store_many(job, 1)
        self._fan_out(job)

        header, callback = mocked_chord.call_args.args
        self.assertEqual(1, len(header))
        self.assertEqual('registry.tasks.harvest.call_md_metadata_files_to_db', header[0].name)
        self.assertEqual('registry.tasks.harvest.finish_harvesting_job', callback.name)

    @patch('registry.tasks.harvest.chord')
    def test_the_reported_steps_stay_granular_by_record(self, mocked_chord):
        job = self._job(7)
        self._store_many(job, 7)
        with override_settings(HARVEST_IMPORT_BATCH_SIZE=3):
            self._fan_out(job)

        header, _ = mocked_chord.call_args.args
        self.assertEqual(3, len(header))
        process = BackgroundProcess.objects.get(pk=job.background_process_id)
        self.assertEqual(8, process.total_steps,
                         'the progress is made of records, bounding the tasks must not move it')

    @patch('registry.tasks.harvest.chord')
    def test_without_stored_files_the_harvest_completes_without_a_task(self, mocked_chord):
        job = self._job(1, phase=Phase.DOWNLOAD_RECORDS)
        self._fan_out(job)

        mocked_chord.assert_not_called()
        job.refresh_from_db()
        self.assertEqual(Phase.COMPLETED, job.phase)
        self.assertIsNotNone(job.done_at)


class ChunkImportTest(StoredFilesTestCaseMixin, TestCase):
    """what a chunk task does with the records it was given"""

    def setUp(self):
        super().setUp()
        self.job = self._job(3)

    def test_a_broken_record_does_not_fail_the_chunk_it_sits_in(self):
        first = self._store(self.job, 'first.xml')
        second = self._store(self.job, 'second.xml')
        broken = self._store(self.job, 'broken.xml')

        def import_file(record):
            if record.pk == broken.pk:
                raise ValueError('invalid metadata')
            return imports_a_record(record)

        with patch.object(TemporaryMdMetadataFile, 'md_metadata_file_to_db', import_file):
            results = call_md_metadata_files_to_db.run(
                md_metadata_file_ids=[broken.pk, first.pk, second.pk],
                harvesting_job_id=self.job.pk)

        broken.refresh_from_db()
        self.assertTrue(broken.has_import_error)
        self.assertIn('invalid metadata', broken.import_error)
        self.assertTrue(TemporaryMdMetadataFile.objects.filter(pk=broken.pk).exists(),
                        'a broken record stays for inspection')
        for stored in (first, second):
            self.assertFalse(TemporaryMdMetadataFile.objects.filter(pk=stored.pk).exists(),
                             'an imported record deletes the stored file of it')
        self.assertEqual([(str(stored.pk), False, False) for stored in (first, second)], results)

    def test_a_record_which_is_gone_is_skipped(self):
        stored = self._store(self.job, 'first.xml')
        attempts = []

        def import_file(record):
            attempts.append(record.pk)
            return imports_a_record(record)

        with patch.object(TemporaryMdMetadataFile, 'md_metadata_file_to_db', import_file):
            # the retry of a chunk works its ids again: what is committed is gone
            results = call_md_metadata_files_to_db.run(
                md_metadata_file_ids=[stored.pk] * 3, harvesting_job_id=self.job.pk)

        self.assertEqual([stored.pk], attempts,
                         'a chunk does not import the same id again after it committed it')
        self.assertEqual([(str(stored.pk), False, False)], results)

    def test_a_flagged_record_is_not_imported_again(self):
        broken = self._store(self.job, 'broken.xml')
        attempts = []

        def fail(record):
            attempts.append(record.pk)
            raise ValueError('invalid metadata')

        with patch.object(TemporaryMdMetadataFile, 'md_metadata_file_to_db', fail):
            call_md_metadata_files_to_db.run(md_metadata_file_ids=[broken.pk],
                                             harvesting_job_id=self.job.pk)
            call_md_metadata_files_to_db.run(md_metadata_file_ids=[broken.pk],
                                             harvesting_job_id=self.job.pk)

        self.assertEqual([broken.pk], attempts,
                         'the documented error of a record is terminal')

    def test_an_aborted_job_imports_nothing_of_its_chunk(self):
        for phase in (Phase.ABORT, Phase.ABORTED):
            with self.subTest(phase=phase):
                job = self._job(1)
                stored = self._store(job, 'first.xml')
                HarvestingJob.objects.filter(pk=job.pk).update(phase=phase)
                attempts = []

                def import_file(record):
                    attempts.append(record.pk)
                    return imports_a_record(record)

                with patch.object(TemporaryMdMetadataFile, 'md_metadata_file_to_db', import_file):
                    results = call_md_metadata_files_to_db.run(
                        md_metadata_file_ids=[stored.pk], harvesting_job_id=job.pk)

                self.assertEqual([], results)
                self.assertEqual([], attempts, 'an aborted job must not be written to the database')
                self.assertTrue(TemporaryMdMetadataFile.objects.filter(pk=stored.pk).exists())

    def test_a_chunk_without_ids_imports_nothing(self):
        self.assertEqual([], call_md_metadata_files_to_db.run(md_metadata_file_ids=[],
                                                              harvesting_job_id=self.job.pk))
