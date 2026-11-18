from pathlib import Path
from unittest.mock import patch

from celery.exceptions import Retry
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, OperationalError, connection, transaction
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django_celery_beat.models import IntervalSchedule
from MrMap.settings import BASE_DIR
from notify.models import BackgroundProcess
from registry.enums.service import HttpMethodEnum, OGCOperationEnum
from registry.enums.update import UpdateJobStatusEnum
from registry.models.service import CatalogueService, WebFeatureService
from registry.models.update import (
    CatalogueServiceUpdateJob, CatalogueServiceUpdateSetting,
    WebFeatureServiceUpdateJob, WebFeatureServiceUpdateSetting,
)
from registry.tasks.update import (
    collect_update_metadata, create_csw_update_job, create_wfs_update_job,
    run_csw_update, run_wfs_update, run_wms_update,
)
from requests.exceptions import ConnectionError, RequestException
from requests.sessions import Session
from tests.django.sql_guard import statements_of
from tests.django.utils import MockResponse

WFS_CAPABILITIES = Path(
    BASE_DIR, "tests/django/test_data/capabilities/wfs/fixture_2.0.0.xml")
CSW_CAPABILITIES = Path(
    BASE_DIR, "tests/django/test_data/capabilities/csw/2.0.2.xml")

# the remote answer which is the document a service already stores: the update
# of a service which stands there fetches it and decides "nothing to do"
WFS_REMOTE_RESPONSE = MockResponse(content=WFS_CAPABILITIES)
CSW_REMOTE_RESPONSE = MockResponse(content=CSW_CAPABILITIES)

# a renamed feature type is a change the update may not decide alone: it leaves
# the run at a review which a human has to answer
WFS_RENAMED_REMOTE_RESPONSE = MockResponse(
    content=WFS_REMOTE_RESPONSE.text.replace(
        "<Name>node3</Name>", "<Name>node3_renamed</Name>"))


class PeriodicUpdateJobTest(TestCase):
    fixtures = [
        "test_users.json", "test_keywords.json", "test_crs.json",
        "test_wfs.json", "test_csw.json",
    ]
    cases = (
        (WebFeatureService, WebFeatureServiceUpdateJob,
         WebFeatureServiceUpdateSetting, create_wfs_update_job, "run_wfs_update"),
        (CatalogueService, CatalogueServiceUpdateJob,
         CatalogueServiceUpdateSetting, create_csw_update_job, "run_csw_update"),
    )

    def setUp(self):
        self.interval = IntervalSchedule.objects.create(every=1, period="days")

    def test_reuses_unfinished_jobs_without_enqueueing(self):
        for service_model, job_model, setting_model, create_job, runner in self.cases:
            service = service_model.objects.first()
            setting = setting_model.objects.create(service=service, interval=self.interval)
            for status in (
                UpdateJobStatusEnum.WAITING_FOR_PROCESSING,
                UpdateJobStatusEnum.UPDATING,
                UpdateJobStatusEnum.REVIEW_REQUIRED,
                UpdateJobStatusEnum.RESUME,
            ):
                with self.subTest(service=service_model.__name__, status=status):
                    job = job_model.objects.create(service=service, status=status.value)
                    process_count = BackgroundProcess.objects.count()
                    with patch(f"registry.tasks.update.{runner}.apply_async") as enqueue:
                        with self.captureOnCommitCallbacks(execute=True):
                            for _ in range(2):
                                self.assertEqual(create_job(name=setting.name), job.pk)
                        enqueue.assert_not_called()
                    job.refresh_from_db()
                    self.assertEqual(job.status, status.value)
                    self.assertIsNone(job.done_at)
                    self.assertEqual(service.update_jobs.filter(done_at__isnull=True).count(), 1)
                    self.assertEqual(BackgroundProcess.objects.count(), process_count)
                    job.finish()

    def test_creates_and_enqueues_after_previous_job_finished(self):
        for service_model, job_model, setting_model, create_job, runner in self.cases:
            with self.subTest(service=service_model.__name__):
                service = service_model.objects.first()
                setting = setting_model.objects.create(service=service, interval=self.interval)
                for status in (
                    UpdateJobStatusEnum.UPDATED,
                    UpdateJobStatusEnum.NO_UPDATE_NEEDED,
                    UpdateJobStatusEnum.ERROR,
                ):
                    job_model.objects.create(service=service).finish(status)
                with patch(f"registry.tasks.update.{runner}.apply_async") as enqueue:
                    with self.captureOnCommitCallbacks(execute=True):
                        job_id = create_job(name=setting.name)
                        enqueue.assert_not_called()
                    enqueue.assert_called_once_with(kwargs={"update_job_id": job_id})
                self.assertEqual(service.update_jobs.count(), 4)
                self.assertEqual(service.update_jobs.filter(done_at__isnull=True).get().pk, job_id)

    def test_different_services_have_independent_jobs(self):
        for service_model, job_model, setting_model, create_job, runner in self.cases:
            with self.subTest(service=service_model.__name__):
                first, second = list(service_model.objects.all()[:2])
                existing = job_model.objects.create(service=first)
                setting = setting_model.objects.create(service=second, interval=self.interval)
                with patch(f"registry.tasks.update.{runner}.apply_async") as enqueue:
                    with self.captureOnCommitCallbacks(execute=True):
                        job_id = create_job(name=setting.name)
                    enqueue.assert_called_once_with(kwargs={"update_job_id": job_id})
                self.assertNotEqual(job_id, existing.pk)
                self.assertEqual(job_model.objects.get(pk=job_id).service_id, second.pk)

    def test_multiple_schedules_for_same_service_reuse_job(self):
        for service_model, job_model, setting_model, create_job, runner in self.cases:
            with self.subTest(service=service_model.__name__):
                service = service_model.objects.first()
                settings = [setting_model.objects.create(service=service, interval=self.interval)
                            for _ in range(2)]
                with patch(f"registry.tasks.update.{runner}.apply_async") as enqueue:
                    with self.captureOnCommitCallbacks(execute=True):
                        job_ids = [create_job(name=setting.name) for setting in settings]
                    enqueue.assert_called_once_with(kwargs={"update_job_id": job_ids[0]})
                self.assertEqual(job_ids[0], job_ids[1])
                self.assertEqual(service.update_jobs.count(), 1)

    def test_database_rejects_duplicate_unfinished_jobs(self):
        for service_model, job_model, _, _, _ in self.cases:
            with self.subTest(service=service_model.__name__):
                service = service_model.objects.first()
                job_model.objects.create(service=service)
                with self.assertRaises(IntegrityError), transaction.atomic():
                    job_model.objects.create(service=service)


class UpdateRunnerDeliveryTest(TestCase):
    """What the WFS' and the CSW' update runners answer a second delivery.

    Both runners used to have no delivery guards at all (#1453): their message
    was acknowledged before the run answered, so a worker which died with it
    took the run with it and nothing ever came back for the job. That job is the
    one an unfinished run blocks its service with - the next period re-uses it
    instead of creating another one and enqueueing it (pinned in
    ``PeriodicUpdateJobTest``) - so the service stood un-updated for every
    following period. The runners answer like the WMS runner does since #817 and
    #1178: the delivery comes back to the broker, the job is read under its own
    row lock, and a job which decided about itself, or which stands at a review
    nobody has answered, is answered without its update running a second time.

    The metadata step a WFS' run hands over (#1274) is not this module's
    subject: every hand-off is captured here, its machinery is pinned in
    ``tests_update_metadata_collection``.
    """

    fixtures = [
        "test_users.json", "test_keywords.json", "test_crs.json",
        "test_wfs.json", "test_csw.json",
    ]

    cases = (
        {
            "service": WebFeatureService,
            "job": WebFeatureServiceUpdateJob,
            "setting": WebFeatureServiceUpdateSetting,
            "create": create_wfs_update_job,
            "runner": run_wfs_update,
            "remote": WFS_REMOTE_RESPONSE,
            # a WFS update collects the metadata its capabilities advertise, so
            # its run is decided before it is over (#1274)
            "collects_metadata": True,
        },
        {
            "service": CatalogueService,
            "job": CatalogueServiceUpdateJob,
            "setting": CatalogueServiceUpdateSetting,
            "create": create_csw_update_job,
            "runner": run_csw_update,
            "remote": CSW_REMOTE_RESPONSE,
            # a CSW advertises no metadata records and collects none, so its run
            # is over when its update decided (#1274)
            "collects_metadata": False,
        },
    )

    def setUp(self):
        self.interval = IntervalSchedule.objects.create(every=1, period="days")
        # everything these runs hand over is published to a broker this test has
        # none of: the next delivery of a runner and the metadata step of a WFS
        self.published = {}
        for task in (run_wfs_update, run_csw_update, collect_update_metadata):
            patcher = patch.object(task, "apply_async", autospec=True)
            self.published[task.name] = patcher.start()
            self.addCleanup(patcher.stop)

    def stored_service(self, case):
        """A service of the fixture which stores the document its remote answers.

        A run asks the GetCapabilities url of its service, so this is the first
        service which answers one - not simply the first of the fixture: the
        WFS2 of it carries only a GetFeature url, so an update of that service
        could never ask its remote for anything at all.

        Returns:
            OGCService: a service whose stored capabilities are exactly what the
                case's mocked remote answers, so an update which fetches them
                decides that there is nothing to do
        """
        service = case["service"].objects.filter(
            operation_url__operation=OGCOperationEnum.GET_CAPABILITIES.value,
            operation_url__method=HttpMethodEnum.GET.value,
        ).first()
        self.assertIsNotNone(
            service, "the fixture has to hold a service its update can ask")
        service.xml_backup_file = SimpleUploadedFile(
            "capabilities.xml", case["remote"].content)
        service.save()
        return service

    def test_runners_answer_a_lost_worker_by_giving_the_delivery_back(self):
        """The three update runners carry one and the same delivery policy.

        They do the same kind of work: a delivery which is acknowledged up front
        and whose worker dies is gone for good, and the unfinished job it leaves
        behind is what blocks its service from then on.
        """
        for runner in (run_wms_update, run_wfs_update, run_csw_update):
            with self.subTest(runner=runner.name):
                self.assertTrue(
                    runner.acks_late, "the run has to answer before the ack")
                self.assertTrue(
                    runner.reject_on_worker_lost,
                    "a worker which dies gives its delivery back")
                self.assertEqual(
                    runner.autoretry_for, (RequestException, OperationalError),
                    "a remote or a database which is briefly gone is retried")
                self.assertTrue(runner.retry_backoff)
                self.assertEqual(runner.retry_kwargs, {"max_retries": 5})

    def test_redelivered_runner_processes_the_job_once(self):
        """No second delivery runs the update of a job a second time.

        The first delivery decides the run. The deliveries after it find it while
        its last step is still open (the metadata of a WFS, #1274) and after the
        run is over: none of them fetches the capabilities document again, none
        reports a result of its own - an update which decided about itself is
        over, whoever asks about it.
        """
        for case in self.cases:
            with self.subTest(service=case["service"].__name__):
                service = self.stored_service(case)
                with self.captureOnCommitCallbacks(execute=True):
                    job = case["job"].objects.create(service=service)
                with patch.object(
                        Session, "send", return_value=case["remote"]) as remote:
                    with self.captureOnCommitCallbacks(execute=True):
                        case["runner"](update_job_id=job.pk)
                    job.refresh_from_db()
                    self.assertEqual(
                        job.status, UpdateJobStatusEnum.NO_UPDATE_NEEDED.value)
                    self.assertEqual(remote.call_count, 1, "the first delivery works the job")
                    # a WFS' run is decided but not over: its metadata step has
                    # to answer first; a CSW collects nothing and is over (#1274)
                    self.assertEqual(
                        job.still_works, case["collects_metadata"],
                        "the run of this kind waits for a step or is over")

                    # the redelivery of a decided run: it answers the open step
                    # of a WFS, it reads the end of a CSW - it never updates
                    with self.captureOnCommitCallbacks(execute=True):
                        case["runner"](update_job_id=job.pk)
                    job.refresh_from_db()
                    self.assertEqual(
                        remote.call_count, 1,
                        "a delivery of a decided run fetches nothing again")
                    self.assertEqual(
                        job.status, UpdateJobStatusEnum.NO_UPDATE_NEEDED.value)
                    self.assertEqual(
                        job.done_at is None, case["collects_metadata"],
                        "a redelivery does not close the step of the run")

                    # what closes a WFS' run is its metadata step and what
                    # closes a CSW' run is its update (#1274); both leave
                    # done_at behind
                    job.metadata_step_completed()
                    job.refresh_from_db()
                    self.assertIsNotNone(job.done_at)
                    done_at = job.done_at

                    with self.captureOnCommitCallbacks(execute=True):
                        case["runner"](update_job_id=job.pk)
                    job.refresh_from_db()
                self.assertEqual(
                    remote.call_count, 1,
                    "nobody fetches the document of a service which decided")
                self.assertEqual(job.done_at, done_at)
                self.assertEqual(
                    job.status, UpdateJobStatusEnum.NO_UPDATE_NEEDED.value)

    def test_redelivered_runner_leaves_a_pending_review_alone(self):
        """A delivery which arrives for a job at a review works nothing.

        A renamed feature type is a change an update may not decide alone: the
        run stands at REVIEW_REQUIRED with its candidate and its unconfirmed
        mappings. Deliveries arrive for such a job from both sides - every
        confirmed mapping enqueues the runner again, a lost worker gives the
        delivery of the interrupted run back - and each of them has to find the
        review where it was, or the answers of the reviewer are thrown away with
        the candidate of the run.
        """
        # a CSW has no elements to map, so only a WFS can stand at a review
        case = self.cases[0]
        service = self.stored_service(case)
        with self.captureOnCommitCallbacks(execute=True):
            job = case["job"].objects.create(service=service)
        with patch.object(Session, "send",
                          return_value=WFS_RENAMED_REMOTE_RESPONSE) as remote:
            with self.captureOnCommitCallbacks(execute=True):
                run_wfs_update(update_job_id=job.pk)
            job.refresh_from_db()
            self.assertEqual(job.status, UpdateJobStatusEnum.REVIEW_REQUIRED.value)
            self.assertIsNone(job.done_at)
            unconfirmed = job.mappings.filter(is_confirmed=False).count()
            self.assertGreater(
                unconfirmed, 0, "the renamed feature type waits for its review")

            # the delivery which comes back for a job which waits: it reads the
            # job under its own lock, answers, and writes nothing - every write
            # of a run which stands at a review belongs to the reviewer's answer
            with CaptureQueriesContext(connection) as queries:
                with self.captureOnCommitCallbacks(execute=True):
                    run_wfs_update(update_job_id=job.pk)
            writes = [
                statement
                for verb in ("insert", "update", "delete")
                for statement in statements_of(queries, verb=verb)]
            job.refresh_from_db()
        self.assertEqual(
            remote.call_count, 1, "a review which is open is not worked again")
        self.assertEqual(
            [statement["sql"] for statement in writes], [],
            "the delivery of an unanswered review changes nothing")
        self.assertEqual(job.status, UpdateJobStatusEnum.REVIEW_REQUIRED.value)
        self.assertIsNone(job.done_at)
        self.assertEqual(job.mappings.filter(is_confirmed=False).count(), unconfirmed)
        self.assertTrue(
            WebFeatureService.objects.filter(update_candidate_of=service).exists(),
            "the candidate whose mapping waits is still there to answer")

    def test_stale_job_does_not_block_the_next_period(self):
        """The delivery which comes back for an unworked job still works it.

        This is the shape a worker which died leaves behind: the transaction of
        the run went back with it, so the job of the service is unfinished and
        stands WAITING_FOR_PROCESSING. The guard of a runner must not turn such
        a delivery away - the schedule re-uses this job without enqueueing
        anything, so the delivery which came back is the only thing which can
        still answer it, and a service whose job is refused has no update in
        every following period either.
        """
        for case in self.cases:
            with self.subTest(service=case["service"].__name__):
                service = self.stored_service(case)
                setting = case["setting"].objects.create(
                    service=service, interval=self.interval)
                with self.captureOnCommitCallbacks(execute=True):
                    stale = case["job"].objects.create(
                        service=service,
                        status=UpdateJobStatusEnum.WAITING_FOR_PROCESSING.value)
                self.published[case["runner"].name].reset_mock()

                with patch.object(
                        Session, "send", return_value=case["remote"]) as remote:
                    with self.captureOnCommitCallbacks(execute=True):
                        case["runner"](update_job_id=stale.pk)
                self.assertEqual(remote.call_count, 1, "the delivery worked the stale job")
                job = case["job"].objects.get(pk=stale.pk)
                self.assertEqual(
                    job.status, UpdateJobStatusEnum.NO_UPDATE_NEEDED.value)
                # the step which closes the run answers here (see above)
                job.metadata_step_completed()
                job.refresh_from_db()
                self.assertIsNotNone(job.done_at, "the stale job is over")

                # the schedule goes on: the next period finds no unfinished job
                # anymore and creates the one it enqueues itself
                with self.captureOnCommitCallbacks(execute=True):
                    job_id = case["create"](name=setting.name)
                self.assertNotEqual(job_id, stale.pk)
                self.published[case["runner"].name].assert_called_once_with(
                    kwargs={"update_job_id": job_id})
                self.assertEqual(
                    service.update_jobs.filter(done_at__isnull=True).get().pk, job_id)

    def test_transient_failure_retries_without_finishing_the_job(self):
        """A remote which is unreachable hands the run back to the broker.

        The job of a retried run keeps its open state: the retry answers it, not
        a report which says the service was updated.
        """
        for case in self.cases:
            with self.subTest(service=case["service"].__name__):
                service = self.stored_service(case)
                with self.captureOnCommitCallbacks(execute=True):
                    job = case["job"].objects.create(service=service)
                with patch.object(Session, "send",
                                  side_effect=ConnectionError("unavailable")):
                    with patch.object(case["runner"], "retry",
                                      side_effect=Retry()) as retry:
                        # Invoke directly: Celery's task signals close
                        # connections, which would discard the outer transaction
                        # owned by Django's TestCase.
                        with self.assertRaises(Retry):
                            case["runner"](update_job_id=job.pk)
                retry.assert_called_once()
                self.assertIsInstance(retry.call_args.kwargs["exc"], ConnectionError)
                job.refresh_from_db()
                self.assertIsNone(job.done_at)
                self.assertEqual(
                    job.status, UpdateJobStatusEnum.WAITING_FOR_PROCESSING.value)
