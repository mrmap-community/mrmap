"""The sweep of stale unfinished service-update jobs (#1460).

An unfinished job which nobody drives blocks its service's schedule forever:
the constraint of one unfinished job per service makes every later fire of the
schedule re-use it without enqueueing anything. The sweep fails such jobs once
they stand beyond the configured horizon and reports the incident of #1319
about every service it decided about; fresh jobs, mappings which wait for a
human review and runs which only stand at their metadata step are left alone.
"""
from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase
from django.test.utils import override_settings
from django.utils import timezone
from django_celery_beat.models import CrontabSchedule, IntervalSchedule, \
    PeriodicTask
from notify.enums import (IncidentSeverityEnum, IncidentSourceEnum,
                          IncidentStatusEnum, ProcessStatusEnum)
from notify.incident_reporting import WATCHDOG_CODE_PREFIX
from notify.models import BackgroundProcessLog, OperationalIncident
from registry.apps import STALE_UPDATE_JOB_SWEEP_TASK_NAME
from registry.enums.update import UpdateJobStatusEnum
from registry.models.service import (CatalogueService, WebFeatureService,
                                     WebMapService)
from registry.models.update import (CatalogueServiceUpdateJob,
                                    WebFeatureServiceUpdateJob,
                                    WebFeatureServiceUpdateSetting,
                                    WebMapServiceUpdateJob)
from registry.tasks.update import (STALE_SWEEP_STATUSES,
                                   STALE_UPDATE_JOB_CODE_SUFFIX,
                                   sweep_stale_update_job,
                                   sweep_stale_update_jobs,
                                   update_job_stale_horizon)
from tests.django.sql_guard import SqlGuardMixin

# every concrete kind of service-update job, with its service
CASES = (
    (WebMapService, WebMapServiceUpdateJob),
    (WebFeatureService, WebFeatureServiceUpdateJob),
    (CatalogueService, CatalogueServiceUpdateJob),
)

#: what a fire may never decide about: a mapping belongs to the human who was
#: asked to answer it (#1207), and a decided status with an open ``done_at``
#: is the metadata step of #1274 which its own recovery redrives
UNTOUCHABLE_STATUSES = [
    UpdateJobStatusEnum.REVIEW_REQUIRED,
    UpdateJobStatusEnum.UPDATED,
    UpdateJobStatusEnum.NO_UPDATE_NEEDED,
]

SWEEP_SETTINGS = dict(UPDATE_JOB_STALE_HORIZON_HOURS=6)
STALE = timedelta(hours=7)


def age(job_model, job, moments):
    """Wind the job's creation back behind the moment the sweep reads."""
    job_model.objects.filter(pk=job.pk).update(
        date_created=timezone.now() - moments)


class StaleUpdateJobSweepTest(TestCase):
    """The decision itself, per kind of job and per undecided status."""

    fixtures = [
        "test_users.json", "test_keywords.json", "test_crs.json",
        "test_wms.json", "test_wfs.json", "test_csw.json",
    ]

    def test_stale_undecided_jobs_are_failed(self):
        for service_model, job_model in CASES:
            service = service_model.objects.first()
            for status in STALE_SWEEP_STATUSES:
                with self.subTest(kind=job_model.__name__, status=status):
                    with override_settings(**SWEEP_SETTINGS):
                        job = job_model.objects.create(
                            service=service, status=status)
                        age(job_model, job, STALE)
                        self.assertEqual(
                            sweep_stale_update_jobs.run(), [job.pk])
                    job.refresh_from_db()
                    self.assertEqual(
                        job.status, UpdateJobStatusEnum.ERROR.value)
                    self.assertIsNotNone(
                        job.done_at,
                        "the constraint of one unfinished job only frees "
                        "with the job's end")
                    process = job.background_process
                    self.assertEqual(process.status, ProcessStatusEnum.FAILED)
                    self.assertIsNotNone(process.done_at)
                    log = BackgroundProcessLog.objects.filter(
                        background_process=process).first()
                    self.assertIsNotNone(
                        log, "the sweep tells its decision on the process")
                    self.assertIn("stale update job sweep", log.description)
                    # the service stands free again for its schedule
                    self.assertFalse(job_model.objects.filter(
                        service=service, done_at__isnull=True).exists())

    def test_fresh_jobs_are_left_alone(self):
        for service_model, job_model in CASES:
            with self.subTest(kind=job_model.__name__):
                service = service_model.objects.first()
                fresh = job_model.objects.create(
                    service=service,
                    status=UpdateJobStatusEnum.WAITING_FOR_PROCESSING)
                with override_settings(**SWEEP_SETTINGS):
                    self.assertEqual(sweep_stale_update_jobs.run(), [])
                fresh.refresh_from_db()
                self.assertEqual(
                    fresh.status,
                    UpdateJobStatusEnum.WAITING_FOR_PROCESSING.value)
                self.assertIsNone(fresh.done_at)
                job_model.objects.filter(pk=fresh.pk).delete()

    def test_the_horizon_decides_fresh_from_stale(self):
        """the horizon is the line: inside it a job may still work, beyond it
        nobody drives it anymore (#1460)"""
        services = list(WebFeatureService.objects.all()[:2])
        self.assertGreaterEqual(
            len(services), 2, "the fixture must carry two services")
        stale = WebFeatureServiceUpdateJob.objects.create(
            service=services[0], status=UpdateJobStatusEnum.UPDATING)
        age(WebFeatureServiceUpdateJob, stale, STALE)
        fresh = WebFeatureServiceUpdateJob.objects.create(
            service=services[1], status=UpdateJobStatusEnum.UPDATING)
        with override_settings(**SWEEP_SETTINGS):
            self.assertEqual(sweep_stale_update_jobs.run(), [stale.pk])
        stale.refresh_from_db()
        self.assertEqual(stale.status, UpdateJobStatusEnum.ERROR.value)
        fresh.refresh_from_db()
        self.assertIsNone(fresh.done_at)

    def test_jobs_beyond_the_review_and_the_metadata_step_stand(self):
        """a mapping waits for a human, not for a worker; a run which decided
        its outcome while its metadata step is open is the recovery of #1274,
        not this sweep's work"""
        for service_model, job_model in CASES:
            service = service_model.objects.first()
            for status in UNTOUCHABLE_STATUSES:
                with self.subTest(kind=job_model.__name__, status=status):
                    job = job_model.objects.create(service=service,
                                                   status=status)
                    age(job_model, job, timedelta(days=30))
                    with override_settings(**SWEEP_SETTINGS):
                        self.assertEqual(sweep_stale_update_jobs.run(), [])
                    job.refresh_from_db()
                    self.assertEqual(job.status, status.value)
                    self.assertIsNone(job.done_at)
                    job_model.objects.filter(pk=job.pk).delete()

    def test_a_decided_job_is_never_decided_twice(self):
        """the locked re-read answers a job which ended meanwhile - the runner
        of #1453 which won the lock first included"""
        service = WebFeatureService.objects.first()
        job = WebFeatureServiceUpdateJob.objects.create(service=service)
        job.finish(UpdateJobStatusEnum.UPDATED)
        self.assertFalse(sweep_stale_update_job(
            WebFeatureServiceUpdateJob, job.pk))
        self.assertEqual(
            OperationalIncident.objects.filter(
                code=(f"{WATCHDOG_CODE_PREFIX}"
                      f"{STALE_UPDATE_JOB_CODE_SUFFIX}")).count(), 0)

    def test_the_schedule_of_a_swept_service_creates_a_new_job_again(self):
        """the schedule of the blocked service: before the sweep its fire
        re-uses the stranded job without enqueueing anything; after it, a fresh
        job goes out to a worker again (#1460). The WFS fire is the blocked
        shape the issue names - the WMS' fire re-drives its runner, the
        recovery of #1453, and that runner is decided by the sweep's horizon
        exactly like the stranded WFS job"""
        from registry.tasks.update import create_wfs_update_job

        service = WebFeatureService.objects.first()
        interval = IntervalSchedule.objects.create(every=1, period="days")
        setting = WebFeatureServiceUpdateSetting.objects.create(
            service=service, interval=interval)
        stranded = WebFeatureServiceUpdateJob.objects.create(service=service)
        age(WebFeatureServiceUpdateJob, stranded,
            update_job_stale_horizon() + timedelta(hours=1))
        with patch("registry.tasks.update.run_wfs_update.apply_async") as \
                enqueue:
            with self.captureOnCommitCallbacks(execute=True):
                self.assertEqual(
                    create_wfs_update_job(name=setting.name), stranded.pk)
            enqueue.assert_not_called()

        self.assertEqual(sweep_stale_update_jobs.run(), [stranded.pk])

        with patch("registry.tasks.update.run_wfs_update.apply_async") as \
                enqueue:
            with self.captureOnCommitCallbacks(execute=True):
                fresh_id = create_wfs_update_job(name=setting.name)
            self.assertNotEqual(fresh_id, stranded.pk)
            enqueue.assert_called_once_with(
                kwargs={"update_job_id": fresh_id})


class StaleUpdateJobIncidentTest(TestCase):
    """The alert the sweep gives: the incident channel of #1319, deduplicated
    per service, resolved by the service's next successful update."""

    fixtures = [
        "test_users.json", "test_keywords.json", "test_crs.json",
        "test_wms.json", "test_wfs.json", "test_csw.json",
    ]

    def test_the_sweep_reports_an_incident_per_service(self):
        services = list(WebFeatureService.objects.all()[:2])
        self.assertGreaterEqual(
            len(services), 2, "the fixture must carry two services")
        jobs = [WebFeatureServiceUpdateJob.objects.create(
            service=service, status=status)
            for service, status in zip(
                services, STALE_SWEEP_STATUSES[:2])]
        for job in jobs:
            age(WebFeatureServiceUpdateJob, job, timedelta(days=2))
        with override_settings(**SWEEP_SETTINGS):
            self.assertEqual(
                sweep_stale_update_jobs.run(), sorted(job.pk for job in jobs))
        for job in jobs:
            incident = OperationalIncident.objects.get(
                code=f"{WATCHDOG_CODE_PREFIX}{STALE_UPDATE_JOB_CODE_SUFFIX}",
                web_feature_service=job.service)
            self.assertEqual(incident.source, IncidentSourceEnum.UPDATE.value)
            self.assertEqual(
                incident.severity, IncidentSeverityEnum.ERROR.value)
            self.assertEqual(
                incident.status, IncidentStatusEnum.ACTIVE.value)
            self.assertIn(str(job.pk), incident.summary)

    def test_the_next_successful_update_resolves_the_incident(self):
        service = WebFeatureService.objects.first()
        job = WebFeatureServiceUpdateJob.objects.create(
            service=service, status=UpdateJobStatusEnum.UPDATING)
        age(WebFeatureServiceUpdateJob, job, timedelta(days=2))
        with override_settings(**SWEEP_SETTINGS):
            sweep_stale_update_jobs.run()
        incident = OperationalIncident.objects.get(
            code=f"{WATCHDOG_CODE_PREFIX}{STALE_UPDATE_JOB_CODE_SUFFIX}",
            web_feature_service=service)
        self.assertEqual(incident.status, IncidentStatusEnum.ACTIVE.value)

        # the service updates again and its process completes: by the terminal
        # resolver of #1320 this is the proof that the problem is over
        follow_up = WebFeatureServiceUpdateJob.objects.create(service=service)
        follow_up.finish(UpdateJobStatusEnum.UPDATED)
        incident.refresh_from_db()
        self.assertEqual(incident.status, IncidentStatusEnum.RESOLVED.value)
        self.assertIsNotNone(incident.resolved_at)


class StaleUpdateJobHorizonTest(TestCase):
    """The horizon is the deployment's, with a floor of one hour."""

    def test_the_default_horizon_is_a_day(self):
        self.assertEqual(update_job_stale_horizon(), timedelta(hours=24))

    def test_the_deployment_horizon_wins(self):
        with override_settings(UPDATE_JOB_STALE_HORIZON_HOURS=6):
            self.assertEqual(update_job_stale_horizon(), timedelta(hours=6))

    def test_a_horizon_below_an_hour_is_raised_to_it(self):
        """a 0 would fail jobs which only waited a moment for a busy queue"""
        for value in (0, -5):
            with self.subTest(value=value), override_settings(
                    UPDATE_JOB_STALE_HORIZON_HOURS=value):
                self.assertEqual(
                    update_job_stale_horizon(), timedelta(hours=1))


class StaleUpdateJobBeatRowTest(TestCase):
    """Beat reads its schedule from the database, so the sweep needs its row."""

    def test_the_sweep_is_scheduled_hourly(self):
        row = PeriodicTask.objects.get(name=STALE_UPDATE_JOB_SWEEP_TASK_NAME)
        self.assertEqual(row.task,
                         "registry.tasks.update.sweep_stale_update_jobs")
        self.assertEqual(row.crontab.minute, "50")

    def test_a_rescheduled_row_survives_the_next_migrate(self):
        """the row is keyed by its name: a deployment which chose its own
        schedule over the api keeps it when the handler runs again"""
        from registry.apps import create_stale_update_job_sweep_task

        row = PeriodicTask.objects.get(name=STALE_UPDATE_JOB_SWEEP_TASK_NAME)
        other, _ = CrontabSchedule.objects.get_or_create(
            minute="7", hour="*/6", day_of_week="*",
            day_of_month="*", month_of_year="*")
        row.crontab = other
        row.save()

        create_stale_update_job_sweep_task(None)

        self.assertEqual(PeriodicTask.objects.filter(
            name=STALE_UPDATE_JOB_SWEEP_TASK_NAME).count(), 1)
        row.refresh_from_db()
        self.assertEqual(row.crontab_id, other.id)


class StaleUpdateJobSweepShapeTest(SqlGuardMixin, TestCase):
    """The SQL shape of one fire (#1395): the scan costs one read per job kind
    whatever stands in the tables, and a fire pays its per-row decision
    honestly - the locked read, the job, its process and the incident."""

    fixtures = [
        "test_users.json", "test_keywords.json", "test_crs.json",
        "test_wms.json", "test_wfs.json", "test_csw.json",
    ]

    def test_the_fire_costs_a_scan_plus_the_locked_decision_per_swept_job(self):
        pool = [
            (WebMapServiceUpdateJob,
             WebMapService.objects.first()),
            (WebFeatureServiceUpdateJob,
             WebFeatureService.objects.first()),
            (CatalogueServiceUpdateJob,
             CatalogueService.objects.first()),
        ]

        def seed(size):
            for job_model, service in pool[:size]:
                job = job_model.objects.create(service=service)
                age(job_model, job, timedelta(days=2))

        measured = self.assertQueryCountIndependent(
            sizes=(0, 3),
            seed=seed,
            # the body without the singleton lock: what the fire runs
            run=lambda: sweep_stale_update_jobs.run(),
            # per swept job: the locked read, the job update, the savepoint
            # pair of the decision, the process log, the two reports onto the
            # process, the read of the process for the verdict and the incident
            # upsert - one sanctioned per-record transaction (#895), measured
            # the day it ships (14 statements per decided job)
            per_row=14,
            extra=0,
            label="the stale update job sweep")
        self.assertLessEqual(
            measured[3], measured[0] + 3 * 14,
            "the fire grows with its locked decisions, never with the tables "
            "it scans")
