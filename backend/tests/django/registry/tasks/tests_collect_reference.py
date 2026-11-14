"""What the collection learns when one registration reference is not stored.

The work-row consumer of #1263 answers a failing document along three lines:
whether the document gets another attempt, what the row keeps once the
attempts are over, and what the counters of the process do while its plan is
being decided. The failure handling of the deleted ``fetch_remote_metadata_xml``
(#1260) is ported onto the row here, and the row adds the answers the Remote
Metadata pk could not give: a machine-readable ``error_kind``, a stored
document where the failure left one, and a failed reference a delivery cannot
decide twice.

The tasks are answered through celery's tracer (``tests.django.utils``),
because the reports into the process and the retry which replaces the old
swallowed warning are sent by the same signal handlers a worker pays. The
retry publishes over a broker a test does not have, so its publication is
captured: what the tests assert is that the delivery handed the attempt back
to the policy instead of deciding about the document itself.
"""

import tempfile
from pathlib import Path
from unittest.mock import patch

from celery.app.trace import build_tracer
from django.test import TransactionTestCase, override_settings
from django.utils import timezone
from notify.enums import LogTypeEnum, ProcessStatusEnum
from notify.models import BackgroundProcess, BackgroundProcessLog
from registry.enums.metadata import ReferenceErrorKind, ReferenceWorkStateEnum
from registry.models.harvest import TemporaryMdMetadataFile
from registry.models.metadata import (MetadataContact,
                                      ServiceMetadataRecord)
from registry.models.service import WebMapService
from registry.tasks.service import collect_reference
from requests import Session
from requests.exceptions import ConnectionError, Timeout
from rest_framework.reverse import reverse as drf_reverse
from tests.django.utils import MockResponse, WorkerRunMixin

ISO_DATA = Path(__file__).parent.parent.parent / 'test_data/iso_metadata'
SERVICE_DOCUMENT = ISO_DATA / 'service.xml'
DATASET_DOCUMENT = ISO_DATA / 'dataset.xml'

LINK = 'http://metadata.example.org/record.xml'


@override_settings(CHANNEL_LAYERS={
    "default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}})
class CollectReferenceFailureTest(WorkerRunMixin, TransactionTestCase):
    """One work row, worked until its outcome - or an attempt - is answered."""

    def setUp(self):
        super().setUp()
        media = tempfile.TemporaryDirectory()
        self.addCleanup(media.cleanup)
        settings_override = override_settings(MEDIA_ROOT=media.name)
        settings_override.enable()
        self.addCleanup(settings_override.disable)

        contact = MetadataContact.objects.create(name='reference test contact')
        self.service = WebMapService.objects.create(
            title='Reference failure test service',
            version=130,
            origin=1,
            service_url='http://metadata.example.org/wms',
            metadata_contact=contact,
            service_contact=contact)
        # one sealed plan of exactly one reference, as the registration
        # leaves it behind when it publishes the fan-out
        self.process = BackgroundProcess.objects.create(
            phase='collect_metadata_records',
            process_type='registering',
            description='a registration which collects one document',
            total_steps=1,
            references_total=1, references_stored=0, references_failed=0,
            references_skipped=0, references_plan_sealed=True)
        self.row = self._planned_row()

    def _planned_row(self):
        """A PENDING work row of the sealed plan, inserted without dispatch."""
        row = TemporaryMdMetadataFile(
            background_process_id=self.process.pk,
            reference_key=TemporaryMdMetadataFile.build_reference_key(
                self.service, LINK),
            requested_url=LINK,
            described_wms=self.service,
            described_display=self.service.title,
            request_id=timezone.now())
        TemporaryMdMetadataFile.objects.bulk_create([row])
        return row

    # -- the delivery, answered the way a worker pays it --------------------

    def _answer(self, retries=0, allow_failed=False, send=None):
        """Deliver ``collect_reference`` for this row once through the tracer.

        ``send`` is the patched answer of the HTTP layer; the call goes with
        kwargs, which is how both the fan-out and the recovery address it.
        """
        collect_reference._backend = self.app.backend
        self.addCleanup(
            lambda: collect_reference.__dict__.pop('_backend', None))
        trace = build_tracer(
            collect_reference.name, collect_reference, app=self.app)
        task_kwargs = {
            'background_process_pk': str(self.process.pk),
            'temporary_md_metadata_file_id': self.row.pk,
        }
        if allow_failed:
            task_kwargs['allow_failed'] = True
        with patch.object(Session, 'send', side_effect=send):
            return trace(self.task_id, (), task_kwargs,
                         {'id': self.task_id, 'retries': retries})

    @staticmethod
    def _refused(request, *args, **kwargs):
        raise ConnectionError('connection refused')

    @staticmethod
    def _silent(request, *args, **kwargs):
        raise Timeout('the server stayed silent')

    @staticmethod
    def _answered(request, *args, **kwargs):
        return MockResponse(SERVICE_DOCUMENT, status_code=200)

    @staticmethod
    def _not_there(request, *args, **kwargs):
        return MockResponse('', status_code=404)

    # -- a transport failure is an attempt, not an outcome ------------------

    def test_a_silent_server_hands_the_attempt_back_to_the_policy(self):
        """Silence releases the row instead of deciding it (#1260, #1263).

        The attempt which is not the last one the policy allows raises back
        into the autoretry, the lease goes back so any delivery may work the
        row again, and no warning is written - a warning used to be the end
        of the document's story.
        """
        with patch.object(collect_reference, 'apply_async',
                          autospec=True) as apply_async:
            self._answer(send=self._silent)

        apply_async.assert_called_once()
        self.row.refresh_from_db()
        self.assertEqual(
            self.row.state, ReferenceWorkStateEnum.PENDING.value,
            msg='the released row must be claimable by the retried delivery')
        self.assertIsNone(self.row.claim_token)
        self.assertIsNone(self.row.lease_expires_at)
        # the claim counted the attempt, and only the attempt: the row's
        # ledger of attempts is what a recovery reads, not a broker message
        self.assertEqual(self.row.attempt_count, 1)
        self.assertEqual(self.row.error_kind, "")
        self.assertEqual(
            BackgroundProcessLog.objects.filter(
                background_process=self.process).count(), 0)
        self.process.refresh_from_db()
        self.assertEqual(self.process.references_failed, 0)
        self.assertEqual(self.process.done_steps, 0)

    def test_a_refused_connection_hands_the_attempt_back_too(self):
        """The other transient failure walks the same release path."""
        with patch.object(collect_reference, 'apply_async',
                          autospec=True) as apply_async:
            self._answer(send=self._refused)

        apply_async.assert_called_once()
        self.row.refresh_from_db()
        self.assertEqual(self.row.state, ReferenceWorkStateEnum.PENDING.value)
        self.process.refresh_from_db()
        self.assertEqual(self.process.done_steps, 0)

    def test_the_last_attempt_of_a_silent_server_decides_fetch_timeout(self):
        """The attempt the policy runs out of decides - and names which loss.

        The row keeps a machine-readable kind and a process-visible sentence
        saying the reference is kept and can be fetched again; the parent
        process is not failed by one reference (#1260).
        """
        self._answer(retries=collect_reference.max_retries,
                     send=self._silent)

        self.row.refresh_from_db()
        self.assertEqual(self.row.state, ReferenceWorkStateEnum.FAILED.value)
        self.assertEqual(self.row.error_kind,
                         ReferenceErrorKind.FETCH_TIMEOUT.value)
        self.assertIn('did not answer within', self.row.import_error)
        # a transport failure never reached a document: nothing is kept
        self.assertFalse(self.row.md_metadata_file.name)

        log = BackgroundProcessLog.objects.filter(
            background_process=self.process,
            log_type=LogTypeEnum.WARNING).get()
        self.assertIn('can be fetched again', log.description)

        self.process.refresh_from_db()
        self.assertEqual(self.process.status, ProcessStatusEnum.RUNNING)
        self.assertEqual(self.process.done_steps, 1)
        self.assertEqual(self.process.references_failed, 1)
        self.assertEqual(self.process.references_stored, 0)

    def test_the_last_attempt_of_a_refused_host_decides_fetch_unreachable(self):
        """The silence and the refusal stay apart - the fixers differ (#1260)."""
        self._answer(retries=collect_reference.max_retries,
                     send=self._refused)

        self.row.refresh_from_db()
        self.assertEqual(self.row.error_kind,
                         ReferenceErrorKind.FETCH_UNREACHABLE.value)
        log = BackgroundProcessLog.objects.get(
            background_process=self.process,
            log_type=LogTypeEnum.WARNING)
        self.assertIn('could not be reached', log.description)
        self.process.refresh_from_db()
        self.assertEqual(self.process.references_failed, 1)

    # -- an answer is not a failure to retry ---------------------------------

    def test_an_answer_of_404_is_decided_without_another_attempt(self):
        """A link which is not there is not fetched by trying again.

        The delivery reads the answer, decides the row as ``no_content`` and
        returns - no attempt is published, because the next delivery would
        read the same 404 (#1260).
        """
        with patch.object(collect_reference, 'apply_async',
                          autospec=True) as apply_async:
            answer = self._answer(send=self._not_there)

        apply_async.assert_not_called()
        self.assertEqual(
            answer.retval,
            {"data": None, "outcome": None,
             "error_kind": ReferenceErrorKind.NO_CONTENT.value})

        self.row.refresh_from_db()
        self.assertEqual(self.row.state, ReferenceWorkStateEnum.FAILED.value)
        self.assertEqual(self.row.error_kind,
                         ReferenceErrorKind.NO_CONTENT.value)
        self.assertIn('404', self.row.import_error)
        self.assertFalse(self.row.md_metadata_file.name)

        log = BackgroundProcessLog.objects.get(
            background_process=self.process, log_type=LogTypeEnum.WARNING)
        self.assertIn('404', log.description)
        self.process.refresh_from_db()
        self.assertEqual(self.process.done_steps, 1)
        self.assertEqual(self.process.references_failed, 1)

    def test_a_kind_which_is_not_mapped_is_decided_and_keeps_its_file(self):
        """The unsupported kind names itself and leaves the document behind.

        The document was fetched - unlike the transport failures this row
        keeps the bytes which produced the decision, so whoever reads the
        failed reference can read what it claimed to be (#1260, #1263).
        """
        document = DATASET_DOCUMENT.read_text().replace(
            'codeListValue="dataset"',
            'codeListValue="nonGeographicDataset"')

        def answered(request, *args, **kwargs):
            return MockResponse(document, status_code=200)

        with patch.object(collect_reference, 'apply_async',
                          autospec=True) as apply_async:
            self._answer(send=answered)

        apply_async.assert_not_called()
        self.row.refresh_from_db()
        self.assertEqual(self.row.state, ReferenceWorkStateEnum.FAILED.value)
        self.assertEqual(self.row.error_kind,
                         ReferenceErrorKind.UNSUPPORTED_KIND.value)
        # the mapping names the kind it has no config for, lower-cased
        self.assertIn('nongeographicdataset', self.row.import_error)
        self.assertIn(f'reference-{self.row.pk}-',
                      self.row.md_metadata_file.name)
        file_storage = TemporaryMdMetadataFile._meta.get_field(
            'md_metadata_file').storage
        self.assertTrue(
            file_storage.exists(self.row.md_metadata_file.name),
            msg='the document which produced the decision must be readable')

        log = BackgroundProcessLog.objects.get(
            background_process=self.process, log_type=LogTypeEnum.WARNING)
        self.assertIn('nongeographicdataset', log.description.lower())
        self.process.refresh_from_db()
        self.assertEqual(self.process.done_steps, 1)
        self.assertEqual(self.process.references_failed, 1)

    # -- the decided row closes itself against redelivery --------------------

    def test_a_plain_redelivery_never_reopens_a_failed_reference(self):
        """A decided failure waits for the authorization of #1265 (#1263).

        The delivery of the original fan-out which arrives after the decision
        - a redriven queue, a replayed chord member - claims nothing, moves
        no counter and does not touch the row's decision.
        """
        self._answer(retries=collect_reference.max_retries,
                     send=self._refused)
        self.row.refresh_from_db()
        decided_at = self.row.error_at

        with patch.object(collect_reference, 'apply_async',
                          autospec=True) as apply_async:
            # retries=max_retries: the rejected delivery withdraws instead of
            # waiting out another bounded retry
            self._answer(retries=collect_reference.max_retries,
                         send=self._answered)

        apply_async.assert_not_called()
        self.row.refresh_from_db()
        self.assertEqual(self.row.error_kind,
                         ReferenceErrorKind.FETCH_UNREACHABLE.value)
        self.assertEqual(self.row.error_at, decided_at)
        # the claim was refused, so no attempt was counted either
        self.assertEqual(self.row.attempt_count, 1)
        self.assertEqual(ServiceMetadataRecord.objects.count(), 0)
        self.process.refresh_from_db()
        self.assertEqual(self.process.references_failed, 1)
        self.assertEqual(self.process.references_stored, 0)

    # -- the authorized retry after the process decided itself ---------------

    def _complete_the_process_as_failed_once(self):
        """The shape a decided run leaves behind: COMPLETED, one failed."""
        self._answer(retries=collect_reference.max_retries,
                     send=self._not_there)
        BackgroundProcess.objects.filter(pk=self.process.pk).update(
            status=ProcessStatusEnum.COMPLETED,
            done_at=timezone.now(),
            phase='completed')
        self.process.refresh_from_db()
        self.assertEqual(self.process.references_failed, 1)
        return self.process.done_at

    def test_a_manual_retry_of_a_failed_reference_moves_the_counters_back(self):
        """A stored retry shifts the last-outcome counters, not the plan.

        The line #1265 will start over from: the same row, worked under the
        authorization of ``allow_failed``. ``stored`` rises, ``failed`` falls,
        ``done_steps`` and ``references_total`` stay where the sealed plan
        put them, and the COMPLETED process is not reopened - its summary
        just changes with the reference which resolved (#1263, D3).
        """
        finished_at = self._complete_the_process_as_failed_once()

        answer = self._answer(allow_failed=True, send=self._answered)

        record = ServiceMetadataRecord.objects.get()
        self.assertEqual(
            answer.retval["data"]["links"]["self"],
            drf_reverse('registry:servicemetadata-detail', args=[record.pk]))
        self.assertFalse(
            TemporaryMdMetadataFile.objects.filter(pk=self.row.pk).exists(),
            msg='the stored reference is consumed - its absence is the proof')

        self.process.refresh_from_db()
        self.assertEqual(self.process.status, ProcessStatusEnum.COMPLETED)
        self.assertEqual(self.process.done_at, finished_at)
        self.assertEqual(self.process.done_steps, 1)
        self.assertEqual(self.process.references_total, 1)
        self.assertEqual(self.process.references_stored, 1)
        self.assertEqual(self.process.references_failed, 0)

    def test_a_manual_retry_which_fails_again_moves_no_counters(self):
        """The retried reference that fails again keeps its single counting.

        Its first decision already counted it once as failed; an attempt
        below the same row's ledger must not double it, or push ``done_steps``
        past the plan (#1263).
        """
        finished_at = self._complete_the_process_as_failed_once()

        self._answer(retries=collect_reference.max_retries,
                     allow_failed=True, send=self._refused)

        self.row.refresh_from_db()
        self.assertEqual(self.row.state, ReferenceWorkStateEnum.FAILED.value)
        self.assertEqual(self.row.error_kind,
                         ReferenceErrorKind.FETCH_UNREACHABLE.value)
        # the attempt was counted; the decision was not moved a second time
        self.assertEqual(self.row.attempt_count, 2)

        self.process.refresh_from_db()
        self.assertEqual(self.process.references_failed, 1)
        self.assertEqual(self.process.references_stored, 0)
        self.assertEqual(self.process.done_steps, 1)
        self.assertEqual(self.process.status, ProcessStatusEnum.COMPLETED)
        self.assertEqual(self.process.done_at, finished_at)
