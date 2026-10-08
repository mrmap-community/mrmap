from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch
from uuid import uuid4

from celery.exceptions import Retry
from django.core.files.base import ContentFile
from django.db import OperationalError, transaction
from django.test import TestCase, TransactionTestCase, override_settings
from registry.enums.harvesting import HarvestingPhaseEnum as Phase
from registry.models.harvest import HarvestingJob, TemporaryMdMetadataFile
from registry.models.service import CatalogueService
from registry.models.metadata import MetadataContact
from requests.exceptions import Timeout
from kombu.exceptions import OperationalError as BrokerOperationalError
from registry.tasks.harvest import (
    call_chord_md_metadata_file_to_db, call_fetch_records,
    call_fetch_total_records, call_md_metadata_file_to_db,
    create_harvesting_job, finish_harvesting_job, recover_harvesting_jobs,
    recover_harvests_after_restart,
)


class HarvestingRecoveryTest(TestCase):
    def setUp(self):
        self.media = TemporaryDirectory()
        self.addCleanup(self.media.cleanup)
        self.settings_override = override_settings(MEDIA_ROOT=self.media.name)
        self.settings_override.enable()
        self.addCleanup(self.settings_override.disable)
        self.job = HarvestingJob(total_records=1, phase=Phase.RECORDS_TO_DB)
        HarvestingJob.objects.bulk_create([self.job])
        self.record = TemporaryMdMetadataFile(job=self.job)
        self.record.md_metadata_file.save('record.xml', ContentFile(b'<record/>'), save=False)
        TemporaryMdMetadataFile.objects.bulk_create([self.record])

    def test_crashed_import_rolls_back_and_preserves_source_file(self):
        path = Path(self.record.md_metadata_file.path)

        def crash(record):
            HarvestingJob.objects.filter(pk=record.job_id).update(total_records=99)
            record.delete()
            raise SystemExit('worker killed')

        with patch.object(TemporaryMdMetadataFile, 'md_metadata_file_to_db', crash):
            with self.assertRaises(SystemExit):
                call_md_metadata_file_to_db.run(md_metadata_file_id=self.record.pk)
        self.job.refresh_from_db()
        self.record.refresh_from_db()
        self.assertEqual(self.job.total_records, 1)
        self.assertFalse(self.record.has_import_error)
        self.assertTrue(path.exists())

    def test_successful_import_can_be_delivered_twice(self):
        path = Path(self.record.md_metadata_file.path)
        record_id = self.record.pk

        def imported(record):
            record.delete()
            return []

        with patch.object(TemporaryMdMetadataFile, 'md_metadata_file_to_db', imported):
            with self.captureOnCommitCallbacks(execute=True):
                self.assertEqual(call_md_metadata_file_to_db.run(md_metadata_file_id=record_id), [])
            self.assertIsNone(call_md_metadata_file_to_db.run(md_metadata_file_id=record_id))
        self.assertFalse(path.exists())
        self.assertFalse(TemporaryMdMetadataFile.objects.filter(pk=record_id).exists())

    def test_import_error_is_documented_after_partial_changes_roll_back(self):
        def fail(record):
            HarvestingJob.objects.filter(pk=record.job_id).update(total_records=99)
            raise ValueError('invalid metadata')

        with patch.object(TemporaryMdMetadataFile, 'md_metadata_file_to_db', fail):
            self.assertIsNone(call_md_metadata_file_to_db.run(md_metadata_file_id=self.record.pk))
        self.job.refresh_from_db()
        self.record.refresh_from_db()
        self.assertEqual(self.job.total_records, 1)
        self.assertTrue(self.record.has_import_error)
        self.assertIn('invalid metadata', self.record.import_error)
        with patch.object(TemporaryMdMetadataFile, 'md_metadata_file_to_db') as import_record:
            call_md_metadata_file_to_db.run(md_metadata_file_id=self.record.pk)
            import_record.assert_not_called()

    def test_database_outage_is_not_documented_as_import_error(self):
        with patch.object(TemporaryMdMetadataFile, 'md_metadata_file_to_db', side_effect=OperationalError('offline')):
            with self.assertRaises(OperationalError):
                call_md_metadata_file_to_db.run(md_metadata_file_id=self.record.pk)
        self.record.refresh_from_db()
        self.assertFalse(self.record.has_import_error)

    def test_finish_waits_for_pending_imports_but_accepts_documented_errors(self):
        with patch.object(finish_harvesting_job, 'retry', side_effect=Retry()) as retry:
            with self.assertRaises(Retry):
                finish_harvesting_job.run(harvesting_job_id=self.job.pk)
            retry.assert_called_once_with(countdown=5)
        self.job.refresh_from_db()
        self.assertIsNone(self.job.done_at)
        TemporaryMdMetadataFile.objects.filter(pk=self.record.pk).update(has_import_error=True)
        finish_harvesting_job.run(harvesting_job_id=self.job.pk)
        self.job.refresh_from_db()
        self.assertEqual(self.job.phase, Phase.COMPLETED)

    def test_recovery_schedules_only_unfinished_phases(self):
        contact = MetadataContact.objects.create(name='Recovery contact')
        service = CatalogueService(version=202, metadata_contact=contact, service_contact=contact)
        CatalogueService.objects.bulk_create([service])
        download_job = HarvestingJob(service=service, total_records=10, phase=Phase.DOWNLOAD_RECORDS)
        aborted = HarvestingJob(total_records=1, phase=Phase.ABORT)
        HarvestingJob.objects.bulk_create([download_job, aborted])
        with patch.object(call_fetch_total_records, 'delay') as download, patch.object(call_chord_md_metadata_file_to_db, 'delay') as imports:
            recover_harvesting_jobs.run()
        download.assert_called_once_with(harvesting_job_id=download_job.pk)
        imports.assert_called_once_with(harvesting_job_id=self.job.pk)

    def test_worker_startup_queues_recovery(self):
        worker = Mock()
        recover_harvests_after_restart(worker)
        worker.app.send_task.assert_called_once_with('registry.tasks.harvest.recover_harvesting_jobs')

    def test_import_chord_records_real_task_ids_and_publishes_after_commit(self):
        with patch.object(HarvestingJob, '_http_request', return_value=None), patch('registry.tasks.harvest.chord') as chord:
            with self.captureOnCommitCallbacks(execute=True):
                call_chord_md_metadata_file_to_db.run(harvesting_job_id=self.job.pk)
                chord.assert_not_called()
        self.job.refresh_from_db()
        header, callback = chord.call_args.args
        self.assertEqual(set(map(str, self.job.celery_task_ids)), {header[0].options['task_id'], callback.options['task_id']})

    def test_task_ids_from_stale_instances_are_preserved(self):
        stale = HarvestingJob.objects.get(pk=self.job.pk)
        first, second = uuid4(), uuid4()
        self.job.append_celery_task_ids([first])
        stale.append_celery_task_ids([second])
        self.job.refresh_from_db()
        self.assertEqual(self.job.celery_task_ids, [first, second])

    def test_harvesting_tasks_use_worker_loss_redelivery(self):
        for task in [create_harvesting_job, call_fetch_total_records, call_fetch_records,
                     call_chord_md_metadata_file_to_db, call_md_metadata_file_to_db,
                     finish_harvesting_job, recover_harvesting_jobs]:
            with self.subTest(task=task.name):
                self.assertTrue(task.acks_late)
                self.assertTrue(task.reject_on_worker_lost)

    def test_file_delete_is_discarded_on_rollback(self):
        path = Path(self.record.md_metadata_file.path)
        with self.assertRaises(SystemExit):
            with transaction.atomic():
                self.record.delete()
                raise SystemExit()
        self.assertTrue(path.exists())

    def test_resumed_downloads_reuse_count(self):
        HarvestingJob.objects.filter(pk=self.job.pk).update(phase=Phase.DOWNLOAD_RECORDS)
        with patch.object(HarvestingJob, 'fetch_total_records') as count, patch.object(HarvestingJob, 'handle_total_records_defined') as schedule:
            self.assertEqual(call_fetch_total_records.run(harvesting_job_id=self.job.pk), 1)
        count.assert_not_called()
        schedule.assert_called_once_with(recovering=True)

    def test_total_count_timeout_is_retryable_without_completing_job(self):
        HarvestingJob.objects.filter(pk=self.job.pk).update(phase=Phase.PENDING, total_records=None)
        with patch.object(HarvestingJob, 'fetch_total_records', side_effect=Timeout('offline')):
            with self.assertRaises(Timeout):
                call_fetch_total_records.run(harvesting_job_id=self.job.pk)
        self.job.refresh_from_db()
        self.assertIsNone(self.job.total_records)
        self.assertIsNone(self.job.done_at)

    def test_reschedule_clears_documented_error_and_publishes_once_after_commit(self):
        self.record.has_import_error = True
        self.record.import_error = 'invalid metadata'
        self.record.re_schedule = True
        with patch.object(HarvestingJob, '_http_request', return_value=None), patch('celery.canvas.Signature.apply_async') as publish:
            with self.captureOnCommitCallbacks(execute=True):
                self.record.save()
                publish.assert_not_called()
        self.record.refresh_from_db()
        self.assertFalse(self.record.has_import_error)
        self.assertEqual(self.record.import_error, '')
        publish.assert_called_once()

    def test_creation_redelivery_does_not_create_another_completed_harvest(self):
        contact = MetadataContact.objects.create(name='Creation contact')
        service = CatalogueService(version=202, metadata_contact=contact, service_contact=contact)
        CatalogueService.objects.bulk_create([service])
        delivery_id = str(uuid4())
        create_harvesting_job.push_request(id=delivery_id)
        self.addCleanup(create_harvesting_job.pop_request)
        with patch('celery.canvas.Signature.apply_async'), patch.object(call_fetch_total_records, 'delay'):
            first_id = create_harvesting_job.run(service_id=service.pk)
            job = HarvestingJob.objects.get(pk=first_id)
            job.phase = Phase.COMPLETED
            job.done_at = job.date_created
            job.save()
            self.assertEqual(create_harvesting_job.run(service_id=service.pk), first_id)
        self.assertEqual(HarvestingJob.objects.filter(service=service).count(), 1)


class HarvestingPublishingRecoveryTest(TransactionTestCase):
    def test_broker_failure_after_commit_is_retryable_and_resumes_downloads(self):
        job = HarvestingJob(total_records=1, phase=Phase.PENDING)
        HarvestingJob.objects.bulk_create([job])
        with patch.object(HarvestingJob, '_http_request', return_value=None), patch.object(HarvestingJob, 'fetch_total_records') as count:
            with patch('celery.canvas.chord.apply_async', side_effect=BrokerOperationalError('offline')):
                with self.assertRaises(BrokerOperationalError):
                    call_fetch_total_records.run(harvesting_job_id=job.pk)
            job.refresh_from_db()
            self.assertEqual(job.phase, Phase.DOWNLOAD_RECORDS)
            self.assertIsNone(job.done_at)
            count.assert_called_once()
            count.reset_mock()
            with patch('celery.canvas.chord.apply_async') as publish:
                call_fetch_total_records.run(harvesting_job_id=job.pk)
            count.assert_not_called()
            publish.assert_called_once()
