"""The queue separation of #970 and the dedup of the import chord publish.

`db-routines` used to carry the floodable import backlog of a harvest and
everything that has to answer quickly on one redis list: behind a catalogue
which fills it, the chord control, ``finish_background_process`` and the
beat-scheduled tasks starved for the ~17 h the backlog took to drain. These
tests hold both halves of the fix:

* the routing map - every task in question resolves, through the celery app
  the workers route with, onto the queue of its role, the beat-scheduled
  tasks onto queues a harvest can not fill, and the worker commands of the
  deployment keep consuming every queue the settings declare (a queue
  without a consumer is exactly the starvation this issue is about; #1040
  took away the hand-copied -Q list which could drift behind a release);
* the dedup - ``call_chord_md_metadata_file_to_db`` must not be published a
  second time for a job while one of its messages still waits. The question
  is asked of the broker through the same paged reads #972's
  ``import_run_message_state`` established, so the probes run against the
  same fakes (reused from the staleness module).
"""

import base64
import json
import os
import re
from tempfile import TemporaryDirectory
from unittest.mock import patch
from uuid import uuid4

from django.conf import settings
from django.core.files.base import ContentFile
from django.test import TestCase, override_settings
from django_celery_beat.models import PeriodicTask
from MrMap import celery_queues
from MrMap.celery import app
from MrMap.settings import CELERY_TASK_QUEUES
# importing the task modules registers the tasks the router resolves
import notify.tasks  # noqa: F401  (registers finish_background_process)
import system.tasks  # noqa: F401  (registers delete_old_slow_request_dumps)
from registry.enums.harvesting import HarvestingPhaseEnum as Phase
from registry.enums.harvesting import LogLevelEnum
from registry.models.harvest import HarvestingJob, TemporaryMdMetadataFile
from registry.tasks.harvest import (call_chord_md_metadata_file_to_db,
                                    chord_publish_message_state,
                                    recover_harvesting_jobs)
from tests.django.registry.tasks.tests_harvest_recovery_staleness import \
    FakeRedisClient

# what the worker commands must consume on top of the queue names of #972
from tests.django.registry.tasks.tests_harvest_recovery_staleness import \
    _broker_connection


def _chord_message(job_id, task_id=None):
    """One publish of the import chord, serialized the way the redis transport
    keeps it on its list: the protocol-2 envelope names the task in its
    headers and the job in the base64 body - the one read deeper than the
    correlation_id probe of #972, because the publishing recovery does not
    know a task id in advance (#970)."""
    return json.dumps({
        'body': base64.b64encode(json.dumps(
            [[], {'harvesting_job_id': job_id}, None]).encode()).decode(),
        'content-encoding': 'base64',
        'content-type': 'application/json',
        'headers': {
            'task': 'registry.tasks.harvest.call_chord_md_metadata_file_to_db'},
        'properties': {'correlation_id': str(task_id or uuid4()),
                       'delivery_tag': 'x'},
    }).encode()


def _queue_of(task_name):
    """The queue the celery app would send this task to: apply_async
    consults the task's own declaration (this project has no routes), and
    the app's queue table only answers queues it actually declares."""
    task = app.tasks[task_name]
    return app.amqp.queues[task.queue].name


class RoutingMapTest(TestCase):
    """Task -> queue, answered by the celery app and not by the source text."""

    EXPECTED = {
        # the floodable import backlog: one message per file or per chunk
        'registry.tasks.harvest.call_md_metadata_file_to_db': celery_queues.HARVEST_IMPORT,
        'registry.tasks.harvest.call_md_metadata_files_to_db': celery_queues.HARVEST_IMPORT,
        # the chord control and the callbacks which must stay reachable while
        # that backlog drains (#970)
        'registry.tasks.harvest.call_chord_md_metadata_file_to_db': celery_queues.DB_ROUTINES,
        'registry.tasks.harvest.finish_harvesting_job': celery_queues.DB_ROUTINES,
        'notify.tasks.finish_background_process': celery_queues.DB_ROUTINES,
        # the beat-scheduled tasks: starved for 16 h behind the backlog (#970)
        'registry.tasks.harvest.check_for_files_to_import': celery_queues.DB_ROUTINES,
        'system.tasks.delete_old_slow_request_dumps': celery_queues.DB_ROUTINES,
        # the harvest tasks which were on their own queues already
        'registry.tasks.harvest.call_fetch_records': celery_queues.DOWNLOAD,
        'registry.tasks.harvest.call_fetch_total_records': celery_queues.DEFAULT,
        'registry.tasks.harvest.recover_harvesting_jobs': celery_queues.DEFAULT,
        'registry.tasks.harvest.create_harvesting_job': celery_queues.DEFAULT,
    }

    def test_every_task_routes_onto_the_queue_of_its_role(self):
        for task_name, queue in self.EXPECTED.items():
            with self.subTest(task=task_name):
                self.assertEqual(_queue_of(task_name), queue)

    def test_the_backlog_queue_carries_nothing_but_the_backlog(self):
        """the starved messages of the issue must not just move onto another
        shared queue - none of the quick tasks may end up on harvest-import"""
        for task_name in self.EXPECTED:
            if task_name.endswith(
                    ('call_md_metadata_file_to_db', 'call_md_metadata_files_to_db')):
                continue
            with self.subTest(task=task_name):
                self.assertNotEqual(
                    _queue_of(task_name), celery_queues.HARVEST_IMPORT)

    def test_every_routed_task_lands_on_a_declared_queue(self):
        declared = {queue.name for queue in CELERY_TASK_QUEUES}
        self.assertIn(celery_queues.HARVEST_IMPORT, declared)
        for task_name in self.EXPECTED:
            with self.subTest(task=task_name):
                self.assertIn(_queue_of(task_name), declared)

    def test_the_beat_scheduled_tasks_reach_their_queues(self):
        """beat sends through the task declarations (there are no routes), so
        every periodic task the migration creates must resolve onto a queue
        a harvest can not fill - the 193 unconsumed check_for_files_to_import
        messages of the issue are the failure this guards"""
        declared = {queue.name for queue in CELERY_TASK_QUEUES}
        scheduled = PeriodicTask.objects.exclude(task='').values_list('task', flat=True)
        self.assertTrue(len(list(scheduled)) > 0, 'the migrations create beat tasks')
        for task_name in PeriodicTask.objects.exclude(task='').values_list('task', flat=True):
            with self.subTest(task=task_name):
                queue = _queue_of(task_name)
                self.assertIn(queue, declared)
                self.assertNotEqual(queue, celery_queues.HARVEST_IMPORT)

    def test_the_worker_commands_consume_every_declared_queue(self):
        """a queue which no worker consumes is the starvation of #970 seen
        from the other side.

        Since #1040 the guard is the absence of the -Q list: a worker
        command without it consumes everything the app declares, so these
        files cannot lag a release which added a queue behind a
        hand-copied list. A queue list on a worker command of these files
        is that drift again, whatever names it carries today; a deployment
        which deliberately splits its workers keeps the list in its own
        override, where the start-up check of MrMap.celery names what it
        strands."""
        root = os.path.dirname(settings.BASE_DIR)
        compose = 'docker-compose.yml'
        if not os.path.isfile(os.path.join(root, compose)):
            # the test services mount only backend/ (see docker-compose.dev.yml),
            # so inside a container this guard cannot see the deployment files;
            # it runs wherever the repository root is visible, and the
            # pre-submit loop of #970 checked it on the host as well
            self.skipTest(f'{compose} is not visible below {root}')
        for name in (compose, 'docker-compose.dev.yml', 'docker-compose.vscode.yml'):
            with open(os.path.join(root, name)) as file:
                lines = file.read().splitlines()
            # only the worker's own command lines: a comment may name the
            # option while explaining why the command does not carry it
            commands = [line for line in lines
                        if 'celery -A MrMap worker' in line
                        and not line.lstrip().startswith('#')]
            restated = set()
            for line in commands:
                for match in re.finditer(r'--?(?:Q|queues)[=\s]+([\w,. -]+)', line):
                    restated.update(
                        token for token in
                        match.group(1).replace(',', ' ').split() if token)
            with self.subTest(compose=name):
                self.assertTrue(commands, f'{name} declares no celery worker command')
                self.assertFalse(
                    restated,
                    f'{name} restates {sorted(restated)} on the worker command; '
                    f'a command without -Q consumes the queues the app declares '
                    f'and cannot be half-installed (#1040)')


class ChordRoutingTest(TestCase):
    """Chords publish members and callback through one call - the queues of
    the two halves must still separate, on the redis list as on paper (#970)."""

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

    def test_the_import_chord_members_and_callback_route_apart(self):
        with patch.object(HarvestingJob, '_http_request', return_value=None), \
                patch('registry.tasks.harvest.chord') as mocked_chord, \
                self.captureOnCommitCallbacks(execute=True):
            call_chord_md_metadata_file_to_db.run(harvesting_job_id=self.job.pk)
        members, callback = mocked_chord.call_args.args
        self.assertTrue(members, 'the chord was built')
        for member in members:
            self.assertEqual(
                _queue_of(member.name),
                celery_queues.HARVEST_IMPORT)
        self.assertEqual(
            _queue_of(callback.name),
            celery_queues.DB_ROUTINES)


class ImportChordPublishStateTest(TestCase):
    """The broker answer about a pending chord publish: pending, absent, unknown."""

    def _state_of(self, client, job_id):
        with patch.object(app, 'connection_for_read',
                          return_value=_broker_connection(client)):
            return chord_publish_message_state(job_id)

    def test_a_pending_publish_of_the_job_is_found(self):
        for queue in ('default', 'download', 'db-routines', 'harvest-import'):
            with self.subTest(queue=queue):
                client = FakeRedisClient({queue: [_chord_message(7)]})
                self.assertIs(True, self._state_of(client, 7))

    def test_an_unacked_publish_is_found(self):
        """the chord control acks late, so a publish a worker is working is
        still pending until it reports in"""
        for key, read in (('unacked', 'lrange'), ('unacked_index', 'zrange')):
            with self.subTest(key=key):
                self.assertIs(True, self._state_of(
                    FakeRedisClient({key: [_chord_message(7)]}), 7))

    def test_a_publish_of_another_job_answers_absent(self):
        """the control messages are per job; the pile-up the issue measured
        must not make one job hold every other job's chord hostage"""
        self.assertIs(False, self._state_of(
            FakeRedisClient({'db-routines': [_chord_message(8)]}), 7))

    def test_the_backlog_messages_answer_absent(self):
        """the queue may be full of the very job's import backlog - that is
        the state recovery is asked about, and it is not a pending publish"""
        client = FakeRedisClient({'harvest-import': [
            json.dumps({'headers': {
                'task': 'registry.tasks.harvest.call_md_metadata_files_to_db'},
                'properties': {'correlation_id': str(uuid4())}}).encode()
            for _ in range(4)]})
        self.assertIs(False, self._state_of(client, 7))

    def test_a_broker_holding_nothing_answers_absent(self):
        self.assertIs(False, self._state_of(FakeRedisClient(), 7))

    def test_a_message_that_names_nothing_answers_unknown(self):
        """#972's stance carried over: an unreadable message must not count
        as no pending publish - publishing blindly onto it is the pile-up"""
        self.assertIsNone(self._state_of(
            FakeRedisClient({'db-routines': [b'not a celery message']}), 7))

    def test_a_chord_publish_whose_body_cannot_be_read_answers_unknown(self):
        message = json.dumps({
            'body': 'not even base64',
            'headers': {'task': 'registry.tasks.harvest.call_chord_md_metadata_file_to_db'},
            'properties': {'correlation_id': str(uuid4())},
        }).encode()
        self.assertIsNone(self._state_of(FakeRedisClient({'db-routines': [message]}), 7))

    def test_a_broker_that_cannot_be_read_answers_unknown(self):
        self.assertIsNone(self._state_of(
            FakeRedisClient(errors=('db-routines',)), 7))

    def test_a_broker_that_cannot_be_connected_answers_unknown(self):
        with patch.object(app, 'connection_for_read',
                          side_effect=ConnectionError('the broker is offline')):
            self.assertIsNone(chord_publish_message_state(7))

    def test_a_broker_without_queue_introspection_answers_unknown(self):
        with patch.object(app, 'connection_for_read',
                          return_value=_broker_connection(None)):
            self.assertIsNone(chord_publish_message_state(7))


class PendingChordPublishRecoveryTest(TestCase):
    """Recovery declines a duplicate chord publish and says so on the job."""

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

    def _recover(self, client):
        """recover_harvesting_jobs over an empty shadow with the given broker;
        the no-shadow branch is where the chord goes out (#891)"""
        with patch.object(app, 'connection_for_read',
                          return_value=_broker_connection(client)), \
                patch.object(call_chord_md_metadata_file_to_db, 'delay') as publish:
            recover_harvesting_jobs.run()
        return publish

    def test_a_waiting_publish_is_not_duplicated(self):
        """the measured pile-up: five copies of the control message behind the
        backlog, one per worker restart; while one waits, restarts add none"""
        publish = self._recover(FakeRedisClient(
            {'db-routines': [_chord_message(self.job.pk)]}))
        publish.assert_not_called()
        log = self.job.logs.latest('pk')
        self.assertEqual(log.level, LogLevelEnum.INFO.value)
        self.assertIn('worker restart recovery', log.description)
        self.assertIn('still pending', log.description)

    def test_a_publish_of_another_job_does_not_hold_this_one_back(self):
        publish = self._recover(FakeRedisClient(
            {'db-routines': [_chord_message(self.job.pk + 1000)]}))
        publish.assert_called_once_with(harvesting_job_id=self.job.pk)

    def test_a_stranded_job_is_rechorded_when_no_publish_waits(self):
        publish = self._recover(FakeRedisClient())
        publish.assert_called_once_with(harvesting_job_id=self.job.pk)
        self.assertFalse(self.job.logs.exists(),
                         'the plain resume path publishes without preaching')

    def test_an_unaskable_broker_declines_visibly(self):
        """publishing a second backlog onto a broker which might already hold
        a publish of it is the risk of #891 - so the job waits visibly, with
        the operator path named on it"""
        publish = self._recover(FakeRedisClient(errors=('db-routines',)))
        publish.assert_not_called()
        log = self.job.logs.latest('pk')
        self.assertEqual(log.level, LogLevelEnum.WARNING.value)
        self.assertIn('could not answer', log.description)
        self.assertIn(f'resume_harvesting_job {self.job.pk}', log.description)
