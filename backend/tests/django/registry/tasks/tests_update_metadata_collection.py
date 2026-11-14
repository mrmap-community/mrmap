"""The update collects the metadata its new capabilities advertise (#1274).

An update of a WMS or WFS hands the references of its published service to
the existing collection machinery of a registration (#1263): the job seals
its run with a decided status while ``done_at`` stays empty, the delivered
step seals the plan and publishes one ``collect_reference`` per advertised
reference, and the completion of the fan-out - the same chord body the
registration uses, and the same one the recovery publishes - closes the job.

Told with the seams the implementation has: the handoff is the task
publication the job registers on commit; the step and the chord body are
answered through celery's tracer (``tests.django.utils``), because the
reports into the process are sent by the signal handlers a worker pays; the
fan-out publication itself is captured - its broker is out of reach here and
its members are pinned in ``tests_collect_reference``. The other half of the
contract - a CSW collects nothing - is answered by the flag the CSW's own
registration already reads.
"""

from unittest.mock import patch

from celery.app.trace import build_tracer
from django.test import TransactionTestCase, override_settings
from django.utils import timezone
from notify.enums import ProcessStatusEnum
from notify.models import BackgroundProcess
from registry.enums.metadata import ReferenceWorkStateEnum
from registry.enums.update import UpdateJobStatusEnum
from registry.models.harvest import TemporaryMdMetadataFile
from registry.models.metadata import (LayerRemoteMetadata,
                                      WebMapServiceRemoteMetadata)
from registry.models.service import CatalogueService, Layer, WebMapService
from registry.models.update import (CatalogueServiceUpdateJob,
                                    WebFeatureServiceUpdateJob,
                                    WebMapServiceUpdateJob,
                                    update_job_for_process)
from registry.tasks.service import (advertised_references, collect_reference,
                                    finish_metadata_collection)
from registry.tasks.update import collect_update_metadata
from requests.sessions import Session
from tests.django.utils import WorkerRunMixin

URL = 'http://metadata.example.org/update/record.xml'


@override_settings(CHANNEL_LAYERS={
    "default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}})
class UpdateMetadataCollectionTests(WorkerRunMixin, TransactionTestCase):
    """The whole walk of the step, from the handoff to the closing report."""

    fixtures = ["test_users.json", "test_keywords.json", "test_crs.json",
                "test_wms.json", "test_wfs.json", "test_csw.json"]

    def setUp(self):
        super().setUp()
        # the handoff and the periodic runner publish over a broker this
        # test does not have; capturing their publications is the point
        self.dispatched = []
        for task in (collect_update_metadata, ):
            patcher = patch.object(task, 'apply_async',
                                   autospec=True)
            mock = patcher.start()
            self.addCleanup(patcher.stop)
            mock.side_effect = lambda *a, **kw: self.dispatched.append(
                (task.name, kw))
        for runner in ('run_wms_update', 'run_wfs_update', 'run_csw_update'):
            patcher = patch(f'registry.tasks.update.{runner}.apply_async')
            patcher.start()
            self.addCleanup(patcher.stop)

        self.wms = WebMapService.objects.first()
        self.assertIsNotNone(self.wms, 'the wms fixture must exist')
        self.layer = Layer.objects.filter(service=self.wms).first()
        self.csw = CatalogueService.objects.first()

    # -- helpers -------------------------------------------------------------

    def _job(self):
        """A WMS update job in the state its update leaves behind: decided,
        not over, with its process reporting the run."""
        job = WebMapServiceUpdateJob.objects.create(
            service=self.wms, status=UpdateJobStatusEnum.UPDATING.value)
        job.finish_after_metadata_step(UpdateJobStatusEnum.UPDATED)
        return job

    def _advertise(self, described, url=URL):
        """A reference the capabilities leave behind, kind per element."""
        model = (LayerRemoteMetadata if described is self.layer
                 else WebMapServiceRemoteMetadata)
        return model.objects.create(link=url, describes=described)

    def _deliver(self, task, task_args=(), task_kwargs=None, retries=0):
        task._backend = self.app.backend
        self.addCleanup(lambda: task.__dict__.pop('_backend', None))
        trace = build_tracer(task.name, task, app=self.app)
        return trace(str(self.task_id), tuple(task_args),
                     task_kwargs or {}, {'id': str(self.task_id),
                                         'retries': retries})

    def _decide(self, process, status=ProcessStatusEnum.FAILED):
        """The shape an administrator's decision (or the task's failure)
        leaves behind: decided, with a done_at."""
        BackgroundProcess.objects.filter(pk=process.pk).update(
            status=status, done_at=timezone.now())

    # -- the handoff -----------------------------------------------------

    def test_update_decides_its_run_yet_stays_open_for_the_step(self):
        """The run names its outcome while the process keeps saying running:
        ``done_at`` belongs to the collection's answer, not to the update's
        (#1274) - the job center and the one-job constraint read exactly
        these two fields."""
        job = WebMapServiceUpdateJob.objects.create(
            service=self.wms, status=UpdateJobStatusEnum.UPDATING.value)

        job.finish_after_metadata_step(UpdateJobStatusEnum.UPDATED)

        job.refresh_from_db()
        self.assertEqual(job.status, UpdateJobStatusEnum.UPDATED.value)
        self.assertIsNone(job.done_at)
        self.assertTrue(job.still_works)

        process = job.background_process
        process.refresh_from_db()
        self.assertEqual(process.status, ProcessStatusEnum.RUNNING)
        self.assertIsNone(process.done_at)

        # the step was published for exactly this process, on commit of the
        # update - after the candidate's rows are durable
        self.assertEqual(
            self.dispatched,
            [(collect_update_metadata.name,
              {'kwargs': {'background_process_pk': process.pk}})])

    def test_no_update_needed_hands_the_step_over_too(self):
        """Decision D5 of the epic: the backfill has to reach the services
        registered before this step, whose capabilities never change - so
        the no-change outcome collects as well."""
        job = WebMapServiceUpdateJob.objects.create(
            service=self.wms, status=UpdateJobStatusEnum.UPDATING.value)

        job.finish_after_metadata_step()

        job.refresh_from_db()
        self.assertEqual(job.status,
                         UpdateJobStatusEnum.NO_UPDATE_NEEDED.value)
        self.assertIsNone(job.done_at)
        self.assertEqual(len(self.dispatched), 1)

    def test_a_kind_without_references_closes_like_its_registration(self):
        """A CSW advertises no metadata records and its registration
        collects none - the flag the view hands for the registration is the
        flag the update reads, and such a job is simply finished."""
        job = CatalogueServiceUpdateJob.objects.create(
            service=self.csw, status=UpdateJobStatusEnum.UPDATING.value)
        self.assertFalse(job.collects_metadata)
        self.assertTrue(WebFeatureServiceUpdateJob.collects_metadata)

        job.finish_after_metadata_step(UpdateJobStatusEnum.UPDATED)

        job.refresh_from_db()
        self.assertEqual(job.status, UpdateJobStatusEnum.UPDATED.value)
        self.assertIsNotNone(job.done_at)
        self.assertEqual(self.dispatched, [])
        job.background_process.refresh_from_db()
        self.assertEqual(job.background_process.status,
                         ProcessStatusEnum.COMPLETED)

    # -- the delivered step --------------------------------------------------

    def test_step_seals_the_plan_of_the_published_service_and_fans_out(self):
        """The step plans one row per advertised reference of the updated
        service, names the expectation on the process before the fan-out is
        out (#1259), and lets the chord body wait for the answers (#1263)."""
        job = self._job()
        process = job.background_process
        self._advertise(self.wms)
        self._advertise(self.layer)

        with patch('registry.tasks.update.chord') as fan_out:
            self._deliver(collect_update_metadata,
                          task_kwargs={'background_process_pk':
                                       str(process.pk)})

        rows = list(TemporaryMdMetadataFile.objects.filter(
            background_process_id=process.pk).order_by('pk'))
        self.assertEqual(len(rows), 2)
        self.assertEqual(
            {row.reference_key for row in rows},
            {TemporaryMdMetadataFile.build_reference_key(self.wms, URL),
             TemporaryMdMetadataFile.build_reference_key(self.layer, URL)})

        process.refresh_from_db()
        self.assertEqual(process.references_total, 2)
        self.assertEqual(process.total_steps, 2)
        self.assertEqual(process.phase, 'collect_metadata_records')
        self.assertTrue(process.references_plan_sealed)
        self.assertIsNone(process.done_at)
        job.refresh_from_db()
        self.assertIsNone(job.done_at,
                          msg='the update stays open until the answers are in')

        # the fan-out: one collect_reference per row, the shared chord body
        fan_out.assert_called_once()
        members = fan_out.call_args.args[0]
        self.assertEqual(len(members), 2)
        self.assertEqual(
            sorted(m.kwargs['temporary_md_metadata_file_id']
                   for m in members), sorted(row.pk for row in rows))
        for member in members:
            self.assertEqual(str(member.kwargs['background_process_pk']),
                             str(process.pk))
        body = fan_out.return_value.call_args.args[0]
        self.assertEqual(str(body.kwargs['background_process_pk']),
                         str(process.pk))

    def test_a_service_advertising_nothing_closes_the_run_at_once(self):
        """Planned empty answers 0 where uncollected answers NULL (#1263) -
        and with nothing to wait for, the step answers where it stands: the
        run closes with its zero-reference summary."""
        job = self._job()
        process = job.background_process

        with patch('registry.tasks.update.chord') as fan_out:
            self._deliver(collect_update_metadata,
                          task_kwargs={'background_process_pk':
                                       str(process.pk)})

        fan_out.assert_not_called()
        process.refresh_from_db()
        self.assertEqual(process.status, ProcessStatusEnum.COMPLETED)
        self.assertEqual(process.references_total, 0)
        self.assertEqual(process.references_skipped, 0)
        self.assertIsNotNone(process.done_at)
        job.refresh_from_db()
        self.assertIsNotNone(job.done_at)

    def test_the_completion_of_the_fan_out_closes_the_job(self):
        """The chord body - and the recovery publishing the same task - ends
        the update whose process it reports: with its own outcome, not a new
        one, and the process mirrors the answer the job gives."""
        job = self._job()
        process = job.background_process
        self._advertise(self.layer)
        with patch('registry.tasks.update.chord'):
            self._deliver(collect_update_metadata,
                          task_kwargs={'background_process_pk':
                                       str(process.pk)})

        self._deliver(finish_metadata_collection,
                      task_kwargs={'background_process_pk':
                                   str(process.pk)})

        process.refresh_from_db()
        self.assertEqual(process.status, ProcessStatusEnum.COMPLETED)
        self.assertEqual(process.references_total, 1)
        self.assertEqual(
            process.references_skipped, 1,
            msg='the never-claimed row is nobody\'s work: it counts skipped')
        job.refresh_from_db()
        self.assertIsNotNone(job.done_at)
        self.assertEqual(job.status, UpdateJobStatusEnum.UPDATED.value)

    def test_a_step_for_a_decided_process_closes_the_run_it_cannot_finish(self):
        """An abort or a failure decides the process; a step delivered into
        that shape may not leave its job unfinished forever - the one
        unfinished job would block the service's next update. It closes the
        run as it stands and writes no plan."""
        job = self._job()
        process = job.background_process
        self._advertise(self.wms)
        self._decide(process)

        with patch('registry.tasks.update.chord') as fan_out:
            self._deliver(
                collect_update_metadata,
                task_kwargs={'background_process_pk': str(process.pk)})
        fan_out.assert_not_called()
        self.assertFalse(TemporaryMdMetadataFile.objects.filter(
            background_process_id=process.pk).exists())
        job.refresh_from_db()
        self.assertIsNotNone(job.done_at)
        self.assertEqual(job.status, UpdateJobStatusEnum.UPDATED.value)
        process.refresh_from_db()
        self.assertEqual(process.status, ProcessStatusEnum.FAILED,
                         msg='the decision of the process stands')

    def test_a_redelivered_step_writes_no_second_fan_out(self):
        """Idempotence is the plan seal of #1263: the second delivery finds
        the marker, publishes nothing and touches no counter; the fan-out of
        the delivery which sealed the plan still closes the run."""
        job = self._job()
        process = job.background_process
        self._advertise(self.wms)
        with patch('registry.tasks.update.chord'):
            self._deliver(collect_update_metadata,
                          task_kwargs={'background_process_pk':
                                       str(process.pk)})
        with patch('registry.tasks.update.chord') as second:
            self._deliver(
                collect_update_metadata,
                task_kwargs={'background_process_pk': str(process.pk)})
        second.assert_not_called()
        self.assertEqual(TemporaryMdMetadataFile.objects.filter(
            background_process_id=process.pk).count(), 1)
        job.refresh_from_db()
        self.assertIsNone(job.done_at,
                          msg='the run still waits for its one fan-out')

    # -- the runner meeting an open step --------------------------------------

    def test_a_re_driven_update_hands_the_step_over_not_the_update(self):
        """The periodic task reuses the unfinished job: the update of it is
        adopted and must not re-fetch the service, while the open step is
        published again - harmless while its fan-out runs, its rescue when
        the step's message was lost with the broker."""
        job = self._job()
        self.dispatched.clear()

        with patch.object(Session, 'send') as send:
            fresh = WebMapServiceUpdateJob.objects.get(pk=job.pk)
            fresh.update()

        send.assert_not_called()
        self.assertEqual(
            self.dispatched,
            [(collect_update_metadata.name,
              {'kwargs': {'background_process_pk':
                          job.background_process_id}})])
        fresh.refresh_from_db()
        self.assertIsNone(fresh.done_at)
        self.assertEqual(fresh.status, UpdateJobStatusEnum.UPDATED.value)

    def test_a_re_driven_update_with_a_decided_process_closes_the_run(self):
        """Same guard, other answer: a decided process will never collect
        again, so the re-driven job ends instead of blocking its service."""
        job = self._job()
        self._decide(job.background_process)
        self.dispatched.clear()

        fresh = WebMapServiceUpdateJob.objects.get(pk=job.pk)
        fresh.update()

        fresh.refresh_from_db()
        self.assertIsNotNone(fresh.done_at)
        self.assertEqual(self.dispatched, [])

    # -- the read behind the process -------------------------------------------

    def test_only_an_unfinished_update_reports_through_a_process(self):
        """A registration's process answers no job (its chord body completes
        the process itself); a finished update answers no job either."""
        job = self._job()
        process = job.background_process
        self.assertEqual(update_job_for_process(process.pk), job)

        job.metadata_step_completed()
        self.assertIsNone(update_job_for_process(process.pk))

        registration = BackgroundProcess.objects.create(
            process_type='registering', phase='collect_metadata_records',
            description='a registration')
        self.assertIsNone(update_job_for_process(registration.pk))
        self.assertIsNone(update_job_for_process(None))


@override_settings(CHANNEL_LAYERS={
    "default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}})
class AdvertisedReferencesTests(TransactionTestCase):
    """What an update collects: the references describing one service and its
    elements - the rows the capabilities mapping leaves behind. The reference
    of a foreign element never answers for this service, and a service (or a
    CSW) without references answers empty. That the rows of a rejected
    candidate are gone before an update's step reads them is the cascade of
    their ``describes`` key, which the candidate deletion of the adoption
    already exercises in ``tests_update_candidates``."""

    fixtures = ["test_users.json", "test_keywords.json", "test_crs.json",
                "test_wms.json", "test_wfs.json", "test_csw.json"]

    def setUp(self):
        super().setUp()
        self.wms = WebMapService.objects.first()
        self.layer = Layer.objects.filter(service=self.wms).first()
        self.csw = CatalogueService.objects.first()

    def test_reads_the_service_and_its_elements(self):
        service_ref = WebMapServiceRemoteMetadata.objects.create(
            link=URL, describes=self.wms)
        layer_ref = LayerRemoteMetadata.objects.create(
            link=f'{URL}?layer=1', describes=self.layer)

        refs = advertised_references(self.wms)

        self.assertCountEqual(refs, [service_ref, layer_ref])

    def test_reads_only_the_references_of_this_service(self):
        own = LayerRemoteMetadata.objects.create(link=URL,
                                                 describes=self.layer)
        foreign_layer = None
        for other in WebMapService.objects.exclude(pk=self.wms.pk):
            foreign_layer = Layer.objects.filter(service=other).first()
            if foreign_layer is not None:
                break
        if foreign_layer is not None:
            LayerRemoteMetadata.objects.create(link=URL,
                                               describes=foreign_layer)

        self.assertEqual(advertised_references(self.wms), [own])

    def test_a_service_without_advertised_references_answers_empty(self):
        self.assertEqual(advertised_references(self.wms), [])
        self.assertEqual(advertised_references(self.csw), [])
