"""Documents advertised identically are pulled once per collection run (#1410).

The capabilities of a service often advertise one ISO document from many
references - the service-level reference and every Layer or FeatureType
pointing at the same url. #1263 made each reference its own work row, which
is what the outcome, the retry of #1265 and the API need; #1410 stops the
HTTP request from multiplying with them: one acquisition row per distinct
advertised url of a run carries the fetch permit and the stored document,
and every other reference of that identity imports a copy under its own
claim and keeps its own outcome.

The acceptance list this module pins:

* identical advertisement pays exactly one request; each reference still
  stores, couples its own element and moves its own counters;
* urls whose query differs are different requests and never collapse into
  one acquisition;
* a waiter imports the stored copy without paying a second request;
* a fetch failure decides every still-open reference of the identity once,
  each keeping its own row, kind and counters, and the identity stays
  retryable through the very same acquisition;
* an expired fetch lease is taken over; the run's completion waits while a
  fetch is leased; recovery drains an acquisition no reference points at
  anymore and keeps the one a FAILED reference still retries through;
* a row without an acquisition (planned before #1410, or a retried
  reference whose acquisition drained) fetches its own document exactly the
  way #1263 always did.

Everything runs through the same tracer seam as the work-queue specs; the
HTTP layer is the patched ``requests.Session.send``.
"""

import tempfile
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from uuid import uuid4

from celery.app.trace import build_tracer
from django.core.files.base import ContentFile
from django.test import TransactionTestCase, override_settings
from django.utils import timezone
from mptt2.models import Tree
from notify.enums import ProcessStatusEnum
from notify.models import BackgroundProcess
from registry.enums.metadata import (DocumentAcquisitionStateEnum,
                                     MetadataOriginEnum,
                                     ReferenceErrorKind,
                                     ReferenceWorkStateEnum)
from registry.models.harvest import (RegistrationDocumentAcquisition,
                                     TemporaryMdMetadataFile)
from registry.models.metadata import (DatasetMetadataRecord,
                                      FeatureTypeRemoteMetadata,
                                      LayerRemoteMetadata, MetadataRelation)
from registry.models.service import (FeatureType, Layer, WebFeatureService,
                                     WebMapService)
from registry.tasks.service import (FINISH_WAIT_MAX_RETRIES,
                                    _decide_shared_fetch_failure,
                                    _wait_for_shared_document,
                                    collect_reference,
                                    finish_metadata_collection,
                                    plan_registration_references,
                                    recover_registration_reference_work)
from requests import Session
from requests.exceptions import ConnectionError
from tests.django.utils import MockResponse

ISO_DATA = Path(__file__).parent.parent.parent / 'test_data/iso_metadata'
DATASET = (ISO_DATA / 'dataset.xml').read_text()
FILE_IDENTIFIER = "de.dwd.geoserver.fach.RBSN_FF"

URL = 'http://metadata.example.org/layer.xml'
OTHER_URL = 'http://metadata.example.org/layer.xml?version=2'


class _PlanningTask:
    """Stand-in for the root task the planner reports its seal through."""

    def __init__(self, process):
        self.process = process

    def update_background_process(self, phase=None, service=None,
                                  total_steps=None, references_total=None,
                                  **kwargs):
        BackgroundProcess.objects.filter(pk=self.process.pk).update(
            total_steps=total_steps, references_total=references_total)


@override_settings(CHANNEL_LAYERS={
    "default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}})
class SharedDocumentAcquisitionTests(TransactionTestCase):
    """One identity, one request - and one honest outcome per reference."""

    fixtures = ["test_users.json", "test_keywords.json", "test_crs.json",
                "test_wms.json", "test_wfs.json"]

    def setUp(self):
        super().setUp()
        media = tempfile.TemporaryDirectory()
        self.addCleanup(media.cleanup)
        override = override_settings(MEDIA_ROOT=media.name)
        override.enable()
        self.addCleanup(override.disable)

        self.app_setup()
        self.wms = WebMapService.objects.first()
        self.assertIsNotNone(self.wms)
        self.layers = list(Layer.objects.filter(service=self.wms)[:1])
        self.assertEqual(
            len(self.layers), 1,
            'the wms fixture must leave at least one layer behind')
        # the sibling is created, not fixture-borrowed: which service
        # ``first()`` answers and how many layers it carries is the
        # fixture's business, and this spec compares references of one
        # service in every test (#1410)
        self.layers.append(Layer.objects.create(
            service=self.wms, title='shared acquisition sibling',
            identifier='shared-acquisition-sibling',
            mptt_tree=Tree.objects.create(), mptt_lft=1, mptt_rgt=2,
            mptt_depth=0))
        self.wfs = WebFeatureService.objects.first()
        self.feature_type = FeatureType.objects.filter(
            service=self.wfs).first()
        self.assertIsNotNone(self.feature_type,
                             'the wfs fixture must describe a feature type')
        self.process = BackgroundProcess.objects.create(
            process_type='registering', phase='collect_metadata_records',
            description='', references_plan_sealed=False)
        self.sends = []

    def app_setup(self):
        """The in-process celery app of ``WorkerRunMixin``.

        ``WorkerRunMixin`` builds it in ``setUp``; this class needs the
        fixtures loaded first, so the app is set up by an explicit call
        here instead of the mixin's inheritance order.
        """
        from celery import Celery
        self.app = Celery('shared-acq-test', set_as_current=False)
        self.addCleanup(self.app.close)
        self.app.conf.result_backend = 'cache+memory://'
        self.task_id = str(uuid4())

    # -- the seams ------------------------------------------------------------

    def _advertised(self, described, url=URL):
        model = (FeatureTypeRemoteMetadata
                 if isinstance(described, FeatureType)
                 else LayerRemoteMetadata)
        return model.objects.create(link=url, describes=described)

    def _plan(self, *advertised):
        return plan_registration_references(
            _PlanningTask(self.process), self.process.pk, list(advertised),
            self.wms)

    def _deliver(self, row_pk, send=None, retries=0, allow_failed=False):
        """Deliver ``collect_reference`` for one row through the tracer.

        The patched ``Session.send`` is recorded per delivery so a test can
        count requests across several deliveries of one plan.
        """
        collect_reference._backend = self.app.backend
        self.addCleanup(
            lambda: collect_reference.__dict__.pop('_backend', None))
        trace = build_tracer(
            collect_reference.name, collect_reference, app=self.app)
        task_kwargs = {
            'background_process_pk': str(self.process.pk),
            'temporary_md_metadata_file_id': row_pk,
        }
        if allow_failed:
            task_kwargs['allow_failed'] = True
        send_mock = Mock(side_effect=send) if send is not None \
            else Mock(side_effect=self._forbidden)
        self.sends.append(send_mock)
        with patch.object(Session, 'send', send_mock):
            return trace(self.task_id, (), task_kwargs,
                         {'id': self.task_id, 'retries': retries})

    def _send_count(self):
        return sum(mock.call_count for mock in self.sends)

    @staticmethod
    def _dataset(request, *args, **kwargs):
        return MockResponse(DATASET, status_code=200)

    @staticmethod
    def _refused(request, *args, **kwargs):
        raise ConnectionError('connection refused')

    @staticmethod
    def _not_there(request, *args, **kwargs):
        return MockResponse('', status_code=404)

    @staticmethod
    def _forbidden(request, *args, **kwargs):
        raise AssertionError(
            'a reference which can import the stored document must not '
            'ask the server again')

    def _finish(self, retries=0):
        finish_metadata_collection._backend = self.app.backend
        trace = build_tracer(
            finish_metadata_collection.name, finish_metadata_collection,
            app=self.app)
        return trace(finish_metadata_collection.name, (),
                     {'background_process_pk': str(self.process.pk)},
                     {'id': str(self.task_id), 'retries': retries})

    @staticmethod
    def _storage():
        return TemporaryMdMetadataFile._meta.get_field(
            "md_metadata_file").storage

    # -- acceptance: one identity, one request --------------------------------

    def test_identical_advertisement_pays_exactly_one_request(self):
        """Three references, one url, one fetch - and three own outcomes.

        Two layers and the feature type advertise the same document. The
        first delivery fetches it once, every delivery stores its own copy
        and couples its own element; the counters say three stored, and the
        acquisition drains with the last reference (#1410, acceptance 1).
        """
        sealed = self._plan(
            self._advertised(self.layers[0]),
            self._advertised(self.layers[1]),
            self._advertised(self.feature_type))
        self.assertEqual(len(sealed), 3)
        acquisitions = RegistrationDocumentAcquisition.objects.filter(
            background_process_id=self.process.pk)
        self.assertEqual(acquisitions.count(), 1,
                         msg='one url of one run is one acquisition')
        doc = acquisitions.get()
        self.assertTrue(
            TemporaryMdMetadataFile.objects.filter(
                background_process_id=self.process.pk, acquisition=doc)
            .count() == 3)

        for row_pk in sealed:
            self._deliver(row_pk, send=self._dataset)

        self.assertEqual(self._send_count(), 1,
                         msg='three references of one identity pay one '
                             'HTTP request between them')
        self.process.refresh_from_db()
        self.assertEqual(
            (self.process.references_total,
             self.process.references_stored, self.process.done_steps),
            (3, 3, 3))
        self.assertFalse(
            TemporaryMdMetadataFile.objects.filter(
                background_process_id=self.process.pk).exists())
        self.assertFalse(
            RegistrationDocumentAcquisition.objects.filter(
                pk=doc.pk).exists(),
            msg='the acquisition drains with its last reference')
        self.assertEqual(DatasetMetadataRecord.objects.filter(
            file_identifier=FILE_IDENTIFIER).count(), 1,
            msg='the identity rules of #982 still re-use one record')
        self.assertEqual(MetadataRelation.objects.filter(
            origin=MetadataOriginEnum.CAPABILITIES.value).count(), 3,
            msg='every element keeps its own coupling')

    def test_different_queries_are_different_acquisitions(self):
        """``?a=1`` and ``?a=1&b=2`` are two requests, never one (#1410).

        No normalization joins them: the contract is the exact advertised
        string, so a query which means a different request keeps its own
        acquisition - and its own fetch.
        """
        sealed = self._plan(
            self._advertised(self.layers[0], URL),
            self._advertised(self.layers[0], OTHER_URL))
        self.assertEqual(len(sealed), 2)
        self.assertEqual(
            RegistrationDocumentAcquisition.objects.filter(
                background_process_id=self.process.pk).count(), 2,
            msg='a different advertised url is a different identity')

        for row_pk in sealed:
            self._deliver(row_pk, send=self._dataset)

        self.assertEqual(self._send_count(), 2,
                         msg='the two identities pay their own request')
        self.process.refresh_from_db()
        self.assertEqual(self.process.references_stored, 2)

    def test_a_waiter_imports_the_stored_copy_without_asking_again(self):
        """The sibling of a stored acquisition never hits the server.

        After the first reference stored the document, the second delivery
        runs against a patched HTTP layer which answers any request with a
        failure: the import goes through the stored copy alone (#1410).
        """
        sealed = self._plan(
            self._advertised(self.layers[0]),
            self._advertised(self.layers[1]))
        self._deliver(sealed[0], send=self._dataset)
        self.assertEqual(self._send_count(), 1)

        # no send mock for this delivery: any request would raise
        self._deliver(sealed[1])

        self.process.refresh_from_db()
        self.assertEqual(
            (self.process.references_stored, self.process.done_steps), (2, 2))

    # -- acceptance: a failed fetch decides once, for everyone -----------------

    def test_an_exhausted_fetch_decides_every_open_reference(self):
        """The missing answer fails the identity together, row by row.

        With the acquisition's fetch budget spent, one more silence decides
        the fetching reference and every PENDING sibling with the same
        machine-readable kind - each its own row, its own counter - and the
        acquisition itself stays retryable through the same identity
        (#1410, keeping #1263's per-reference answer).
        """
        sealed = self._plan(
            self._advertised(self.layers[0]),
            self._advertised(self.layers[1]))
        doc = RegistrationDocumentAcquisition.objects.get(
            background_process_id=self.process.pk)
        # the budget of the identity is its claim count: spend it so the
        # next refused answer is the last attempt
        RegistrationDocumentAcquisition.objects.filter(
            pk=doc.pk).update(attempt_count=10)

        self._deliver(sealed[0], send=self._refused)

        rows = list(TemporaryMdMetadataFile.objects.filter(
            background_process_id=self.process.pk).order_by("pk"))
        self.assertEqual(len(rows), 2,
                         msg='a decided failure is kept, not consumed')
        for row in rows:
            self.assertEqual(row.state,
                             ReferenceWorkStateEnum.FAILED.value)
            self.assertEqual(row.error_kind,
                             ReferenceErrorKind.FETCH_UNREACHABLE.value)
        self.process.refresh_from_db()
        self.assertEqual(
            (self.process.references_failed, self.process.done_steps), (2, 2))
        doc.refresh_from_db()
        self.assertEqual(doc.state, DocumentAcquisitionStateEnum.PENDING.value,
                         msg='the identity stays open for the retry API')
        self.assertIsNone(doc.claim_token)
        self.assertEqual(doc.md_metadata_file.name, "")

    def test_no_content_decides_the_whole_identity_at_once(self):
        """An answer which is no document is read once and decided for all.

        A 404 without a body is not worth ten requests - it is decided for
        the fetcher and mirrored onto every open reference immediately,
        the posture of #1263 batched to the identity (#1410).
        """
        sealed = self._plan(
            self._advertised(self.layers[0]),
            self._advertised(self.layers[1]))

        self._deliver(sealed[0], send=self._not_there)

        self.assertEqual(self._send_count(), 1,
                         msg='the pointless answer is asked once')
        self.assertEqual(
            TemporaryMdMetadataFile.objects.filter(
                background_process_id=self.process.pk,
                state=ReferenceWorkStateEnum.FAILED.value,
                error_kind=ReferenceErrorKind.NO_CONTENT.value).count(), 2)
        self.process.refresh_from_db()
        self.assertEqual(self.process.references_failed, 2)

    # -- acceptance: leases and takeover ----------------------------------------

    def test_an_expired_fetch_lease_is_taken_over(self):
        """A fetcher which died hands the acquisition to a waiting sibling.

        The reference of a LEASE whose holder never reported can claim the
        acquisition again without waiting for the recovery; its fetch
        stores under the new token and imports normally (#1410).
        """
        sealed = self._plan(
            self._advertised(self.layers[0]),
            self._advertised(self.layers[1]))
        doc = RegistrationDocumentAcquisition.objects.get(
            background_process_id=self.process.pk)
        RegistrationDocumentAcquisition.objects.filter(pk=doc.pk).update(
            state=DocumentAcquisitionStateEnum.LEASED.value,
            claim_token=uuid4(),
            lease_expires_at=timezone.now() - timedelta(minutes=5))

        self._deliver(sealed[0], send=self._dataset)

        self.process.refresh_from_db()
        self.assertEqual(self.process.references_stored, 1)
        doc.refresh_from_db()
        self.assertEqual(doc.state, DocumentAcquisitionStateEnum.STORED.value,
                         msg='the sibling still reads from the taken-over '
                             'acquisition')

    def test_the_run_waits_while_a_fetch_is_leased(self):
        """Completion never lands under an in-flight fetch (#1410).

        A chord which answered through waiting references must not close
        the run while a delivery holds the fetch permit: the body waits,
        and the leased acquisition stays for the takeover.
        """
        self._plan(
            self._advertised(self.layers[0]),
            self._advertised(self.layers[1]))
        doc = RegistrationDocumentAcquisition.objects.get(
            background_process_id=self.process.pk)
        RegistrationDocumentAcquisition.objects.filter(pk=doc.pk).update(
            state=DocumentAcquisitionStateEnum.LEASED.value,
            claim_token=uuid4(),
            lease_expires_at=timezone.now() + timedelta(minutes=10))

        # the body's answer under a live fetch is one published wait
        # round - the shape a RETRY takes on a real worker is exactly
        # this delayed re-publish - and no completion: the run stays
        # open and the leased acquisition stays for the takeover.
        with patch.object(finish_metadata_collection, 'apply_async',
                          autospec=True) as apply_async:
            self._finish()
        self.assertEqual(apply_async.call_count, 1,
                         msg='the completion waited exactly one round for '
                             'the fetcher')
        self.assertTrue(apply_async.call_args.kwargs.get('countdown'),
                        msg='the wait round is delayed, not hot-looped')
        self.process.refresh_from_db()
        self.assertNotEqual(self.process.status, ProcessStatusEnum.COMPLETED)

        # the fetcher's death releases the permit: with nobody working the
        # references anymore, the completion closes the run and counts the
        # references which never answered - the acquisition of a still
        # pointing reference is nobody's to drain here (#1263 semantics)
        RegistrationDocumentAcquisition.objects.filter(pk=doc.pk).update(
            state=DocumentAcquisitionStateEnum.PENDING.value,
            claim_token=None, lease_expires_at=None)
        self._finish()
        self.process.refresh_from_db()
        self.assertEqual(self.process.status, ProcessStatusEnum.COMPLETED)
        self.assertEqual(self.process.references_skipped, 2,
                         msg='the references nobody worked are counted '
                             'skipped, exactly like #1259 always did')
        self.assertTrue(
            RegistrationDocumentAcquisition.objects.filter(
                pk=doc.pk).exists(),
            msg='the references still point at their identity')

    # -- acceptance: the recovery keeps its promises ---------------------------

    def test_recovery_drains_an_acquisition_nobody_points_at(self):
        """The crash residue of #1410 is reaped like every other orphan.

        An acquisition whose references all decided while its row and its
        stored copy stayed behind is drained by the hourly pass; the
        acquisition a FAILED reference still retries through is kept.
        """
        sealed = self._plan(self._advertised(self.layers[0]))
        keep = RegistrationDocumentAcquisition.objects.create(
            background_process_id=self.process.pk,
            acquisition_key='k' * 64,
            requested_url='http://metadata.example.org/keeper.xml',
            request_id=timezone.now())
        TemporaryMdMetadataFile.objects.filter(pk=sealed[0]).update(
            state=ReferenceWorkStateEnum.FAILED.value,
            error_kind=ReferenceErrorKind.IMPORT_FAILED.value,
            error_at=timezone.now(),
            acquisition=keep)
        # a stored acquisition whose bytes stayed behind while no
        # reference ever pointed at it - the shape a crashed fetch leaves
        orphan = RegistrationDocumentAcquisition.objects.create(
            background_process_id=self.process.pk,
            acquisition_key='o' * 64,
            requested_url='http://metadata.example.org/orphan.xml',
            request_id=timezone.now())
        orphan.md_metadata_file.save(
            'document-residue.xml', ContentFile(b'<orphan/>'), save=True)
        orphan_name = orphan.md_metadata_file.name

        with patch.object(collect_reference, 'apply_async', autospec=True), \
                patch.object(finish_metadata_collection, 'apply_async',
                             autospec=True):
            summary = recover_registration_reference_work.run()

        # the planned acquisition lost its only reference to the keeper and
        # is residue itself; the orphan is the second - both go, the keeper
        # stays
        self.assertEqual(summary['drained'], 2)
        self.assertFalse(
            RegistrationDocumentAcquisition.objects.filter(
                pk=orphan.pk).exists())
        self.assertFalse(self._storage().exists(orphan_name))
        self.assertTrue(
            RegistrationDocumentAcquisition.objects.filter(
                pk=keep.pk).exists(),
            msg='a retryable failed reference keeps its identity')

    # -- acceptance: rows without an acquisition keep the old answer ------------

    def test_a_row_without_an_acquisition_fetches_its_own_document(self):
        """Legacy rows walk the #1263 path untouched by #1410.

        A row inserted without an acquisition - one planned before this
        feature, or a retried reference whose acquisition drained - pays
        its own request and stores under its own claim token.
        """
        BackgroundProcess.objects.filter(pk=self.process.pk).update(
            references_plan_sealed=True, total_steps=1, references_total=1)
        row = TemporaryMdMetadataFile(
            background_process_id=self.process.pk,
            reference_key=TemporaryMdMetadataFile.build_reference_key(
                self.layers[0], URL),
            requested_url=URL,
            described_layer=self.layers[0],
            request_id=timezone.now())
        TemporaryMdMetadataFile.objects.bulk_create([row])

        self._deliver(row.pk, send=self._dataset)

        self.process.refresh_from_db()
        self.assertEqual(self.process.references_stored, 1)
        self.assertEqual(self._send_count(), 1)
        self.assertFalse(
            RegistrationDocumentAcquisition.objects.filter(
                background_process_id=self.process.pk).exists(),
            msg='the legacy path creates no acquisition')

    # -- acceptance: a refused sweep or waiter answers for the next pass ------

    def test_a_refused_drain_keeps_rows_and_bytes_for_the_next_pass(self):
        """A drain which cannot delete loses nothing (#1410).

        When the bulk delete of the residue refuses, neither the rows nor
        their bytes are touched: the pass reports nothing drained and the
        next pass reads the very same shape again.
        """
        self._plan(self._advertised(self.layers[0]))
        orphan = RegistrationDocumentAcquisition.objects.create(
            background_process_id=self.process.pk,
            acquisition_key='d' * 64,
            requested_url='http://metadata.example.org/drain-refused.xml',
            request_id=timezone.now())
        orphan.md_metadata_file.save(
            'drain-refused.xml', ContentFile(b'<residue/>'), save=True)
        orphan_name = orphan.md_metadata_file.name

        with patch.object(collect_reference, 'apply_async', autospec=True), \
                patch.object(finish_metadata_collection, 'apply_async',
                             autospec=True), \
                patch('django.db.models.query.QuerySet.delete',
                      side_effect=RuntimeError('the database refused')):
            summary = recover_registration_reference_work.run()

        self.assertEqual(summary['drained'], 0)
        self.assertTrue(
            RegistrationDocumentAcquisition.objects.filter(
                pk=orphan.pk).exists(),
            msg='a refused drain leaves its row for the next pass')
        self.assertTrue(self._storage().exists(orphan_name),
                        msg='the bytes of an undrained row stay')

    def test_a_waiter_out_of_rounds_leaves_its_row_for_the_recovery(self):
        """The waiter which gave up is nobody's work anymore (#1410).

        With the wait rounds spent the waiter publishes nothing further:
        its row stands PENDING and unheld, the shape the recovery re-
        drives like every other lost claim.
        """
        sealed = self._plan(self._advertised(self.layers[0]))
        row = TemporaryMdMetadataFile.objects.get(pk=sealed[0])
        claimed = row.claim_for_processing(str(self.process.pk), 600)
        self.assertIsNotNone(claimed,
                             msg='the waiter holds a real claim')
        waiter = SimpleNamespace(
            request=SimpleNamespace(retries=FINISH_WAIT_MAX_RETRIES),
            retry=Mock(side_effect=AssertionError(
                'waited again past the rounds')))

        result = _wait_for_shared_document(waiter, row, claimed[0])

        self.assertIsNone(result)
        waiter.retry.assert_not_called()
        row.refresh_from_db()
        self.assertEqual(row.state, ReferenceWorkStateEnum.PENDING.value,
                         msg='the reference is nobody\'s work again')

    def test_a_closed_run_is_never_mirrored_onto_its_open_siblings(self):
        """A decision which lands after the completion sees the door shut.

        The delivery answers while the run is already closed: its own row
        answers as the late report it is, but the mirror of the identity
        does not decide the siblings of a completed run - the completion
        has counted them its own way, and a second decision would double
        the answer (#1410).
        """
        sealed = self._plan(
            self._advertised(self.layers[0]),
            self._advertised(self.layers[1]))
        doc = RegistrationDocumentAcquisition.objects.get(
            background_process_id=self.process.pk)
        row = TemporaryMdMetadataFile.objects.get(pk=sealed[0])
        claimed = row.claim_for_processing(str(self.process.pk), 600)
        self.assertIsNotNone(claimed)
        BackgroundProcess.objects.filter(pk=self.process.pk).update(
            status=ProcessStatusEnum.COMPLETED, done_at=timezone.now())

        result = _decide_shared_fetch_failure(
            Mock(), doc, self.process.pk, ReferenceErrorKind.FETCH_UNREACHABLE,
            ConnectionError('refused'), sealed[0], claimed[0], False)

        self.assertEqual(
            result, {"data": None, "outcome": None,
                     "error_kind": ReferenceErrorKind.FETCH_UNREACHABLE.value})
        sibling = TemporaryMdMetadataFile.objects.get(pk=sealed[1])
        self.assertEqual(
            sibling.state, ReferenceWorkStateEnum.PENDING.value,
            msg='the mirror of a closed run decides nothing')
