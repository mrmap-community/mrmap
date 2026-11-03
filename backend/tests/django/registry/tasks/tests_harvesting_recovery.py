from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import Mock, PropertyMock, patch
from uuid import uuid4

from celery.exceptions import Retry
from django.core.files.base import ContentFile
from django.db import OperationalError, connection, transaction
from django.test import TestCase, TransactionTestCase, override_settings
from django.utils.timezone import now
from lxml import etree
from registry.enums.harvesting import (HarvestingPhaseEnum as Phase,
                                       LogKindEnum, LogLevelEnum)
from registry.models.harvest import HarvestingJob, TemporaryMdMetadataFile
from registry.models.service import CatalogueService
from registry.models.metadata import MetadataContact
from registry.ows_lib.client.exceptions import InitialError
from registry.querys.harvest_history import complete_harvest
from requests.exceptions import (ChunkedEncodingError, ConnectionError,
                                 ReadTimeout, Timeout)
from kombu.exceptions import OperationalError as BrokerOperationalError
from registry.tasks.harvest import (
    HarvestingTask, call_chord_md_metadata_file_to_db, call_fetch_records,
    call_fetch_total_records, call_md_metadata_file_to_db,
    call_md_metadata_files_to_db,
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

    def test_skipped_temporal_extent_is_reported_in_harvesting_log(self):
        for filename in ('dataset.xml', 'service.xml'):
            with self.subTest(filename=filename):
                xml = Path(__file__).parent / '../../test_data/iso_metadata' / filename
                root = etree.parse(str(xml))
                period = root.xpath('//*[local-name()="TimePeriod"]')[0]
                period.find('{*}beginPosition').text = '2016-02-01'
                end = period.find('{*}endPosition')
                end.attrib.clear()
                end.text = '2014-12-31'
                identifier = root.xpath('//*[local-name()="fileIdentifier"]/*/text()')[0]
                record = TemporaryMdMetadataFile(job=self.job)
                record.md_metadata_file.save(filename, ContentFile(etree.tostring(root)), save=False)
                TemporaryMdMetadataFile.objects.bulk_create([record])
                record_id = record.pk

                with self.captureOnCommitCallbacks(execute=True):
                    results = record.md_metadata_file_to_db()

                imported = results[0][0]
                self.assertEqual(imported.file_identifier, identifier)
                self.assertFalse(imported.time_extents.exists())
                self.assertFalse(TemporaryMdMetadataFile.objects.filter(pk=record_id).exists())
                log = self.job.logs.latest('pk')
                self.assertEqual(log.level, LogLevelEnum.WARNING)
                self.assertEqual(log.description,
                                 'Skipped temporal extent because begin 2016-02-01 is after end 2014-12-31.')
                with log.extented_description.open('rb') as details_file:
                    details = details_file.read().decode()
                self.assertIn(identifier, details)
                self.assertIn(filename, details)
                self.assertIn(log.description, details)
                self.assertIn('The remaining metadata was imported.', details)
        self.assertEqual(self.job.logs.count(), 2)

    def test_valid_temporal_extent_does_not_create_harvesting_warning(self):
        xml = Path(__file__).parent / '../../test_data/iso_metadata/service.xml'
        self.record.md_metadata_file.save('service.xml', ContentFile(xml.read_bytes()), save=False)
        TemporaryMdMetadataFile.objects.bulk_update([self.record], ['md_metadata_file'])

        with self.captureOnCommitCallbacks(execute=True):
            results = self.record.md_metadata_file_to_db()

        self.assertTrue(results[0][0].time_extents.exists())
        self.assertFalse(self.job.logs.exists())

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
                     call_md_metadata_files_to_db,
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

    def test_a_task_which_gave_up_ends_the_job_as_aborted(self):
        """a page which keeps failing never completes the chord it belongs to, so the callback
        which would end the run never runs - the job must not sit unfinished forever (#690)"""
        HarvestingJob.objects.filter(pk=self.job.pk).update(
            phase=Phase.DOWNLOAD_RECORDS, celery_task_ids=[uuid4()])
        call_fetch_records.push_request(retries=10)
        self.addCleanup(call_fetch_records.pop_request)

        with patch('celery.app.control.Control.revoke') as revoke, self.captureOnCommitCallbacks(execute=True):
            call_fetch_records.on_failure(
                Timeout('the catalogue is offline'), str(uuid4()), (),
                {'harvesting_job_id': self.job.pk, 'start_position': 51}, None)
            revoke.assert_not_called()

        revoke.assert_called_once()
        self.job.refresh_from_db()
        self.assertEqual(self.job.phase, Phase.ABORTED)
        self.assertIsNotNone(self.job.done_at)
        log = self.job.logs.first()
        self.assertEqual(log.level, LogLevelEnum.ERROR.value)
        self.assertEqual(log.kind, LogKindEnum.REMOTE_ERROR.value)
        self.assertIn('start_position=51', log.description)
        logged = log.extented_description.read().decode('UTF-8')
        self.assertIn('after 10 retries', logged)
        self.assertIn('Timeout: the catalogue is offline', logged)

    def test_a_late_failure_does_not_rewrite_a_job_which_is_already_done(self):
        """the callback which completed the job decided about it; a task of it which reports a
        failure afterwards must neither abort the finished run nor log itself as its end"""
        HarvestingJob.objects.filter(pk=self.job.pk).update(
            phase=Phase.COMPLETED, done_at=now())

        with patch('celery.app.control.Control.revoke') as revoke:
            call_fetch_records.on_failure(
                Timeout('offline'), str(uuid4()), (),
                {'harvesting_job_id': self.job.pk}, None)

        revoke.assert_not_called()
        self.job.refresh_from_db()
        self.assertEqual(self.job.phase, Phase.COMPLETED)
        self.assertEqual(self.job.logs.count(), 0)

    def test_a_task_which_is_not_about_one_job_ends_no_job(self):
        with patch('celery.app.control.Control.revoke') as revoke:
            create_harvesting_job.on_failure(
                Timeout('offline'), str(uuid4()), (), {}, None)

        revoke.assert_not_called()

    def test_a_late_chord_callback_does_not_complete_an_aborted_harvest(self):
        """the abort which ends a run whose tasks gave up revokes the tasks of that run, so the
        callback of its chord may still report in later - it must not turn the aborted run into a
        snapshot of the catalogue"""
        HarvestingJob.objects.filter(pk=self.job.pk).update(
            phase=Phase.ABORTED, done_at=now())

        with patch('registry.querys.harvest_history.complete_snapshots') as snapshots:
            complete_harvest(self.job.pk)

        snapshots.assert_not_called()
        self.job.refresh_from_db()
        self.assertEqual(self.job.phase, Phase.ABORTED)

    def test_a_harvest_created_for_a_catalogue_starts_from_its_step_size(self):
        """neither a schedule nor the "harvest now" of the ui name a step size - the catalogue is
        the memory of the size its remote service answers, so a run starts from that (#691)"""
        contact = MetadataContact.objects.create(name='Sized catalogue contact')
        service = CatalogueService(version=202, metadata_contact=contact, service_contact=contact,
                                   max_step_size=250)
        CatalogueService.objects.bulk_create([service])
        with patch('celery.canvas.Signature.apply_async'), patch.object(call_fetch_total_records, 'delay'):
            job_id = create_harvesting_job.run(service_id=service.pk)
        self.assertEqual(HarvestingJob.objects.get(pk=job_id).max_step_size, 250)


class ImportTransientFailureTest(TestCase):
    """a stored metadata file must survive a catalogue which times out or answers 5xx
    while its records are imported: the terminal has_import_error is reserved for
    errors of the record, not of the network (#895)"""

    CAPABILITIES_URL = ('https://catalogue.example.org/csw'
                        '?service=CSW&version=2.0.2&request=GetCapabilities')

    def setUp(self):
        self.media = TemporaryDirectory()
        self.addCleanup(self.media.cleanup)
        self.settings_override = override_settings(MEDIA_ROOT=self.media.name)
        self.settings_override.enable()
        self.addCleanup(self.settings_override.disable)
        contact = MetadataContact.objects.create(name='Transient import contact')
        service = CatalogueService(version=202, metadata_contact=contact, service_contact=contact)
        CatalogueService.objects.bulk_create([service])
        self.job = HarvestingJob(total_records=1, phase=Phase.RECORDS_TO_DB, service=service)
        HarvestingJob.objects.bulk_create([self.job])
        # a real record: its import asks the catalogue for the origin url of the record,
        # which is where the read timeout of the live failure was raised
        dataset = Path(__file__).parent / '../../test_data/iso_metadata/dataset.xml'
        self.record = self._stored('dataset.xml', dataset.read_bytes())

    def _stored(self, name, content=b'<record/>'):
        stored = TemporaryMdMetadataFile(job=self.job)
        stored.md_metadata_file.save(name, ContentFile(content), save=False)
        TemporaryMdMetadataFile.objects.bulk_create([stored])
        return stored

    def test_a_read_timeout_while_the_client_is_built_retries_the_file(self):
        """the origin url of an imported record is answered by the client of the catalogue,
        whose constructor GETs the stored capabilities URL; the live read timeout of that
        request must redeliver the file with the backoff of the harvest instead of ending
        it with the traceback of the network (the mechanism of #895)"""
        with patch.object(CatalogueService, 'capabilities', new_callable=PropertyMock,
                          return_value=self.CAPABILITIES_URL), \
                patch('requests.Session.send', side_effect=ReadTimeout(
                    'HTTPSConnectionPool(host=...): Read timed out. (read timeout=10)')):
            with self.assertRaises(ReadTimeout):
                call_md_metadata_file_to_db.run(md_metadata_file_id=self.record.pk,
                                                harvesting_job_id=self.job.pk)
        self.record.refresh_from_db()
        self.assertFalse(self.record.has_import_error)
        self.assertEqual('', self.record.import_error)
        self.assertTrue(TemporaryMdMetadataFile.objects.filter(pk=self.record.pk).exists())

    def test_a_5xx_while_the_client_is_built_retries_the_file(self):
        """the same round trip answers a 5xx with the InitialError of the client
        package: it is the failure of the same remote and must not end the file either"""
        response = Mock(status_code=503, headers={'content-type': 'text/html'})
        with patch.object(CatalogueService, 'capabilities', new_callable=PropertyMock,
                          return_value=self.CAPABILITIES_URL), \
                patch('requests.Session.send', return_value=response):
            with self.assertRaises(InitialError):
                call_md_metadata_file_to_db.run(md_metadata_file_id=self.record.pk,
                                                harvesting_job_id=self.job.pk)
        self.record.refresh_from_db()
        self.assertFalse(self.record.has_import_error)

    def test_transient_failures_reach_the_task_base_of_both_import_tasks(self):
        """what a harvest task retries must escape the per-file catch, and that has to
        hold for the single file and for the chunk which carries many of them"""
        for error in (Timeout('read timeout=10'), ReadTimeout('read timeout=10'),
                      ConnectionError('connection refused'),
                      InitialError('client could not be initialized. Response status code: 502')):
            for task in (call_md_metadata_file_to_db, call_md_metadata_files_to_db):
                with self.subTest(task=task.name, error=type(error).__name__):
                    stored = self._stored('record.xml')
                    with patch.object(TemporaryMdMetadataFile, 'md_metadata_file_to_db',
                                      side_effect=error):
                        with self.assertRaises(type(error)):
                            if task is call_md_metadata_file_to_db:
                                task.run(md_metadata_file_id=stored.pk,
                                         harvesting_job_id=self.job.pk)
                            else:
                                task.run(md_metadata_file_ids=[stored.pk],
                                         harvesting_job_id=self.job.pk)
                    stored.refresh_from_db()
                    self.assertFalse(stored.has_import_error)
                    self.assertEqual('', stored.import_error)

    def test_the_import_tasks_retry_what_must_not_end_a_file(self):
        """the re-raising of the import and the autoretry of its tasks answer one
        set: two contradicting statements about retryable failures were #895"""
        for task in (call_md_metadata_file_to_db, call_md_metadata_files_to_db):
            with self.subTest(task=task.name):
                self.assertIn(InitialError, task.autoretry_for)
                self.assertTrue(set(HarvestingTask.autoretry_for) <= set(task.autoretry_for))
        self.assertNotIn(InitialError, HarvestingTask.autoretry_for,
                         'the other tasks of the harvest keep their retry contract')

    def test_a_transient_error_sends_the_pending_files_of_a_chunk_to_retry(self):
        """a chunk which loses the catalogue stops at that file: the files it did not
        commit stay unflagged, so the redelivery of the chunk imports them"""
        first, second = self._stored('first.xml'), self._stored('second.xml')
        attempts = []

        def import_file(record):
            attempts.append(record.pk)
            raise ReadTimeout('read timed out')

        with patch.object(TemporaryMdMetadataFile, 'md_metadata_file_to_db', import_file):
            with self.assertRaises(ReadTimeout):
                call_md_metadata_files_to_db.run(md_metadata_file_ids=[first.pk, second.pk],
                                                 harvesting_job_id=self.job.pk)

        self.assertEqual([first.pk], attempts, 'the chunk stops at the transient error')
        for stored in (first, second):
            stored.refresh_from_db()
            self.assertFalse(stored.has_import_error,
                             'the pending files wait for the redelivery unflagged')

    def test_a_record_error_is_still_documented_as_terminal(self):
        """nothing transient is in play here: the document is no MD_Metadata, so the
        file ends with the error of its own content and stays flagged for inspection"""
        broken = self._stored('broken.xml')
        self.assertIsNone(call_md_metadata_file_to_db.run(md_metadata_file_id=broken.pk,
                                                          harvesting_job_id=self.job.pk))
        broken.refresh_from_db()
        self.assertTrue(broken.has_import_error)
        self.assertIn('No MD_Metadata elements found', broken.import_error)
        self.assertIsNone(call_md_metadata_file_to_db.run(md_metadata_file_id=broken.pk,
                                                          harvesting_job_id=self.job.pk))
        broken.refresh_from_db()
        self.assertTrue(broken.has_import_error, 'the documented error stays terminal')


class ImportTransientRetryEagerTest(TransactionTestCase):
    """the celery machinery, not only the body of the task, must answer a first read
    timeout with a retry: applied eagerly, the task retries with its backoff and the
    second attempt imports the file (#895).

    TransactionTestCase: the deployment closes old connections before and after every
    task run (MrMap/celery.py), which the atomic block wrapping a TestCase does not
    survive - the celery apply tests of this module are TransactionTestCases too.
    """

    def setUp(self):
        self.media = TemporaryDirectory()
        self.addCleanup(self.media.cleanup)
        self.settings_override = override_settings(MEDIA_ROOT=self.media.name)
        self.settings_override.enable()
        self.addCleanup(self.settings_override.disable)
        self.job = HarvestingJob(total_records=1, phase=Phase.RECORDS_TO_DB)
        HarvestingJob.objects.bulk_create([self.job])
        self.record = TemporaryMdMetadataFile(job=self.job)
        self.record.md_metadata_file.save('dataset.xml', ContentFile(b'<record/>'), save=False)
        TemporaryMdMetadataFile.objects.bulk_create([self.record])

    def test_the_file_is_imported_after_a_retried_timeout(self):
        attempts = []

        def import_file(record):
            attempts.append(record.pk)
            if len(attempts) == 1:
                raise ReadTimeout('HTTPSConnectionPool(host=...): Read timed out.')
            record.delete()
            return [(SimpleNamespace(pk=record.pk), False, False)]

        with patch.object(TemporaryMdMetadataFile, 'md_metadata_file_to_db', import_file):
            result = call_md_metadata_file_to_db.apply(
                kwargs={'md_metadata_file_id': self.record.pk,
                        'harvesting_job_id': self.job.pk}, throw=False)

        self.assertEqual('SUCCESS', result.state, str(result.result))
        self.assertGreaterEqual(len(attempts), 2,
                                'the timeout was retried by the task base, not documented')
        self.assertFalse(TemporaryMdMetadataFile.objects.filter(pk=self.record.pk).exists(),
                         'the file of the retry was imported')


class HarvestingPublishingRecoveryTest(TransactionTestCase):
    def setUp(self):
        media = TemporaryDirectory()
        self.addCleanup(media.cleanup)
        settings = override_settings(MEDIA_ROOT=media.name)
        settings.enable()
        self.addCleanup(settings.disable)

    def test_exhausted_discovery_commits_failure_before_revoking_siblings(self):
        task_id, sibling_id = uuid4(), uuid4()
        job = HarvestingJob(celery_task_ids=[task_id, sibling_id])
        HarvestingJob.objects.bulk_create([job])
        observed = []

        def check_committed_abort(*args, **kwargs):
            job.refresh_from_db()
            log = job.logs.get()
            with log.extented_description.open('rb') as details:
                observed.append((connection.in_atomic_block, job.phase, job.done_at,
                                 log.description, details.read()))

        with patch.object(HarvestingJob, 'fetch_total_records', side_effect=ChunkedEncodingError('incomplete body')):
            with patch('celery.app.control.Control.revoke', side_effect=check_committed_abort) as revoke:
                result = call_fetch_total_records.apply(
                    kwargs={'harvesting_job_id': job.pk}, task_id=str(task_id), retries=10, throw=False)

        self.assertEqual(result.state, 'FAILURE')
        revoke.assert_called_once_with([str(sibling_id)], terminate=True)
        self.assertEqual(len(observed), 1)
        in_transaction, phase, done_at, description, details = observed[0]
        self.assertFalse(in_transaction)
        self.assertEqual(phase, Phase.ABORTED)
        self.assertIsNotNone(done_at)
        self.assertEqual(description, 'task gave up')
        self.assertIn(b'ChunkedEncodingError: incomplete body', details)

    def test_manual_abort_is_saved_before_tasks_are_terminated(self):
        task_id = uuid4()
        job = HarvestingJob(celery_task_ids=[task_id])
        HarvestingJob.objects.bulk_create([job])

        def check_committed_abort(*args, **kwargs):
            self.assertFalse(connection.in_atomic_block)
            stored = HarvestingJob.objects.get(pk=job.pk)
            self.assertEqual(stored.phase, Phase.ABORTED)
            self.assertIsNotNone(stored.done_at)

        with patch('celery.app.control.Control.revoke', side_effect=check_committed_abort) as revoke:
            job.phase = Phase.ABORT
            job.save()
        revoke.assert_called_once_with([str(task_id)], terminate=True)

    def test_rolled_back_abort_does_not_terminate_tasks(self):
        job = HarvestingJob(celery_task_ids=[uuid4()])
        HarvestingJob.objects.bulk_create([job])
        with patch('celery.app.control.Control.revoke') as revoke:
            with self.assertRaisesMessage(RuntimeError, 'rollback'):
                with transaction.atomic():
                    job.phase = Phase.ABORT
                    job.save()
                    revoke.assert_not_called()
                    raise RuntimeError('rollback')
        revoke.assert_not_called()
        job.refresh_from_db()
        self.assertEqual(job.phase, Phase.PENDING)
        self.assertIsNone(job.done_at)

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
