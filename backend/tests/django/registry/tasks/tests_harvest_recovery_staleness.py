"""The staleness of a registered import run (#972).

``HarvestingJob.has_live_import_run`` answers from the database, and a task id
whose message the broker dropped stays registered for the rest of the job's
life - one such row plus waiting files was enough for recovery to decline the
whole backlog forever. These tests hold the broker in their own hands: the
recovery paths stub ``import_run_message_state``, and the state itself is
probed against fakes of the redis reads it makes. A recovery which cannot go
stale is the bug, so the demos of the issue are the tests here: a fake id row
with no broker message must re-chord, and a broker which verifiably still
holds a message must still be declined (the protection of #891 intact).
"""

import json
from contextlib import ExitStack
from io import StringIO
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch
from uuid import uuid4

from django.core.files.base import ContentFile
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils.timezone import now
from MrMap.celery import app
from registry.enums.harvesting import HarvestingPhaseEnum as Phase
from registry.enums.harvesting import LogLevelEnum
from registry.models.harvest import (HarvestingJob, HarvestingJobTaskId,
                                     TemporaryMdMetadataFile)
from registry.tasks.harvest import (call_chord_md_metadata_file_to_db,
                                    import_run_message_state,
                                    recover_harvesting_jobs)


def _message(task_id):
    """One celery protocol-2 envelope as the redis transport keeps it on a
    queue: the task id the probe reads is the ``properties.correlation_id``."""
    return json.dumps({
        'body': 'eyJrZXkiOiAidGhlIHByb2JlIG5ldmVyIGRlY29kZXMgdGhlIGJvZHkifQ==',
        'content-encoding': 'base64',
        'content-type': 'application/json',
        'headers': {},
        'properties': {'correlation_id': str(task_id), 'delivery_tag': 'x'},
    }).encode()


class FakeRedisClient:
    """The few paged reads the broker probe makes, answered from dicts of raw
    values, sliced the way the redis list reads slice."""

    def __init__(self, data=None, errors=()):
        self.data = data or {}
        self.errors = errors

    def _read(self, key, start, end):
        if key in self.errors:
            raise ConnectionError(f'the broker does not answer for {key}')
        return self.data.get(key, [])[start:end + 1]

    def lrange(self, key, start, end):
        return self._read(key, start, end)

    def zrange(self, key, start, end):
        return self._read(key, start, end)


def _broker_connection(client):
    """A read connection as the probe finds it, with the transport's raw
    redis client on its channel."""
    connection = MagicMock()
    connection.default_channel = SimpleNamespace(client=client) if client is not None \
        else SimpleNamespace()
    context = MagicMock()
    context.__enter__.return_value = connection
    return context


class ImportRunMessageStateTest(TestCase):
    """The broker answer itself: live, stale or unaskable (#972)."""

    def _state_of(self, client, *registered):
        # the workers only reinforce what the queues and unacked keys answer;
        # their broadcasts stay out of these queue tests
        with patch.object(app, 'connection_for_read',
                          return_value=_broker_connection(client)), \
                patch('registry.tasks.harvest._worker_reported_task_ids',
                      return_value=set()):
            return import_run_message_state({str(_id) for _id in registered})

    def test_an_empty_shadow_names_no_run(self):
        with patch.object(app, 'connection_for_read') as connect:
            self.assertFalse(import_run_message_state(set()))
        connect.assert_not_called()

    def test_a_registered_id_still_queued_on_a_harvest_queue_is_live(self):
        task_id = uuid4()
        for queue in ('default', 'download', 'db-routines', 'harvest-import'):
            with self.subTest(queue=queue):
                client = FakeRedisClient({queue: [_message(uuid4()), _message(task_id)]})
                self.assertIs(True, self._state_of(client, task_id))

    def test_a_message_between_queue_and_ack_is_live(self):
        """all harvest tasks ack late, so a message a worker took out of a
        queue still sits in the transport's unacked keys until it reports in"""
        task_id = uuid4()
        for key, read in (('unacked', 'lrange'), ('unacked_index', 'zrange')):
            with self.subTest(key=key):
                self.assertIs(True, self._state_of(
                    FakeRedisClient({key: [_message(task_id)]}), task_id))

    def test_an_id_a_running_worker_reports_is_live(self):
        task_id = uuid4()
        inspector = Mock()
        inspector.active.return_value = {
            'celery@worker': [{'id': str(task_id), 'name': 'registry.tasks.harvest'}]}
        inspector.reserved.return_value = None
        inspector.scheduled.return_value = None
        with patch.object(app, 'connection_for_read',
                          return_value=_broker_connection(FakeRedisClient())), \
                patch('celery.app.control.Control.inspect', return_value=inspector):
            self.assertIs(True, import_run_message_state({str(task_id)}))

    def test_the_nested_lists_of_a_reserved_answer_are_searched_too(self):
        """inspect().reserved() answers [name, [id, args, kwargs]] instead of
        the task-info dicts of active and scheduled"""
        task_id = uuid4()
        inspector = Mock()
        inspector.active.return_value = None
        inspector.reserved.return_value = {
            'celery@worker': [['registry.tasks.harvest.call_md_metadata_files_to_db',
                               [str(task_id), [], {}]]]}
        inspector.scheduled.return_value = None
        with patch.object(app, 'connection_for_read',
                          return_value=_broker_connection(FakeRedisClient())), \
                patch('celery.app.control.Control.inspect', return_value=inspector):
            self.assertIs(True, import_run_message_state({str(task_id)}))

    def test_a_broker_holding_nothing_answers_stale(self):
        self.assertIs(False, self._state_of(FakeRedisClient(), uuid4()))

    def test_a_backlog_beyond_one_scan_page_is_worked_through(self):
        """the paged read must terminate its pages in both directions: the id
        at the far end is still found, and a full queue of other work still
        answers stale instead of spinning"""
        ours = uuid4()
        deep = [_message(uuid4()) for _ in range(1200)]
        self.assertIs(
            True, self._state_of(
                FakeRedisClient({'db-routines': deep + [_message(ours)]}), ours))
        self.assertIs(
            False, self._state_of(FakeRedisClient({'db-routines': deep}), uuid4()))

    def test_the_messages_of_other_work_answer_stale(self):
        """a queue which is only full of somebody else's backlog does not make
        this shadow live - the question is asked id by id"""
        client = FakeRedisClient({'db-routines': [_message(uuid4()) for _ in range(3)]})
        self.assertIs(False, self._state_of(client, uuid4()))

    def test_a_message_that_names_nothing_answers_unknown(self):
        """a message which exists but cannot be attributed must not count as
        no message"""
        client = FakeRedisClient({'db-routines': [b'not a celery message']})
        self.assertIsNone(self._state_of(client, uuid4()))

    def test_a_broker_that_cannot_be_read_answers_unknown(self):
        client = FakeRedisClient(errors=('db-routines',))
        self.assertIsNone(self._state_of(client, uuid4()))

    def test_a_broker_that_cannot_be_connected_answers_unknown(self):
        with patch.object(app, 'connection_for_read',
                          side_effect=ConnectionError('the broker is offline')):
            self.assertIsNone(import_run_message_state({str(uuid4())}))

    def test_a_broker_without_queue_introspection_answers_unknown(self):
        """no redis client on the channel (another transport): the question is
        unaskable and recovery has to know that"""
        with patch.object(app, 'connection_for_read',
                          return_value=_broker_connection(None)):
            self.assertIsNone(import_run_message_state({str(uuid4())}))


class StaleImportRunRecoveryTest(TestCase):
    """Recovery acts on the stale answer and says what it decided on the job."""

    def setUp(self):
        self.media = TemporaryDirectory()
        self.addCleanup(self.media.cleanup)
        media_settings = override_settings(MEDIA_ROOT=self.media.name)
        media_settings.enable()
        self.addCleanup(media_settings.disable)
        self.job = HarvestingJob(total_records=1, phase=Phase.RECORDS_TO_DB)
        HarvestingJob.objects.bulk_create([self.job])
        record = TemporaryMdMetadataFile(job=self.job)
        record.md_metadata_file.save('record.xml', ContentFile(b'<record/>'), save=False)
        TemporaryMdMetadataFile.objects.bulk_create([record])

    def test_the_demo_of_the_issue_rechords_once_the_broker_says_stale(self):
        """a row whose uuid appears in no queue was True and declined forever;
        the shadow now goes stale against the broker and the import resumes"""
        lost = uuid4()
        HarvestingJobTaskId.objects.create(job=self.job, task_id=lost)
        self.assertTrue(self.job.has_live_import_run())

        with patch('registry.tasks.harvest.import_run_message_state',
                   return_value=False) as ask, \
                patch('registry.tasks.harvest.chord_publish_message_state',
                      return_value=False), \
                patch.object(call_chord_md_metadata_file_to_db, 'delay') as rechord:
            recover_harvesting_jobs.run()

        ask.assert_called_once_with({str(lost)})
        rechord.assert_called_once_with(harvesting_job_id=self.job.pk)
        self.assertFalse(HarvestingJobTaskId.objects.filter(creation=False).exists(),
                         'the ids are gone with the messages they never named')
        log = self.job.logs.latest('pk')
        self.assertEqual(log.level, LogLevelEnum.WARNING.value)
        self.assertIn('no message on the broker', log.description)
        self.assertIn('worker restart recovery', log.description)
        with log.extented_description.open('rb') as details:
            self.assertIn(str(lost), details.read().decode())

    def test_the_creation_id_outlives_a_stale_shadow(self):
        """the delivery id of the creation task is not bookkeeping of the run
        and stays registered (see append_celery_task_ids)"""
        creation, lost = uuid4(), uuid4()
        HarvestingJobTaskId.objects.bulk_create([
            HarvestingJobTaskId(job=self.job, task_id=creation, creation=True),
            HarvestingJobTaskId(job=self.job, task_id=lost)])

        with patch('registry.tasks.harvest.import_run_message_state', return_value=False), \
                patch('registry.tasks.harvest.chord_publish_message_state', return_value=False), \
                patch.object(call_chord_md_metadata_file_to_db, 'delay'):
            recover_harvesting_jobs.run()

        self.assertEqual([str(creation)],
                         [str(_id) for _id in
                          HarvestingJobTaskId.objects.values_list('task_id', flat=True)])

    def test_a_backlog_whose_messages_live_on_the_broker_is_left_alone(self):
        """conversely the protection of #891: while a message verifiably still
        lives, recovery must not publish the backlog a second time onto the
        queue which is already consuming it - and it says so on the job"""
        HarvestingJobTaskId.objects.create(job=self.job, task_id=uuid4())

        with patch('registry.tasks.harvest.import_run_message_state', return_value=True), \
                patch.object(call_chord_md_metadata_file_to_db, 'delay') as rechord:
            recover_harvesting_jobs.run()

        rechord.assert_not_called()
        self.assertEqual(1, HarvestingJobTaskId.objects.count(),
                         'a live shadow stays registered for the revocation on abort')
        log = self.job.logs.latest('pk')
        self.assertEqual(log.level, LogLevelEnum.INFO.value)
        self.assertIn('broker still holds a message', log.description)

    def test_a_broker_that_cannot_be_asked_declines_visibly(self):
        """without the broker the shadow cannot go stale, and an operator has
        to learn that from the job, not only from a worker log"""
        HarvestingJobTaskId.objects.create(job=self.job, task_id=uuid4())

        with patch('registry.tasks.harvest.import_run_message_state', return_value=None), \
                patch.object(call_chord_md_metadata_file_to_db, 'delay') as rechord:
            recover_harvesting_jobs.run()

        rechord.assert_not_called()
        log = self.job.logs.latest('pk')
        self.assertEqual(log.level, LogLevelEnum.WARNING.value)
        self.assertIn('could not answer', log.description)
        self.assertIn(f'resume_harvesting_job {self.job.pk}', log.description)

    def test_an_empty_shadow_rechords_without_asking_about_the_run(self):
        """#891's other half stays as it was: a run whose ids all reported in
        needs the chord again and there is nothing to ask the broker about;
        only #970's question whether a publish of the chord is already
        pending is asked, here stubbed absent"""
        HarvestingJobTaskId.objects.create(job=self.job, task_id=uuid4(), creation=True)

        with patch('registry.tasks.harvest.import_run_message_state') as ask, \
                patch('registry.tasks.harvest.chord_publish_message_state',
                      return_value=False), \
                patch.object(call_chord_md_metadata_file_to_db, 'delay') as rechord:
            recover_harvesting_jobs.run()

        ask.assert_not_called()
        rechord.assert_called_once_with(harvesting_job_id=self.job.pk)


class ResumeHarvestingJobCommandTest(TestCase):
    """The one supported operator path past a stranded backlog (#972)."""

    def setUp(self):
        self.media = TemporaryDirectory()
        self.addCleanup(self.media.cleanup)
        media_settings = override_settings(MEDIA_ROOT=self.media.name)
        media_settings.enable()
        self.addCleanup(media_settings.disable)
        self.job = HarvestingJob(total_records=1, phase=Phase.RECORDS_TO_DB)
        HarvestingJob.objects.bulk_create([self.job])
        record = TemporaryMdMetadataFile(job=self.job)
        record.md_metadata_file.save('record.xml', ContentFile(b'<record/>'), save=False)
        TemporaryMdMetadataFile.objects.bulk_create([record])
        self.out, self.err = StringIO(), StringIO()

    def _run(self, state='unset'):
        """call_command under the given broker answer; returns its exit code
        (None when it ran through) and the mocked chord publishing. None is a
        broker answer of its own, so the no-patch case needs its own value."""
        with ExitStack() as stack:
            rechord = stack.enter_context(
                patch.object(call_chord_md_metadata_file_to_db, 'delay'))
            # #970's question whether a publish of the chord is already
            # pending is answered absent, so the resume publishes (the
            # pending case itself is guarded in tests_harvest_queue_routing)
            stack.enter_context(
                patch('registry.tasks.harvest.chord_publish_message_state',
                      return_value=False))
            if state != 'unset':
                stack.enter_context(
                    patch('registry.tasks.harvest.import_run_message_state',
                          return_value=state))
            try:
                call_command('resume_harvesting_job', str(self.job.pk),
                             stdout=self.out, stderr=self.err)
            except SystemExit as exited:
                return exited.code, rechord
        return None, rechord

    def test_the_command_resumes_a_stranded_job(self):
        lost = uuid4()
        HarvestingJobTaskId.objects.create(job=self.job, task_id=lost)

        code, rechord = self._run(state=False)

        self.assertIsNone(code, self.err.getvalue())
        rechord.assert_called_once_with(harvesting_job_id=self.job.pk)
        self.assertFalse(HarvestingJobTaskId.objects.filter(creation=False).exists())
        log = self.job.logs.latest('pk')
        self.assertEqual(log.level, LogLevelEnum.WARNING.value)
        self.assertIn('resume_harvesting_job', log.description)

    def test_the_command_refuses_while_a_message_of_the_run_still_lives(self):
        HarvestingJobTaskId.objects.create(job=self.job, task_id=uuid4())

        code, rechord = self._run(state=True)

        self.assertEqual(1, code)
        rechord.assert_not_called()
        self.assertEqual(1, HarvestingJobTaskId.objects.count())
        self.assertIn('still holds a message', self.err.getvalue())
        self.assertFalse(self.job.logs.exists(),
                         'a refusal which changes nothing prints nothing and '
                         'publishes nothing')

    def test_the_command_refuses_when_the_broker_cannot_be_asked(self):
        HarvestingJobTaskId.objects.create(job=self.job, task_id=uuid4())

        code, rechord = self._run(state=None)

        self.assertEqual(1, code)
        rechord.assert_not_called()
        self.assertIn('could not be asked', self.err.getvalue())

    def test_the_command_refuses_a_job_which_did_not_strand_in_its_import(self):
        for phase, done in ((Phase.DOWNLOAD_RECORDS, None), (Phase.COMPLETED, 'done')):
            with self.subTest(phase=phase):
                HarvestingJob.objects.filter(pk=self.job.pk).update(
                    phase=phase.value, done_at=None if done is None else now())
                with patch('registry.tasks.harvest.import_run_message_state') as ask, \
                        patch.object(call_chord_md_metadata_file_to_db, 'delay') as rechord:
                    with self.assertRaises(SystemExit) as exited:
                        call_command('resume_harvesting_job', str(self.job.pk),
                                     stdout=self.out, stderr=self.err)
                self.assertEqual(1, exited.exception.code)
                ask.assert_not_called()
                rechord.assert_not_called()
            HarvestingJob.objects.filter(pk=self.job.pk).update(
                phase=Phase.RECORDS_TO_DB.value, done_at=None)

    def test_the_command_resumes_a_backlog_behind_an_empty_shadow(self):
        """no registered id at all is trivially no live run: the backlog of a
        job which nothing publishes anymore goes out as a fresh chord"""
        code, rechord = self._run(state=False)

        self.assertIsNone(code, self.err.getvalue())
        rechord.assert_called_once_with(harvesting_job_id=self.job.pk)
        self.assertIn('0 registered task ids', self.out.getvalue())
