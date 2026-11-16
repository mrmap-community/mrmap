"""The estimator contract of #1325: elapsed time, queue wait and worker time apart.

The tests answer the questions the acceptance criteria ask, always from the
typed result of `periodic_capacity_estimate`: which of the three durations a
number belongs to, how well it is measured, and what the estimator must
never do - present the four hours a monitoring run waited for its probe as
worker time, equate a fan-out's wall clock with slot occupancy, rename the
#693 average into a p95, or read more rows than the one service asked about.
"""
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from zoneinfo import ZoneInfo

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils.timezone import now
from django_celery_beat.models import CrontabSchedule, PeriodicTask
from extras.scheduling import run_interval
from notify.enums import ProcessNameEnum, ProcessStatusEnum
from notify.models import BackgroundProcess
from registry.enums.capacity import (EstimateGapEnum, EvidenceQualityEnum,
                                     RunOperationEnum)
from registry.enums.harvesting import HarvestingPhaseEnum as Phase
from registry.enums.update import UpdateJobStatusEnum
from registry.models.harvest import HarvestingJob
from registry.models.monitoring import (GetMapProbeResult,
                                        WebMapServiceMonitoringRun,
                                        WebMapServiceMonitoringSetting)
from registry.models.service import CatalogueService, WebMapService
from registry.models.update import (WebMapServiceUpdateJob,
                                    WebMapServiceUpdateSetting)
from registry.querys.capacity import (LOOKBACK_DAYS, P95_MIN_SAMPLES,
                                      ScheduleProposal,
                                      periodic_capacity_estimate)
from registry.querys.harvest_history import harvest_durations

WMS_ONE = 'cd16cc1f-3abb-4625-bb96-fbe80dbe23e3'
WMS_TWO = '1b195589-dcfa-403f-9e66-e7e1c0a67024'
CSW_ONE = "9cc4889d-0cd4-4c3b-8975-58de6d30db41"


class CapacityEstimateTestCase(TestCase):
    """Shared fixtures: schedules and the runs they dispatched."""

    fixtures = ["test_users.json", "test_keywords.json", "test_crs.json",
                "test_wms.json", "test_csw.json"]

    def setUp(self):
        self.wms = WebMapService.objects.get(pk=WMS_ONE)
        self.other_wms = WebMapService.objects.get(pk=WMS_TWO)
        self.csw = CatalogueService.objects.get(pk=CSW_ONE)

    def crontab(self, scheduling='*/5 * * * *', tz='UTC'):
        """A crontab row as the schedule screen would have made it."""
        minute, hour, day_of_month, month_of_year, day_of_week = \
            scheduling.split()
        return CrontabSchedule.objects.create(
            minute=minute, hour=hour, day_of_month=day_of_month,
            month_of_year=month_of_year, day_of_week=day_of_week,
            timezone=ZoneInfo(tz))

    def monitoring_setting(self, service=None, scheduling='*/5 * * * *',
                           tz='UTC', **kwargs):
        """A saved monitoring schedule of a service."""
        return WebMapServiceMonitoringSetting.objects.create(
            service=service or self.wms,
            crontab=self.crontab(scheduling, tz),
            name=str(uuid4()), **kwargs)

    def update_setting(self, service=None, scheduling='0 8 * * *',
                       **kwargs):
        """A saved update schedule of a service."""
        return WebMapServiceUpdateSetting.objects.create(
            service=service or self.wms,
            crontab=self.crontab(scheduling),
            name=str(uuid4()), **kwargs)

    def process(self, status):
        """A background process which reported a run at a terminal status."""
        return BackgroundProcess.objects.create(
            phase="Capacity test", process_type=ProcessNameEnum.MONITORING.value,
            description="capacity test", status=status)

    def monitoring_run(self, setting, duration, ended=None,
                       status=ProcessStatusEnum.COMPLETED, failing=False):
        """A monitoring run which ended `duration` after it was created.

        The timestamps are written the way the deployment writes them: the
        run is created while it waits and `finish_run` answers `date_done`
        when the last probe reported - so the duration is elapsed time,
        waiting for a worker and for the fan-out callback included.
        """
        run = WebMapServiceMonitoringRun.objects.create(
            setting=setting, background_process=self.process(status))
        ended = ended or now()
        WebMapServiceMonitoringRun.objects.filter(pk=run.pk).update(
            date_created=ended - duration, date_done=ended)
        if failing:
            GetMapProbeResult.objects.create(
                run=run, monitored_uri='http://example.com/wms',
                check_response_image_success=False)
        return run

    def harvest(self, made, ended, phase=Phase.COMPLETED, service=None):
        """A harvesting run of the catalogue which was made at a known moment."""
        return HarvestingJob.objects.create(
            service=service or self.csw, phase=phase,
            date_created=made, done_at=ended)

    def update_job(self, made, ended, status, service=None):
        """An update job which was created `made` and ended `ended`.

        `date_created` is answered by `auto_now_add`, so the moment is
        written behind the object's back - the row then carries the same
        pair of verified dates a real finished job carries.
        """
        job = WebMapServiceUpdateJob.objects.create(
            service=service or self.wms, status=status, done_at=ended)
        WebMapServiceUpdateJob.objects.filter(pk=job.pk).update(
            date_created=made)
        return job

    def estimate(self, service, operation, **kwargs):
        return periodic_capacity_estimate(
            type(service), service.pk, operation, **kwargs)


class ElapsedIsNotWorkerTimeTest(CapacityEstimateTestCase):
    """The durations of one run answered apart - the core distinction of #1325."""

    def test_a_run_that_waited_hours_before_its_probe_measures_elapsed_only(self):
        """the acceptance fixture: four hours of waiting, two seconds of probe

        `date_created` to `date_done` is four hours and two seconds - the
        run waited for a worker and the chord callback before its probe ran.
        The estimator may answer this as elapsed time and must never answer
        it as worker time, which it has no per-task event for.
        """
        setting = self.monitoring_setting()
        self.monitoring_run(setting, timedelta(hours=4, seconds=2))

        estimate = self.estimate(self.wms, 'monitoring', setting=setting)

        self.assertEqual(estimate.elapsed.evidence,
                         EvidenceQualityEnum.MEASURED_ELAPSED.value)
        self.assertEqual(estimate.elapsed.median_seconds, 4 * 3600 + 2)
        self.assertIsNone(estimate.worker_slot.seconds)
        self.assertEqual(estimate.worker_slot.evidence,
                         EvidenceQualityEnum.UNKNOWN.value)
        self.assertEqual(estimate.worker_slot.gap,
                         EstimateGapEnum.WORKER_TELEMETRY_MISSING.value)
        self.assertNotEqual(estimate.worker_slot.seconds,
                            estimate.elapsed.median_seconds)
        self.assertIsNone(estimate.queue_wait.seconds)
        self.assertEqual(estimate.queue_wait.gap,
                         EstimateGapEnum.QUEUE_PAIR_MISSING.value)

    def test_a_fan_out_run_never_equates_wall_clock_with_slot_occupancy(self):
        """a fan-out harvest: one elapsed wall clock, many tasks - types apart

        A harvesting run is a fan-out of download and import tasks behind a
        chord; its `done_at` is the completion of the whole fan-out. Even a
        history large enough for a p95 leaves the worker slot answer null:
        the elapsed observations live in another type with another evidence
        quality and are never equated with occupancy.
        """
        made = now()
        for index in range(P95_MIN_SAMPLES):
            self.harvest(made - timedelta(minutes=42, days=index),
                         made - timedelta(minutes=2, days=index))

        estimate = self.estimate(self.csw, 'harvest')

        self.assertEqual(estimate.elapsed.evidence,
                         EvidenceQualityEnum.MEASURED_ELAPSED.value)
        self.assertEqual(estimate.elapsed.p95_seconds, 40 * 60)
        self.assertIsNone(estimate.worker_slot.seconds)
        self.assertNotIsInstance(estimate.worker_slot, type(estimate.elapsed))
        self.assertNotEqual(estimate.worker_slot.evidence,
                            estimate.elapsed.evidence)

    def test_queue_wait_is_answered_as_a_third_own_metric(self):
        """no subtraction of job timestamps stands in for the queue wait"""
        setting = self.monitoring_setting()
        self.monitoring_run(setting, timedelta(minutes=10))

        estimate = self.estimate(self.wms, 'monitoring', setting=setting)

        self.assertIsNot(type(estimate.queue_wait), type(estimate.elapsed))
        self.assertIsNone(estimate.queue_wait.seconds)
        self.assertNotEqual(estimate.queue_wait.evidence,
                            estimate.elapsed.evidence)


class SampleSizePolicyTest(CapacityEstimateTestCase):
    """0, 3, 19 and 20 completed histories answer deterministically (#1325)."""

    def setUp(self):
        super().setUp()
        self.setting = self.monitoring_setting()

    def history(self, count, minutes=1, ended=None):
        """`count` completed runs, one minute apart, `minutes` minutes long."""
        ended = ended or now()
        for index in range(count):
            self.monitoring_run(
                self.setting, timedelta(minutes=minutes),
                ended=ended - timedelta(days=index))

    def test_no_history_is_unknown_with_a_reason_and_never_a_zero_cost(self):
        estimate = self.estimate(self.wms, 'monitoring', setting=self.setting)

        self.assertEqual(estimate.elapsed.evidence,
                         EvidenceQualityEnum.UNKNOWN.value)
        self.assertIsNone(estimate.elapsed.median_seconds)
        self.assertIsNone(estimate.elapsed.p95_seconds)
        self.assertIsNone(estimate.elapsed.average_seconds)
        self.assertIn(EstimateGapEnum.NO_COMPLETED_RUNS.value,
                      estimate.elapsed.gaps)
        self.assertIsNone(estimate.overlap.potential_overlap)

    def test_three_completed_runs_answer_a_median_but_no_p95(self):
        self.history(3, minutes=10)

        estimate = self.estimate(self.wms, 'monitoring', setting=self.setting)

        self.assertEqual(estimate.elapsed.sample_count, 3)
        self.assertEqual(estimate.elapsed.median_seconds, 10 * 60)
        self.assertIsNone(estimate.elapsed.p95_seconds)
        self.assertIn(EstimateGapEnum.INSUFFICIENT_SAMPLES.value,
                      estimate.elapsed.gaps)

    def test_nineteen_completed_runs_still_answer_no_p95(self):
        self.history(P95_MIN_SAMPLES - 1)

        estimate = self.estimate(self.wms, 'monitoring', setting=self.setting)

        self.assertEqual(estimate.elapsed.sample_count, P95_MIN_SAMPLES - 1)
        self.assertIsNotNone(estimate.elapsed.median_seconds)
        self.assertIsNone(estimate.elapsed.p95_seconds)
        self.assertIn(EstimateGapEnum.INSUFFICIENT_SAMPLES.value,
                      estimate.elapsed.gaps)

    def test_twenty_completed_runs_answer_the_nearest_rank_p95(self):
        ended = now()
        for index in range(P95_MIN_SAMPLES):
            self.monitoring_run(self.setting, timedelta(minutes=index + 1),
                                ended=ended - timedelta(days=index))

        estimate = self.estimate(self.wms, 'monitoring', setting=self.setting)

        self.assertEqual(estimate.elapsed.sample_count, P95_MIN_SAMPLES)
        # nearest rank over 1..20 minutes: p50 = ceil(10) -> 10, p95 =
        # ceil(19) -> 19 - sorted, no interpolation
        self.assertEqual(estimate.elapsed.median_seconds, 10 * 60)
        self.assertEqual(estimate.elapsed.p95_seconds, 19 * 60)
        self.assertEqual(estimate.elapsed.gaps, ())


class FailedIncompleteAndSkewedTest(CapacityEstimateTestCase):
    """Failures are counted, not averaged; a skewed row is no observation."""

    def setUp(self):
        super().setUp()
        self.setting = self.monitoring_setting()

    def test_failed_runs_leave_the_baseline_and_are_counted_separately(self):
        ended = now()
        self.monitoring_run(self.setting, timedelta(seconds=60),
                            ended=ended)
        self.monitoring_run(self.setting, timedelta(seconds=120),
                            ended=ended - timedelta(days=1))
        # a run whose probes failed ended, but answers no duration to trust
        self.monitoring_run(self.setting, timedelta(hours=9),
                            ended=ended - timedelta(days=2), failing=True)
        # a run whose task died is failed too, even without a probe result
        self.monitoring_run(self.setting, timedelta(hours=9),
                            ended=ended - timedelta(days=3),
                            status=ProcessStatusEnum.FAILED)
        # and a run which still works did not finish at all
        self.monitoring_run(self.setting, timedelta(hours=9),
                            ended=ended - timedelta(days=4),
                            status=ProcessStatusEnum.RUNNING)

        estimate = self.estimate(self.wms, 'monitoring', setting=self.setting)

        self.assertEqual(estimate.elapsed.sample_count, 2)
        self.assertEqual(estimate.elapsed.median_seconds, 60)
        self.assertEqual(estimate.elapsed.failed_count, 2)
        self.assertEqual(estimate.elapsed.incomplete_count, 1)

    def test_a_completion_before_the_creation_is_no_observation(self):
        """the deterministic policy for the skewed row of a repaired deployment"""
        setting = self.monitoring_setting()
        self.monitoring_run(setting, timedelta(minutes=10))
        skewed = self.monitoring_run(setting, timedelta(minutes=-30))
        skewed.refresh_from_db()
        # the fixture stands as a skewed repaired row: its completion is
        # stored before its creation, so it measures a negative duration
        self.assertLess(skewed.date_done, skewed.date_created)

        estimate = self.estimate(self.wms, 'monitoring', setting=setting)

        self.assertEqual(estimate.elapsed.sample_count, 1)
        self.assertEqual(estimate.elapsed.median_seconds, 10 * 60)
        self.assertEqual(estimate.elapsed.incomplete_count, 1)

    def test_a_finished_run_without_a_creation_answers_the_missing_timestamps_gap(self):
        setting = self.monitoring_setting()
        run = self.monitoring_run(setting, timedelta(minutes=5))
        WebMapServiceMonitoringRun.objects.filter(pk=run.pk).update(
            date_created=None)

        estimate = self.estimate(self.wms, 'monitoring', setting=setting)

        self.assertEqual(estimate.elapsed.sample_count, 0)
        self.assertIn(EstimateGapEnum.MISSING_TIMESTAMPS.value,
                      estimate.elapsed.gaps)
        self.assertEqual(estimate.elapsed.incomplete_count, 1)

    def test_an_outlier_shows_in_the_p95_and_not_in_the_median(self):
        ended = now()
        for index in range(20):
            self.monitoring_run(self.setting, timedelta(minutes=index + 1),
                                ended=ended - timedelta(days=index))
        self.monitoring_run(self.setting, timedelta(hours=5),
                            ended=ended - timedelta(days=25))

        estimate = self.estimate(self.wms, 'monitoring', setting=self.setting)

        self.assertEqual(estimate.elapsed.sample_count, 21)
        self.assertEqual(estimate.elapsed.median_seconds, 11 * 60)
        # nearest rank of 21 observations: p95 = ceil(19.95) -> the 20th
        self.assertEqual(estimate.elapsed.p95_seconds, 20 * 60)


class StaleHistoryTest(CapacityEstimateTestCase):
    """Very old observations age out of the measured baseline, visibly."""

    def test_only_old_runs_answer_a_prior_but_no_measured_percentile(self):
        setting = self.monitoring_setting()
        stale = now() - timedelta(days=LOOKBACK_DAYS + 40)
        self.monitoring_run(setting, timedelta(minutes=10), ended=stale)
        self.monitoring_run(setting, timedelta(minutes=20),
                            ended=stale - timedelta(days=7))

        estimate = self.estimate(self.wms, 'monitoring', setting=setting)

        self.assertEqual(estimate.elapsed.evidence,
                         EvidenceQualityEnum.ESTIMATED_PRIOR.value)
        self.assertIn(EstimateGapEnum.OUTSIDE_LOOKBACK.value,
                      estimate.elapsed.gaps)
        self.assertIsNone(estimate.elapsed.median_seconds)
        self.assertIsNone(estimate.elapsed.p95_seconds)
        self.assertEqual(estimate.elapsed.average_seconds, 15 * 60)
        self.assertEqual(estimate.elapsed.last_measurement_at, stale)

    def test_a_prior_is_never_silently_compared_into_the_overlap_flag(self):
        setting = self.monitoring_setting(scheduling='* * * * *')
        stale = now() - timedelta(days=LOOKBACK_DAYS + 1)
        self.monitoring_run(setting, timedelta(minutes=30), ended=stale)

        estimate = self.estimate(self.wms, 'monitoring', setting=setting)

        self.assertIsNone(estimate.overlap.potential_overlap)
        self.assertIn(EstimateGapEnum.OUTSIDE_LOOKBACK.value,
                      estimate.overlap.gaps)


class OverlapRiskTest(CapacityEstimateTestCase):
    """The potential overlap flag: decided from measured elapsed, qualified."""

    def test_a_schedule_tighter_than_the_measured_elapsed_is_flagged(self):
        setting = self.monitoring_setting()  # every five minutes
        self.monitoring_run(setting, timedelta(minutes=10))

        estimate = self.estimate(self.wms, 'monitoring', setting=setting)

        self.assertTrue(estimate.overlap.potential_overlap)
        self.assertEqual(estimate.overlap.basis, 'median')
        self.assertEqual(estimate.overlap.interval_seconds, 300)
        # the exact qualifier: concurrency and locking is task-dependent
        self.assertIn('task-specific', str(estimate.overlap.qualifier))
        self.assertIn('does not verify', str(estimate.overlap.qualifier))

    def test_a_schedule_which_the_runs_meet_is_not_flagged(self):
        setting = self.monitoring_setting(scheduling='0 * * * *')
        self.monitoring_run(setting, timedelta(minutes=10))

        estimate = self.estimate(self.wms, 'monitoring', setting=setting)

        self.assertFalse(estimate.overlap.potential_overlap)

    def test_the_overlap_of_a_proposal_is_decided_from_the_proposed_schedule(self):
        self.monitoring_run(self.monitoring_setting(scheduling='0 * * * *'),
                            timedelta(minutes=30))

        estimate = self.estimate(
            self.wms, 'monitoring',
            proposal=ScheduleProposal(crontab='*/5 * * * *'))

        self.assertTrue(estimate.overlap.potential_overlap)
        self.assertEqual(estimate.overlap.basis, 'median')
        self.assertEqual(estimate.overlap.interval_seconds, 300)


class ScheduleAnswerTest(CapacityEstimateTestCase):
    """Disabled, one-off, unconfigured and proposed schedules answer gaps."""

    def test_a_disabled_schedule_answers_no_interval_and_a_gap(self):
        setting = self.monitoring_setting()
        PeriodicTask.objects.filter(pk=setting.pk).update(enabled=False)
        setting.refresh_from_db()

        estimate = self.estimate(self.wms, 'monitoring', setting=setting)

        self.assertIsNone(estimate.schedule.run_interval_seconds)
        self.assertIn(EstimateGapEnum.SCHEDULE_DISABLED.value,
                      estimate.schedule.gaps)
        self.assertIn(EstimateGapEnum.SCHEDULE_DISABLED.value,
                      estimate.overlap.gaps)

    def test_a_one_off_which_ran_waits_for_no_next_run(self):
        setting = self.monitoring_setting()
        PeriodicTask.objects.filter(pk=setting.pk).update(
            one_off=True, total_run_count=1)
        setting.refresh_from_db()

        estimate = self.estimate(self.wms, 'monitoring', setting=setting)

        self.assertIsNone(estimate.schedule.next_run_expected_at)
        self.assertIn(EstimateGapEnum.ONE_OFF_RAN.value,
                      estimate.schedule.gaps)

    def test_no_setting_and_no_proposal_is_not_configured(self):
        estimate = self.estimate(self.wms, 'monitoring')

        self.assertIn(EstimateGapEnum.NOT_CONFIGURED.value,
                      estimate.schedule.gaps)
        self.assertIsNone(estimate.schedule.run_interval_seconds)

    def test_a_setting_without_a_crontab_answers_the_crontab_gap(self):
        setting = self.update_setting()
        PeriodicTask.objects.filter(pk=setting.pk).update(crontab=None)
        setting.refresh_from_db()

        estimate = self.estimate(self.wms, 'update', setting=setting)

        self.assertIn(EstimateGapEnum.NO_CRONTAB.value,
                      estimate.schedule.gaps)

    def test_a_draft_proposal_answers_next_run_and_interval_without_rows(self):
        estimate = self.estimate(
            self.wms, 'monitoring',
            proposal=ScheduleProposal(crontab='*/5 * * * *'))

        self.assertEqual(estimate.schedule.run_interval_seconds, 300)
        self.assertIsNotNone(estimate.schedule.next_run_expected_at)
        self.assertFalse(estimate.schedule.gaps)
        # nothing measured yet: no overlap decision, but no cost claimed either
        self.assertIsNone(estimate.overlap.potential_overlap)

    def test_a_proposal_carries_the_canonical_semantics_of_a_second_timezone(self):
        """a proposed crontab is decided exactly as a saved one (#1325)

        The proposal pipeline must not invent its own cron math: the answer
        for a proposed crontab in `Europe/Berlin` is the very answer
        `extras.scheduling` gives for a saved setting of the same fields and
        baseline - which is where the 23 and 25 hour distances of a DST
        change live.
        """
        baseline = datetime(2026, 3, 27, 1, 30, tzinfo=timezone.utc)
        saved = WebMapServiceUpdateSetting.objects.create(
            service=self.wms, crontab=self.crontab('30 2 * * *', tz='UTC'),
            name=str(uuid4()))
        PeriodicTask.objects.filter(pk=saved.pk).update(
            last_run_at=baseline, total_run_count=5)
        saved.refresh_from_db()

        utc_proposal = self.estimate(
            self.wms, 'update', setting=saved,
            proposal=ScheduleProposal(crontab='30 2 * * *', timezone='UTC'))
        berlin_proposal = self.estimate(
            self.wms, 'update', setting=saved,
            proposal=ScheduleProposal(crontab='30 2 * * *', timezone='Europe/Berlin'))

        self.assertEqual(
            utc_proposal.schedule.run_interval_seconds,
            run_interval(saved).total_seconds())
        # both answers repeat identically - the multi-timezone cron is
        # decided deterministically, not by the moment the question is asked
        again = self.estimate(
            self.wms, 'update', setting=saved,
            proposal=ScheduleProposal(crontab='30 2 * * *', timezone='Europe/Berlin'))
        self.assertEqual(berlin_proposal.schedule.next_run_expected_at,
                         again.schedule.next_run_expected_at)
        self.assertIsNotNone(berlin_proposal.schedule.next_run_expected_at)


class SourceValidationTest(CapacityEstimateTestCase):
    """Unknown, foreign and unsupported inputs degrade, they never raise."""

    def test_an_unknown_service_kind_is_no_estimate(self):
        estimate = periodic_capacity_estimate(
            'Layer', WMS_ONE, RunOperationEnum.MONITORING)

        self.assertIn(EstimateGapEnum.UNKNOWN_SERVICE.value,
                      estimate.schedule.gaps)
        self.assertEqual(estimate.elapsed.sample_count, 0)

    def test_an_unknown_service_id_is_no_estimate(self):
        estimate = self.estimate_layer_style(uuid4(), 'monitoring')

        self.assertIn(EstimateGapEnum.UNKNOWN_SERVICE.value,
                      estimate.elapsed.gaps)

    def test_an_unparsable_service_id_is_no_estimate_instead_of_an_error(self):
        estimate = self.estimate_layer_style('not-a-uuid', 'monitoring')

        self.assertIn(EstimateGapEnum.UNKNOWN_SERVICE.value,
                      estimate.elapsed.gaps)

    def estimate_layer_style(self, service_id, operation):
        return periodic_capacity_estimate(
            WebMapService, service_id, operation)

    def test_a_setting_of_another_service_is_rejected_as_invalid_source(self):
        foreign = self.monitoring_setting(service=self.other_wms)

        estimate = self.estimate(self.wms, 'monitoring', setting=foreign)

        self.assertIn(EstimateGapEnum.INVALID_SETTING.value,
                      estimate.elapsed.gaps)

    def test_harvesting_a_web_map_service_is_an_unsupported_variant(self):
        estimate = self.estimate(self.wms, 'harvest')

        self.assertIn(EstimateGapEnum.UNSUPPORTED_OPERATION.value,
                      estimate.elapsed.gaps)

    def test_an_unparsable_proposal_is_answered_as_invalid(self):
        estimate = self.estimate(
            self.wms, 'monitoring',
            proposal=ScheduleProposal(crontab='every five minutes'))

        self.assertIn(EstimateGapEnum.INVALID_PROPOSAL.value,
                      estimate.schedule.gaps)
        self.assertIsNone(estimate.schedule.run_interval_seconds)

    def test_the_asked_scope_travels_with_the_answer_without_filtering(self):
        setting = self.monitoring_setting()
        self.monitoring_run(setting, timedelta(minutes=10))

        estimate = self.estimate(self.wms, 'monitoring', setting=setting,
                                 scope=('layer:16b93d90',))

        self.assertEqual(estimate.scope, ('layer:16b93d90',))
        self.assertEqual(estimate.elapsed.sample_count, 1)

    def test_an_unsupported_operation_name_degrades(self):
        estimate = periodic_capacity_estimate(
            WebMapService, WMS_ONE, 'teleport')

        self.assertIn(EstimateGapEnum.UNSUPPORTED_OPERATION.value,
                      estimate.elapsed.gaps)


class UpdateHistoryTest(CapacityEstimateTestCase):
    """The update jobs of a service answer their verified date pair."""

    def test_only_the_terminal_statuses_measure_a_completed_update(self):
        made = now()
        self.update_job(made - timedelta(minutes=40), made - timedelta(minutes=1),
                        UpdateJobStatusEnum.UPDATED.value)
        self.update_job(made - timedelta(minutes=90), made - timedelta(minutes=30),
                        UpdateJobStatusEnum.NO_UPDATE_NEEDED.value)
        self.update_job(made - timedelta(minutes=600), made - timedelta(minutes=120),
                        UpdateJobStatusEnum.ERROR.value)
        # a job which waits for a review is not finished: no terminal date pair
        self.update_job(made - timedelta(minutes=60), None,
                        UpdateJobStatusEnum.REVIEW_REQUIRED.value)

        estimate = self.estimate(self.wms, 'update')

        self.assertEqual(estimate.elapsed.sample_count, 2)
        self.assertEqual(estimate.elapsed.median_seconds, 39 * 60)
        self.assertEqual(estimate.elapsed.failed_count, 1)
        self.assertEqual(estimate.elapsed.incomplete_count, 1)


class ScheduleSixNinetyThreeCompatibilityTest(CapacityEstimateTestCase):
    """The #693 estimate stays what it was: an average, never a worker cost."""

    def test_the_estimator_carries_the_693_average_under_its_own_name(self):
        made = now()
        self.harvest(made - timedelta(minutes=30), made)
        self.harvest(made - timedelta(minutes=90), made - timedelta(minutes=40))

        durations = harvest_durations([self.csw.pk])[self.csw.pk]
        estimate = self.estimate(self.csw, 'harvest')

        self.assertEqual(estimate.elapsed.average_seconds,
                         durations['average'].total_seconds())
        # two observations answer no p95 - the average alone is the #693
        # answer and the estimator does not rename it into a percentile
        self.assertIsNone(estimate.elapsed.p95_seconds)
        self.assertEqual(estimate.elapsed.sample_count, 2)
        # and no field of the elapsed metric ever claims worker seconds
        elapsed_fields = {f.name for f in
                          estimate.elapsed.__dataclass_fields__.values()}
        self.assertTrue(all('worker' not in name for name in elapsed_fields))
        self.assertEqual(estimate.elapsed.last_measurement_at,
                         durations['last_done'])


class BoundedQueryTest(CapacityEstimateTestCase):
    """One single-setting preview costs no global scan and no row loop (#1308)."""

    def queries_of(self, service_kind, service_id, operation,
                   setting_pk=None):
        """The queries of one estimate, answering as a view would.

        The setting is taken with its crontab, like the viewsets of the
        schedules do, and it is taken inside the measured window so that
        both measurements see the same shape of work.
        """
        with CaptureQueriesContext(connection) as captured:
            setting = None
            if setting_pk is not None:
                setting = WebMapServiceMonitoringSetting.objects \
                    .select_related('crontab').get(pk=setting_pk)
            periodic_capacity_estimate(
                service_kind, service_id, operation, setting=setting)
        return len(captured.captured_queries)

    def test_the_monitoring_estimate_costs_the_same_at_5_and_at_50_runs(self):
        setting = self.monitoring_setting()
        ended = now()
        for index in range(5):
            self.monitoring_run(setting, timedelta(minutes=5),
                                ended=ended - timedelta(days=index))

        few = self.queries_of(WebMapService, WMS_ONE, 'monitoring',
                              setting_pk=setting.pk)

        # more history of this service and full tables of every other
        # service may not add one query: the preview is bounded by the
        # service it answers, never by the alert state of the deployment
        for index in range(45):
            self.monitoring_run(setting, timedelta(minutes=5),
                                ended=ended - timedelta(days=index))
        other_setting = self.monitoring_setting(service=self.other_wms)
        for index in range(50):
            self.monitoring_run(other_setting, timedelta(minutes=5),
                                ended=ended - timedelta(days=index))

        many = self.queries_of(WebMapService, WMS_ONE, 'monitoring',
                               setting_pk=setting.pk)

        self.assertEqual(few, many)
        self.assertLessEqual(few, 8)

    def test_the_harvest_estimate_stays_bounded_as_the_catalogue_grows(self):
        made = now()
        for index in range(5):
            self.harvest(made - timedelta(minutes=42, days=index),
                         made - timedelta(days=index))

        few = self.queries_of(CatalogueService, CSW_ONE, 'harvest')

        for index in range(5, 60):
            self.harvest(made - timedelta(minutes=42, days=index),
                         made - timedelta(days=index))

        many = self.queries_of(CatalogueService, CSW_ONE, 'harvest')

        self.assertEqual(few, many)
        self.assertLessEqual(few, 8)
