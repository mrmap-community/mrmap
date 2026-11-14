"""The idempotency contract of the registration reference work queue (#1263).

The deterministic acceptance list of the issue, told with the seams the
implementation actually has:

* the sealed plan is written once - a redelivered root or a replayed planner
  delivery finds the marker and writes nothing; the same url advertised for
  two resources is two rows, advertised twice for one resource it is one;
* a delivery without the row's claim token decides nothing - the token which
  died with a lost lease does not persist a completion and moves no counter;
* a decided row is closed: a plain redelivery of a FAILED reference refuses
  to work it, only the ``allow_failed`` authorization of #1265 reopens it
  (its counter arithmetic lives in ``tests_collect_reference``);
* the recovery redrives exactly the eligible rows - old PENDING, expired
  LEASE - bounded per pass, and closes sealed plans whose work all decided;
* the registration orphan sweep only reaches the registration prefix and
  only files no live row or token names; the harvesting cleanup of #1237
  keeps its own prefix and never touches a retained failed reference;
* deleting a process takes its rows and stored documents with it and leaves
  the permanent records alone; the API answers the work paged and filtered
  without ever handing out a claim token.

Successful couplings, kind classification, the transport attempt semantics
and the manual-retry counter arithmetic are pinned in ``tests_service``
(fan-out and kinds) and ``tests_collect_reference`` (failures); this module
adds the plan-, recovery-, cleanup- and API-level guarantees around them.
"""

import tempfile
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

from celery.app.trace import build_tracer
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.db import connection
from django.test import TransactionTestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from notify.enums import ProcessStatusEnum
from notify.models import BackgroundProcess
from registry.enums.harvesting import HarvestingPhaseEnum as Phase
from registry.enums.metadata import (MetadataOriginEnum, ReferenceErrorKind,
                                     ReferenceWorkStateEnum)
from registry.models.harvest import (HarvestingJob, TemporaryMdMetadataFile)
from registry.models.metadata import (DatasetMetadataRecord, MetadataContact,
                                      FeatureTypeRemoteMetadata,
                                      MetadataRelation, LayerRemoteMetadata)
from registry.models.service import (FeatureType, Layer, WebFeatureService,
                                     WebMapService)
from registry.tasks import service as service_tasks
from registry.tasks.harvest import cleanup_harvesting_job_temp_files
from registry.tasks.service import (collect_reference,
                                    finish_metadata_collection,
                                    plan_registration_references,
                                    recover_registration_reference_work,
                                    sweep_registration_orphan_files)
from requests import Session
from rest_framework.test import APIClient
from tests.django.utils import MockResponse, WorkerRunMixin

ISO_DATA = Path(__file__).parent.parent.parent / 'test_data/iso_metadata'
DATASET = (ISO_DATA / 'dataset.xml').read_text()
FILE_IDENTIFIER = "de.dwd.geoserver.fach.RBSN_FF"
OLD = timezone.now() - timedelta(hours=2)


class _PlanningTask:
    """Stand-in for the root task the planner reports its seal through.

    It writes the plan numbers exactly the way ``update_background_process``
    of the real task does, so the test reads the same process shape a
    registration leaves behind - without importing the whole root delivery.
    """

    def __init__(self, process):
        self.process = process
        self.calls = []

    def update_background_process(self, phase=None, service=None,
                                  total_steps=None, references_total=None,
                                  **kwargs):
        self.calls.append({
            'phase': phase, 'total_steps': total_steps,
            'references_total': references_total})
        BackgroundProcess.objects.filter(pk=self.process.pk).update(
            total_steps=total_steps, references_total=references_total)


class MediaStorageMixin:
    """A private MEDIA_ROOT per test, so storage assertions never race."""

    def setUp(self):
        super().setUp()
        media = tempfile.TemporaryDirectory()
        self.addCleanup(media.cleanup)
        override = override_settings(MEDIA_ROOT=media.name)
        override.enable()
        self.addCleanup(override.disable)

    def _store(self, row, name, content=b'<Metadata/>'):
        row.md_metadata_file.save(name, ContentFile(content), save=True)
        return row.md_metadata_file.name


@override_settings(CHANNEL_LAYERS={
    "default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}})
class ReferencePlanTests(MediaStorageMixin,
                         WorkerRunMixin,
                         TransactionTestCase):
    """The plan is written once; a delivery without its row decides nothing."""

    fixtures = ["test_users.json", "test_keywords.json", "test_crs.json",
                "test_wms.json", "test_wfs.json"]

    URL = 'http://metadata.example.org/layer.xml'

    def setUp(self):
        super().setUp()
        self.wms = WebMapService.objects.first()
        self.layers = list(Layer.objects.filter(service=self.wms)[:2])
        self.assertIsNotNone(self.wms)
        self.wfs = WebFeatureService.objects.first()
        self.feature_type = FeatureType.objects.filter(
            service=self.wfs).first()
        self.assertIsNotNone(
            self.feature_type,
            'the wfs fixture must describe a feature type')
        self.process = BackgroundProcess.objects.create(
            process_type='registering', phase='collect_metadata_records',
            description='', references_plan_sealed=False)

    def _advertised(self, described_list, url=URL):
        """RemoteMetadata rows as the capabilities left them, duplicates in.

        The kind follows the described element, exactly as the persistence
        of the mapping hands them over to the root task.
        """
        rows = []
        for described in described_list:
            model = (FeatureTypeRemoteMetadata
                     if isinstance(described, FeatureType)
                     else LayerRemoteMetadata)
            rows.append(model.objects.create(link=url, describes=described))
        return rows

    def _deliver(self, process_pk, row_pk, send=None, retries=0,
                 allow_failed=False):
        collect_reference._backend = self.app.backend
        trace = build_tracer(
            collect_reference.name, collect_reference, app=self.app)
        task_kwargs = {
            'background_process_pk': str(process_pk),
            'temporary_md_metadata_file_id': row_pk,
        }
        if allow_failed:
            task_kwargs['allow_failed'] = True
        with patch.object(Session, 'send', side_effect=send):
            return trace(self.task_id, (), task_kwargs,
                         {'id': self.task_id, 'retries': retries})

    @staticmethod
    def _dataset(request, *args, **kwargs):
        return MockResponse(DATASET, status_code=200)

    # -- scenario 1: two references, one delivered twice --------------------

    def test_two_references_one_replayed_after_its_success(self):
        """Replay cannot decide a consumed reference a second time.

        After the first reference stored itself, its row and file are gone;
        the replay of its message answers nothing and moves neither counter
        while the second reference is still PENDING (#1263, acceptance 1).
        """
        # same url advertised for the same resource twice: one logical
        # reference (acceptance 3's second half) - and a second resource,
        # the fixture's feature type, asking for the same url: a second
        # row (first half).
        advertised = self._advertised([self.layers[0], self.layers[0],
                                       self.feature_type])
        sealed = plan_registration_references(
            _PlanningTask(self.process), self.process.pk, advertised,
            self.wms)
        self.assertEqual(len(sealed), 2,
                         msg='one url per resource plans exactly two rows')
        self.process.refresh_from_db()
        self.assertEqual(self.process.references_total, 2)

        first, second = sealed
        self._deliver(self.process.pk, first, send=self._dataset)

        self.process.refresh_from_db()
        self.assertEqual(
            (self.process.references_total,
             self.process.references_stored, self.process.done_steps),
            (2, 1, 1))
        self.assertFalse(
            TemporaryMdMetadataFile.objects.filter(pk=first).exists(),
            msg='the stored row and its file are gone with it')
        replay = self._deliver(self.process.pk, first, send=self._dataset)
        self.assertIsNone(replay.retval)
        self.process.refresh_from_db()
        self.assertEqual(
            (self.process.references_stored, self.process.done_steps),
            (1, 1),
            msg='the replay of a consumed reference decides nothing')
        self.assertTrue(
            TemporaryMdMetadataFile.objects.filter(pk=second).exists(),
            msg='the second reference is untouched and still pending')

    # -- scenario 2: the stale token decides nothing ------------------------

    def test_a_stale_completion_after_a_newer_claim_is_refused(self):
        """The lost lease takes the permit with it (#1263, acceptance 2).

        The delivery whose row was re-claimed under a newer token - a
        recovery re-drove it while this worker still fetched - reports under
        its dead token: the decision is refused, the row keeps the newer
        claim and no counter moves.
        """
        row = TemporaryMdMetadataFile(
            background_process_id=self.process.pk,
            reference_key=TemporaryMdMetadataFile.build_reference_key(
                self.layers[0], self.URL),
            requested_url=self.URL,
            described_layer=self.layers[0],
            request_id=timezone.now())
        TemporaryMdMetadataFile.objects.bulk_create([row])
        BackgroundProcess.objects.filter(pk=self.process.pk).update(
            total_steps=1, references_total=1, references_stored=0,
            references_failed=0)

        stale_token, _ = row.claim_for_processing(self.process.pk, 900)
        row.refresh_from_db()
        row.release_claim(stale_token)
        fresh_token, retried = row.claim_for_processing(self.process.pk, 900)
        self.assertFalse(retried)

        decided = service_tasks._decide_reference_failure(
            self.process.pk, row.pk, stale_token,
            ReferenceErrorKind.NO_CONTENT, RuntimeError('stale'))

        self.assertFalse(decided,
                         msg='a dead token must not decide the row')
        row.refresh_from_db()
        self.assertEqual(row.state, ReferenceWorkStateEnum.LEASED.value)
        self.assertEqual(str(row.claim_token), str(fresh_token))
        self.assertEqual(row.error_kind, "")
        self.process.refresh_from_db()
        self.assertEqual(self.process.references_failed, 0)
        self.assertEqual(self.process.done_steps, 0)

        # the holder of the live token still decides
        decided = service_tasks._decide_reference_failure(
            self.process.pk, row.pk, fresh_token,
            ReferenceErrorKind.NO_CONTENT, RuntimeError('answered 404'))
        self.assertTrue(decided)
        row.refresh_from_db()
        self.assertEqual(row.state, ReferenceWorkStateEnum.FAILED.value)
        self.process.refresh_from_db()
        self.assertEqual(self.process.references_failed, 1)

    # -- scenario 5: pre-existing relations -----------------------------------

    def test_a_preexisting_relation_is_not_the_success_of_a_reference(self):
        """A curated coupling does not short-circuit the import (#1263, 5).

        The layer already carries an EDITOR relation to a record with the
        very file identifier the advertised document carries. That must not
        be taken as success of this reference: the reference is worked - the
        record is identified by the existing instance (the identity rules of
        #982), its own coupling is asserted and the curated one keeps its
        row; the counters say stored, not inherited.
        """
        contact = MetadataContact.objects.create(name='curated contact')
        record = DatasetMetadataRecord.objects.create(
            file_identifier=FILE_IDENTIFIER, title='curated record',
            metadata_contact=contact, dataset_contact=contact,
            code_space='de.mrmap.', code='CURATED',
            abstract='curated before the collection ran')
        curated = record.add_metadata_relation(
            related_object=self.layers[0],
            origin=MetadataOriginEnum.EDITOR.value, is_internal=False)

        advertised = self._advertised([self.layers[0]])
        sealed = plan_registration_references(
            _PlanningTask(self.process), self.process.pk, advertised,
            self.wms)
        self._deliver(self.process.pk, sealed[0], send=self._dataset)

        self.process.refresh_from_db()
        self.assertEqual(self.process.references_stored, 1)
        self.assertEqual(self.process.done_steps, 1)
        self.assertEqual(DatasetMetadataRecord.objects.count(), 1,
                         msg='the identity rules must re-use the record')
        self.assertTrue(MetadataRelation.objects.filter(
            pk=curated.pk,
            origin=MetadataOriginEnum.EDITOR.value).exists(),
            msg="the curator's coupling stays whatever this import does")
        self.assertTrue(MetadataRelation.objects.filter(
            layer=self.layers[0], dataset_metadata=record,
            origin=MetadataOriginEnum.CAPABILITIES.value).exists(),
            msg='the collection asserts its own coupling of this element')
        self.assertFalse(TemporaryMdMetadataFile.objects.exists())

    # -- scenario 7: the replayed root plans nothing again -------------------

    def test_a_replayed_root_never_writes_a_second_plan(self):
        """The sealed marker is the whole deduplication of the root (#1263).

        After one row of the plan was already consumed, a redelivery of the
        planning finds the marker: no new row repopulates the consumed one,
        no counter is reset, and the plan numbers stay (#1263, acceptance 7).
        """
        advertised = self._advertised([self.layers[0], self.feature_type])
        first_task = _PlanningTask(self.process)
        sealed = plan_registration_references(
            first_task, self.process.pk, advertised, self.wms)
        # one reference already consumed: the row is simply gone
        TemporaryMdMetadataFile.objects.filter(pk=sealed[0]).delete()

        replay = _PlanningTask(self.process)
        again = plan_registration_references(
            replay, self.process.pk, advertised, self.wms)

        self.assertIsNone(again)
        self.assertEqual(replay.calls, [],
                         msg='the plan numbers are not rewritten by a replay')
        self.process.refresh_from_db()
        self.assertEqual(self.process.references_total, 2)
        self.assertEqual(
            TemporaryMdMetadataFile.objects.count(), 1,
            msg='the consumed reference is not repopulated')

        # a decided process holds no open plan either
        decided = BackgroundProcess.objects.create(
            process_type='registering', phase='', description='',
            status=ProcessStatusEnum.COMPLETED,
            done_at=timezone.now())
        self.assertIsNone(plan_registration_references(
            _PlanningTask(decided), decided.pk, advertised, self.wms))
        self.assertFalse(
            TemporaryMdMetadataFile.objects.filter(
                background_process=decided).exists())

    # -- scenario 4's tail: the completion closes with skipped ----------------

    def test_the_completion_closes_the_plan_without_skipped(self):
        """All references decided: ``skipped`` answers 0, not NULL.

        The chord body of #1259 closes a plan whose every reference reported
        with exactly zero skipped; the sealed plan of #1263 is what lets it
        tell 0 from never-planned (NULL stays for unplanned runs).
        """
        advertised = self._advertised([self.layers[0]])
        sealed = plan_registration_references(
            _PlanningTask(self.process), self.process.pk, advertised,
            self.wms)
        self._deliver(self.process.pk, sealed[0], send=self._dataset)

        finish_metadata_collection._backend = self.app.backend
        trace = build_tracer(
            finish_metadata_collection.name, finish_metadata_collection,
            app=self.app)
        trace(finish_metadata_collection.name, (),
              {'background_process_pk': str(self.process.pk)},
              {'id': str(self.task_id), 'retries': 0})

        self.process.refresh_from_db()
        self.assertEqual(self.process.status, ProcessStatusEnum.COMPLETED)
        self.assertEqual(self.process.references_skipped, 0)
        self.assertEqual(self.process.references_stored, 1)
        self.assertEqual(self.process.done_steps, self.process.total_steps)


@override_settings(CHANNEL_LAYERS={
    "default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}})
class ReferenceRecoveryAndCleanupTests(MediaStorageMixin, WorkerRunMixin,
                                       TransactionTestCase):
    """Recovery, orphan sweep, deletion cascade and the harvesting isolation."""

    def setUp(self):
        super().setUp()
        contact = MetadataContact.objects.create(name='recovery contact')
        self.service = WebMapService.objects.create(
            title='Recovery test service', version=130, origin=1,
            service_url='http://recovery.example.org/wms',
            metadata_contact=contact, service_contact=contact)

    def _process(self, **overrides):
        values = dict(
            process_type='registering', phase='collect_metadata_records',
            description='', total_steps=1, references_total=1,
            references_stored=0, references_failed=0, references_skipped=0,
            references_plan_sealed=True)
        values.update(overrides)
        return BackgroundProcess.objects.create(**values)

    def _row(self, process, url, state=ReferenceWorkStateEnum.PENDING.value,
             request_id=None, store=None):
        row = TemporaryMdMetadataFile(
            background_process_id=process.pk,
            reference_key=TemporaryMdMetadataFile.build_reference_key(
                self.service, url),
            requested_url=url,
            described_wms=self.service,
            described_display=self.service.title,
            state=state,
            request_id=request_id if request_id is not None
            else timezone.now())
        TemporaryMdMetadataFile.objects.bulk_create([row])
        if store:
            self._store(row, store)
        return row

    # -- scenario 8: the bounded recovery reads the plan, not the broker -----

    def test_recovery_redrives_only_stuck_rows_and_closes_decided_plans(self):
        """Old PENDING and expired LEASE go back to work; the rest stays (#8).

        A fresh PENDING row is a healthy queue, a live lease is a working
        worker, a FAILED row belongs to the authorization of #1265 - none
        of them is re-driven. A sealed plan whose rows all decided but whose
        process never completed is closed through the very task the chord
        body is. The pass is bounded by the configured batch size.
        """
        stuck = self._process()
        old_pending = self._row(stuck, 'http://x/old', request_id=OLD)
        fresh_pending = self._row(stuck, 'http://x/fresh')
        expired_lease = self._row(
            stuck, 'http://x/lease',
            state=ReferenceWorkStateEnum.LEASED.value)
        TemporaryMdMetadataFile.objects.filter(
            pk=expired_lease.pk).update(
                claim_token='00000000-0000-0000-0000-000000000001',
                lease_expires_at=timezone.now() - timedelta(minutes=5))
        live_lease = self._row(
            stuck, 'http://x/live',
            state=ReferenceWorkStateEnum.LEASED.value)
        TemporaryMdMetadataFile.objects.filter(
            pk=live_lease.pk).update(
                claim_token='00000000-0000-0000-0000-000000000002',
                lease_expires_at=timezone.now() + timedelta(minutes=5))
        decided_failed = self._row(
            stuck, 'http://x/failed',
            state=ReferenceWorkStateEnum.FAILED.value)
        closed = self._process()
        self._row(closed, 'http://x/done',
                  state=ReferenceWorkStateEnum.FAILED.value)
        unplanned = self._process(references_plan_sealed=False,
                                  references_total=None)
        self._row(unplanned, 'http://x/unplanned', request_id=OLD)

        with patch.object(collect_reference, 'apply_async',
                          autospec=True) as redrive, \
                patch.object(finish_metadata_collection, 'apply_async',
                             autospec=True) as finish:
            summary = recover_registration_reference_work.run()

        redriven = {c.kwargs['kwargs']['temporary_md_metadata_file_id']
                    for c in redrive.call_args_list}
        self.assertEqual(
            redriven, {old_pending.pk, expired_lease.pk},
            msg='only the old PENDING and the expired LEASE go back to work')
        finish.assert_called_once()
        self.assertEqual(
            finish.call_args.kwargs['kwargs']['background_process_pk'],
            closed.pk)
        self.assertEqual(summary['redriven'], 2)
        self.assertEqual(summary['completed'], [closed.pk])

        # the batch bound of one pass (#1263: bounded, like the harvest one)
        self._row(stuck, 'http://x/old2', request_id=OLD)
        with patch.object(collect_reference, 'apply_async',
                          autospec=True) as redrive, \
                patch.object(finish_metadata_collection, 'apply_async',
                             autospec=True), \
                patch.object(service_tasks, 'REGISTRATION_RECOVERY_BATCH_SIZE',
                             1):
            recover_registration_reference_work.run()
        self.assertEqual(
            redrive.call_count, 1,
            msg='one pass never redrives more than the configured batch')
        # the fresh row still waits, the FAILED row still belongs to #1265
        fresh_pending.refresh_from_db()
        decided_failed.refresh_from_db()
        self.assertEqual(fresh_pending.state,
                         ReferenceWorkStateEnum.PENDING.value)
        self.assertEqual(decided_failed.state,
                         ReferenceWorkStateEnum.FAILED.value)

    # -- scenario 8/9 tail: the orphan sweep, scoped --------------------------

    def test_the_orphan_sweep_only_reaches_the_registration_prefix(self):
        """The sweep reaps lost attempts - and nothing else (#1263, 8/10).

        Kept: a file a live row stores under, a file whose name carries the
        token of a live lease, anything below the numeric directories of the
        harvesting runs, and files too young to have outrun their commit.
        Deleted: the bytes of a lost attempt inside the registration prefix.
        """
        process = self._process()
        live = self._row(process, 'http://x/live', store='live.xml')
        leased = self._row(process, 'http://x/leased')
        token = 'aaaaaaaa-0000-0000-0000-000000000001'
        TemporaryMdMetadataFile.objects.filter(pk=leased.pk).update(
            state=ReferenceWorkStateEnum.LEASED.value,
            claim_token=token,
            lease_expires_at=timezone.now() + timedelta(minutes=5))
        lost_name = self._store(
            self._row(process, 'http://x/owner'), 'kept-but-unstored.xml')

        storage = TemporaryMdMetadataFile._meta.get_field(
            'md_metadata_file').storage
        from registry.models.harvest import (
            REGISTRATION_FILE_SUBDIR, TEMPORARY_MD_METADATA_FILE_SUBDIR)
        base = f"{TEMPORARY_MD_METADATA_FILE_SUBDIR}/{REGISTRATION_FILE_SUBDIR}"
        orphan_name = storage.save(
            f"{base}/{process.pk}/reference-{process.pk}-dead-dead.xml",
            ContentFile(b'<orphan/>'))
        token_name = storage.save(
            f"{base}/{process.pk}/reference-{process.pk}-{token}.xml",
            ContentFile(b'<inflight/>'))
        # a harvesting run's own directory, numeric like its job id: this
        # sweep must not even look there (#1237 owns that tree)
        job_dir_file = storage.save(
            f"{TEMPORARY_MD_METADATA_FILE_SUBDIR}/999999/record.xml",
            ContentFile(b'<harvest/>'))
        self.assertNotEqual(orphan_name, lost_name)

        # the grace window covers commits in flight; for this test the files
        # are all older than any window, so the scoping is what is measured
        with patch.object(service_tasks,
                          'REGISTRATION_ORPHAN_FILE_GRACE_SECONDS', -120):
            deleted = sweep_registration_orphan_files()

        self.assertTrue(storage.exists(live.md_metadata_file.name))
        self.assertTrue(storage.exists(token_name))
        self.assertTrue(storage.exists(job_dir_file))
        self.assertFalse(
            storage.exists(orphan_name),
            msg='a lost attempt below the registration prefix is its answer')
        self.assertGreaterEqual(deleted, 1)

    # -- scenario 10: the harvesting cleanup keeps its own ground -------------

    def test_harvesting_cleanup_never_touches_a_retained_failure(self):
        """#1237 reaps its job, #1263 keeps its failed references (acceptance 10).

        The cleanup of an ended harvest deletes the job's rows and files and
        sweeps its directory - and a registration process with a retained
        failed reference (row and stored document) is untouched by it, as
        the reverse holds for the registration sweep above.
        """
        job = HarvestingJob(total_records=0, phase=Phase.COMPLETED,
                            done_at=timezone.now())
        job.save()
        harvest_record = TemporaryMdMetadataFile.objects.create(
            job=job, has_import_error=False)
        harvest_name = self._store(
            harvest_record, f"job-{job.pk}.xml", b'<record/>')

        process = self._process()
        failed = self._row(process, 'http://x/failed',
                           state=ReferenceWorkStateEnum.FAILED.value)
        failed_name = self._store(
            failed, f"reference-{failed.pk}-keeper.xml", b'<kept/>')

        summary = cleanup_harvesting_job_temp_files(
            job.pk, respect_retention=False)

        self.assertFalse(summary['skipped'])
        self.assertFalse(TemporaryMdMetadataFile.objects.filter(
            pk=harvest_record.pk).exists())
        storage = TemporaryMdMetadataFile._meta.get_field(
            'md_metadata_file').storage
        self.assertFalse(storage.exists(harvest_name))
        failed.refresh_from_db()
        self.assertTrue(
            TemporaryMdMetadataFile.objects.filter(pk=failed.pk).exists(),
            msg='the harvesting cleanup never reaps registration work')
        self.assertTrue(storage.exists(failed_name))

    # -- scenario 9: process deletion decides where work stops ----------------

    def test_process_deletion_cascades_work_but_keeps_the_records(self):
        """The permanent graph survives, the work items and bytes do not.

        Deleting the process takes its work rows (cascade) and their stored
        documents (the sweep in ``BackgroundProcess.delete``); the metadata
        record and its coupling created by a stored reference are permanent
        and stay. A delivery of a cascaded row afterwards is a no-op - the
        in-flight completion of a deleted run finds nothing to decide.
        """
        process = self._process()
        row = self._row(process, 'http://x/stored',
                        state=ReferenceWorkStateEnum.FAILED.value)
        name = self._store(row, f'reference-{row.pk}-gone.xml', b'<x/>')
        storage = TemporaryMdMetadataFile._meta.get_field(
            'md_metadata_file').storage
        self.assertTrue(storage.exists(name))

        process.delete()

        self.assertFalse(TemporaryMdMetadataFile.objects.filter(
            background_process_id=process.pk).exists())
        self.assertFalse(
            storage.exists(name),
            msg='the stored documents of a deleted process go with it')

        # an in-flight delivery of the deleted run decides nothing
        collect_reference._backend = self.app.backend
        trace = build_tracer(
            collect_reference.name, collect_reference, app=self.app)
        result = trace(
            collect_reference.name, (),
            {'background_process_pk': str(process.pk),
             'temporary_md_metadata_file_id': row.pk},
            {'id': str(self.task_id), 'retries': 0})
        self.assertIsNone(result.retval)
        self.assertEqual(DatasetMetadataRecord.objects.count(), 0)

    def test_claim_of_a_deleted_process_is_refused(self):
        """After the purge there is nothing to retry - the row is gone, and
        with it the handle of #1265 (acceptance 11's last clause)."""
        process = self._process()
        row = self._row(process, 'http://x/gone')
        pk = row.pk
        process.delete()
        self.assertIsNone(TemporaryMdMetadataFile.objects.filter(
            pk=pk).first())


@override_settings(CHANNEL_LAYERS={
    "default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}})
class ReferenceWorkApiTests(MediaStorageMixin, TransactionTestCase):
    """Paged, filtered reads - and never a permit of the queue (#1263, 11/12)."""

    def setUp(self):
        super().setUp()
        # TransactionTestCase truncation removes the guardian user created
        # on post_migrate; anonymous read checks look it up by name
        get_user_model().objects.get_or_create(username="AnonymousUser")
        contact = MetadataContact.objects.create(name='api contact')
        self.service = WebMapService.objects.create(
            title='Reference api service', version=130, origin=1,
            service_url='http://api.example.org/wms',
            metadata_contact=contact, service_contact=contact)
        self.client = APIClient()

    LIST_URL = '/api/registry/harvesting/temporary-md-metadata-file'

    def _process(self, **overrides):
        values = dict(
            process_type='registering', phase='collect_metadata_records',
            description='', references_plan_sealed=True)
        values.update(overrides)
        return BackgroundProcess.objects.create(**values)

    def _row(self, process, url, **overrides):
        values = dict(
            background_process_id=process.pk,
            reference_key=TemporaryMdMetadataFile.build_reference_key(
                self.service, url),
            requested_url=url,
            described_wms=self.service,
            described_display=self.service.title,
            request_id=timezone.now())
        values.update(overrides)
        row = TemporaryMdMetadataFile(**values)
        TemporaryMdMetadataFile.objects.bulk_create([row])
        return row

    def _get(self, params=None):
        response = self.client.get(
            self.LIST_URL, params or {},
            HTTP_ACCEPT='application/vnd.api+json')
        self.assertEqual(response.status_code, 200, response.content[:400])
        return response.json()

    def test_the_endpoint_answers_the_work_without_its_permits(self):
        """Filters answer the process's work; the claim internals stay out.

        ``claim_token``, ``lease_expires_at`` and ``reference_key`` authorize
        one delivery to write - a client that read them could forge a claim,
        so they are not in the answer (#1263).
        """
        process = self._process()
        other = self._process()
        pending = self._row(process, 'http://api/pending')
        failed = self._row(
            process, 'http://api/failed',
            state=ReferenceWorkStateEnum.FAILED.value,
            error_kind=ReferenceErrorKind.NO_CONTENT.value,
            error_at=timezone.now(), import_error='answered with 404')
        self._row(other, 'http://api/other')
        # the both-null legacy row of a deployment which had no owner yet:
        # readable, never claimed
        legacy = TemporaryMdMetadataFile.objects.create(
            import_error='legacy row', has_import_error=True)

        body = self._get({'filter[background_process__id]': str(process.pk)})
        answers = {resource['id'] for resource in body['data']}
        self.assertEqual(answers, {str(pending.pk), str(failed.pk)})
        for resource in body['data']:
            attributes = resource['attributes']
            # the JSON:API renderer camel-cases; neither spelling of a
            # permit may appear
            for secret in ('claim_token', 'lease_expires_at',
                           'reference_key', 'claimToken', 'leaseExpiresAt',
                           'referenceKey'):
                self.assertNotIn(
                    secret, attributes,
                    msg=f'the API must never hand out {secret}')
            self.assertIn('state', attributes)
        # JSON:API 1.1 carries pagination in the top-level meta
        self.assertIn('pagination', body['meta'])

        only_failed = self._get({
            'filter[background_process__id]': str(process.pk),
            'filter[state]': ReferenceWorkStateEnum.FAILED.value})
        self.assertEqual(len(only_failed['data']), 1)
        self.assertEqual(
            only_failed['data'][0]['attributes']['errorKind'],
            ReferenceErrorKind.NO_CONTENT.value)

        # paged: one per page answers the pagination meta with the full count
        paged = self._get({
            'filter[background_process__id]': str(process.pk),
            'page[size]': 1})
        self.assertEqual(len(paged['data']), 1)
        self.assertEqual(
            int(paged['meta']['pagination']['count']), 2)
        # and the legacy row is simply there, with no process to name
        legacy_body = self._get({'filter[import_error]': 'legacy row'})
        self.assertEqual(
            {r['id'] for r in legacy_body['data']}, {str(legacy.pk)})

    def test_the_list_costs_the_same_queries_whatever_the_rows(self):
        """No per-row aggregation behind the collection (#1263, acceptance 12).

        Three rows of different processes must not cost more reads than one
        row: the answer stays at the same query count, so a large run does
        not turn every poll of the card into a scan of the queue.
        """
        first = self._process()
        self._row(first, 'http://api/a')
        with CaptureQueriesContext(connection) as one:
            self._get({'page[size]': 100})

        other = self._process()
        for index in range(3):
            self._row(other, f'http://api/b{index}')
        self._process()
        with CaptureQueriesContext(connection) as many:
            self._get({'page[size]': 100})

        self.assertEqual(
            len(one), len(many),
            msg='the collection must not read more per row than per request')
