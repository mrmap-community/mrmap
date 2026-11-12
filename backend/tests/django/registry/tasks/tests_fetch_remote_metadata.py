"""What a registration learns when one of its metadata documents is not collected.

``fetch_remote_metadata_xml`` answers as a member of a chord below the process
which a registration polls, so the failure handling of one document answers two
questions at once: whether the document gets another attempt, and what the
process keeps once the attempts are over. Before #1260 both answers were the
same for every failure - a warning which the task then swallowed, so a document
which was unreachable for ten seconds was given up for the whole registration
with no second attempt and no retry anybody could start.

The tasks are answered through celery's tracer (``tests.django.utils``), because
the reports into the process and the retry which replaces the warning are sent
by the same signal handlers a worker pays. The retried attempt is published over
a broker a test does not have, so its publication is captured instead: what the
test asserts is that the task handed the attempt back to the policy instead of
deciding about the document itself.
"""

from pathlib import Path
from unittest.mock import patch

from celery.app.trace import build_tracer
from django.test import TransactionTestCase, override_settings
from notify.enums import LogTypeEnum, ProcessStatusEnum
from notify.models import BackgroundProcess, BackgroundProcessLog
from registry.exceptions.metadata import (MetadataFetchTimeout,
                                          MetadataFetchUnreachable)
from registry.exceptions.service import NoContent
from registry.models.metadata import (MetadataContact,
                                      WebMapServiceRemoteMetadata)
from registry.models.service import WebMapService
from registry.tasks.service import fetch_remote_metadata_xml
from tests.django.utils import WorkerRunMixin

DATASET_DOCUMENT = (
    Path(__file__).parent.parent.parent / 'test_data/iso_metadata/dataset.xml')


@override_settings(CHANNEL_LAYERS={
    "default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}})
class FetchRemoteMetadataFailureTest(WorkerRunMixin, TransactionTestCase):
    """One document of a collection, answered until its outcome is decided."""

    def setUp(self):
        super().setUp()
        contact = MetadataContact.objects.create(name='Retry test contact')
        self.service = WebMapService.objects.create(
            title='Metadata retry test service',
            version=130,
            origin=1,
            service_url='http://metadata.example.org/wms',
            metadata_contact=contact,
            service_contact=contact)
        self.remote_metadata = WebMapServiceRemoteMetadata.objects.create(
            describes=self.service,
            link='http://metadata.example.org/record.xml')
        self.process = BackgroundProcess.objects.create(
            phase='collecting metadata records...',
            process_type='registering',
            description='a registration which collects one document')

    # -- the answers of one delivery -----------------------------------------

    def test_a_document_which_was_not_answered_is_handed_to_the_retry(self):
        """Silence retries instead of being logged away.

        The attempt which is not the last one the policy allows raises, because
        only a raised exception is a case ``autoretry_for`` applies to: the
        retried attempt is published, the process reports itself as retrying
        (#1207) and no warning is written - the warning used to be the end of
        the document's story (#1260).
        """
        with patch.object(
                WebMapServiceRemoteMetadata, 'fetch_remote_content',
                side_effect=MetadataFetchTimeout(
                    'The server did not answer within 15 seconds.')), \
                patch.object(fetch_remote_metadata_xml.app, 'send_task',
                             autospec=True) as send_task:
            self._answer_the_fetch()

        send_task.assert_called_once()
        self.assertEqual(send_task.call_args.args[0],
                         fetch_remote_metadata_xml.name)
        self.assertEqual(send_task.call_args.kwargs['retries'], 1)

        logs = BackgroundProcessLog.objects.filter(background_process=self.process)
        self.assertEqual(logs.count(), 0, '\n'.join(logs.values_list('description', flat=True)))
        self.process.refresh_from_db()
        self.assertEqual(self.process.status, ProcessStatusEnum.RUNNING)
        self.assertEqual(self.process.done_steps, 0)
        self.assertEqual(self.process.retry_count, 1)

    def test_a_refused_connection_is_handed_to_the_retry_too(self):
        """The other transient failure is retried by the same policy."""
        with patch.object(
                WebMapServiceRemoteMetadata, 'fetch_remote_content',
                side_effect=MetadataFetchUnreachable(
                    'The server behind the link could not be reached.')), \
                patch.object(fetch_remote_metadata_xml.app, 'send_task',
                             autospec=True) as send_task:
            self._answer_the_fetch()

        send_task.assert_called_once()
        self.assertEqual(
            BackgroundProcessLog.objects.filter(
                background_process=self.process).count(), 0)
        self.process.refresh_from_db()
        self.assertEqual(self.process.retry_count, 1)

    def test_the_last_attempt_records_the_failure_it_could_not_fix(self):
        """The attempt the policy runs out of writes the failure instead.

        The reference is recorded as failed with its reason, and the record
        says the document can be fetched again - which is the half #1263 makes
        a work row of, and the half which was missing when the failure was a
        warning nobody could act on. The registration which waits for this one
        document is not failed by it (#1260).
        """
        with patch.object(
                WebMapServiceRemoteMetadata, 'fetch_remote_content',
                side_effect=MetadataFetchTimeout(
                    'The server behind http://metadata.example.org/record.xml'
                    ' did not answer within 15 seconds.')), \
                patch.object(fetch_remote_metadata_xml.app, 'send_task',
                             autospec=True) as send_task:
            self._answer_the_fetch(
                retries=fetch_remote_metadata_xml.max_retries)

        send_task.assert_not_called()

        log = BackgroundProcessLog.objects.get(background_process=self.process)
        self.assertEqual(log.log_type, LogTypeEnum.WARNING)
        self.assertIn('did not answer within', log.description)
        self.assertIn('can be fetched again', log.description)

        self.process.refresh_from_db()
        self.assertEqual(self.process.status, ProcessStatusEnum.RUNNING)
        self.assertEqual(self.process.done_steps, 1)

    def test_the_failure_of_an_unreachable_host_names_the_host(self):
        """The stored sentence of a refused connection is not the silence one.

        Both failures are transient, neither of them is fixed by the same
        person as the other, so the row which keeps them apart is part of the
        fix (#1260).
        """
        with patch.object(
                WebMapServiceRemoteMetadata, 'fetch_remote_content',
                side_effect=MetadataFetchUnreachable(
                    'The server behind the link could not be reached: '
                    'connection refused')), \
                patch.object(fetch_remote_metadata_xml.app, 'send_task',
                             autospec=True):
            self._answer_the_fetch(
                retries=fetch_remote_metadata_xml.max_retries)

        log = BackgroundProcessLog.objects.get(background_process=self.process)
        self.assertIn('could not be reached', log.description)

    # -- an answer is not a failure to retry -------------------------------

    def test_an_answer_of_404_is_recorded_without_another_attempt(self):
        """A link which is not there is not fetched by trying again.

        Recorded, counted and not retried - and with the status which was
        answered, which is what keeps this row apart from the row of a server
        which never answered (#1260).
        """
        with patch.object(
                WebMapServiceRemoteMetadata, 'fetch_remote_content',
                side_effect=NoContent(
                    'Can\'t fetch content from remote for RemoteMetadata: the'
                    ' server answered with status 404.')), \
                patch.object(fetch_remote_metadata_xml.app, 'send_task',
                             autospec=True) as send_task:
            self._answer_the_fetch()

        send_task.assert_not_called()

        log = BackgroundProcessLog.objects.get(background_process=self.process)
        self.assertEqual(log.log_type, LogTypeEnum.WARNING)
        self.assertIn('404', log.description)
        self.process.refresh_from_db()
        self.assertEqual(self.process.done_steps, 1)

    def test_a_kind_which_is_not_mapped_is_recorded_and_not_retried(self):
        """The unsupported kind reaches the branch which names it again.

        The document is fetched and read; what it says it is, Mr. Map has no
        mapping for. The kind the document names is stored, and no attempt is
        scheduled: the next attempt would read the same kind (#1260, which also
        removed the branch which could never run).
        """
        self.remote_metadata.remote_content = self._an_unsupported_document()
        self.remote_metadata.save()

        with patch.object(WebMapServiceRemoteMetadata,
                          'fetch_remote_content') as fetch, \
                patch.object(fetch_remote_metadata_xml.app, 'send_task',
                             autospec=True) as send_task:
            self._answer_the_fetch()

        fetch.assert_called_once()
        send_task.assert_not_called()

        log = BackgroundProcessLog.objects.get(background_process=self.process)
        self.assertEqual(log.log_type, LogTypeEnum.WARNING)
        self.assertIn('nongeographicdataset', log.description)
        self.process.refresh_from_db()
        self.assertEqual(self.process.status, ProcessStatusEnum.RUNNING)
        self.assertEqual(self.process.done_steps, 1)

    # -- the delivery of one task ------------------------------------------

    def _answer_the_fetch(self, retries=0):
        """Answer one delivery of the real fetch task the way a worker would.

        ``retries`` is the count of retries the message carries with it, which
        is how a worker hands over the attempt number; the delivery which
        exhausted the task's own policy is the one which carries
        ``max_retries``.
        """
        task = fetch_remote_metadata_xml
        old_backend = task.__dict__.get('_backend')
        task._backend = self.app.backend
        self.addCleanup(setattr, task, '_backend', old_backend)
        trace = build_tracer(task.name, task, app=self.app)
        return trace(self.task_id,
                     (self.remote_metadata.pk, 'WebMapServiceRemoteMetadata'),
                     {'background_process_pk': str(self.process.pk)},
                     {'id': self.task_id, 'retries': retries})

    def _an_unsupported_document(self):
        """The dataset document of the tests, with a kind nothing maps.

        The mapping configs answer ``dataset``, ``service`` and ``application``;
        a document which names a scope outside of them is the case the kind is
        asked for (#1260).
        """
        return DATASET_DOCUMENT.read_text().replace(
            'codeListValue="dataset"',
            'codeListValue="nonGeographicDataset"')
