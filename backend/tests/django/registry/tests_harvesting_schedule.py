"""Tests the two numbers a tight harvesting schedule is decided by (#693).

A schedule which fires more often than a harvest takes is answered to an
administrator as a warning, so the test of it is the answer of both sides of the
comparison: the distance of two runs of a crontab, which is calculated without a
database, and the duration the harvests of a catalogue measured, which is
answered by the runs which finished.
"""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from django.test import SimpleTestCase, TestCase
from django.utils.timezone import now
from django_celery_beat.models import CrontabSchedule
from extras.scheduling import (format_duration, run_interval,
                               schedule_is_tighter_than)
from registry.enums.harvesting import HarvestingPhaseEnum as Phase
from registry.models.harvest import HarvestingJob, PeriodicHarvestingJob
from registry.models.service import CatalogueService
from registry.querys.harvest_history import harvest_durations

CSW_ONE = "9cc4889d-0cd4-4c3b-8975-58de6d30db41"


class HarvestingScheduleIntervalTest(SimpleTestCase):
    """The distance of two runs of a harvesting schedule."""

    def setting(self, scheduling='*/5 * * * *', **kwargs):
        """A scheduled harvesting which was last made at a known moment.

        Args:
            scheduling (str): the crontab of the schedule as an administrator
                writes it into the screen of a schedule
            **kwargs: the values of the schedule to answer differently
        """
        made = datetime(2026, 10, 27, 8, 1, 25, tzinfo=timezone.utc)
        minute, hour, day_of_month, month_of_year, day_of_week = \
            scheduling.split()
        values = dict(
            # an id keeps a scheduled job from making the task and the system
            # user of its defaults, which both ask a database
            pk=1, date_changed=made, enabled=True,
            crontab=CrontabSchedule(
                id=1, minute=minute, hour=hour, day_of_week=day_of_week,
                day_of_month=day_of_month, month_of_year=month_of_year,
                timezone=ZoneInfo('UTC')))
        values.update(kwargs)
        return PeriodicHarvestingJob(**values)

    def test_a_crontab_of_five_minutes_waits_five_minutes(self):
        self.assertEqual(run_interval(self.setting()), timedelta(minutes=5))

    def test_a_crontab_of_every_day_waits_a_day(self):
        self.assertEqual(
            run_interval(self.setting(scheduling='0 8 * * *')),
            timedelta(hours=24))

    def test_a_disabled_schedule_waits_for_nothing(self):
        self.assertIsNone(run_interval(self.setting(enabled=False)))

    def test_a_one_off_which_ran_waits_for_nothing(self):
        self.assertIsNone(
            run_interval(self.setting(one_off=True, total_run_count=1)))

    def test_a_schedule_is_tighter_than_a_harvest_it_does_not_wait_for(self):
        self.assertTrue(
            schedule_is_tighter_than(self.setting(), timedelta(minutes=40)))

    def test_a_schedule_which_the_harvest_meets_is_not_too_tight(self):
        """the warning is about a schedule which cannot wait long enough"""
        hourly = self.setting(scheduling='0 * * * *')
        self.assertFalse(
            schedule_is_tighter_than(hourly, timedelta(minutes=40)))
        # a harvest which takes exactly as long as the schedule waits still
        # reaches the dispatch which follows it
        self.assertFalse(schedule_is_tighter_than(hourly, timedelta(hours=1)))

    def test_a_catalogue_which_never_harvested_is_never_too_tight(self):
        self.assertFalse(schedule_is_tighter_than(self.setting(), None))

    def test_a_duration_is_named_the_way_a_run_names_it(self):
        self.assertEqual(format_duration(timedelta(minutes=40)), '0:40:00')
        self.assertEqual(
            format_duration(timedelta(hours=26, minutes=5, seconds=9)),
            '26:05:09')


class HarvestDurationEstimateTest(TestCase):
    """The duration a harvest of a catalogue takes, measured by its finished runs."""

    fixtures = ["test_users.json", "test_keywords.json", "test_crs.json",
                "test_csw.json"]

    def setUp(self):
        self.csw = CatalogueService.objects.get(pk=CSW_ONE)

    def harvest(self, phase, made=None, ended=None):
        """A harvesting run of the catalogue which was made at a known moment.

        Args:
            phase: the phase the run is in
            made: the creation date of the run, None when the run has none -
                which is the case of every run a deployment made itself
            ended: the moment the run ended, None while it did not
        """
        return HarvestingJob.objects.create(
            service=self.csw, phase=phase, date_created=made, done_at=ended)

    def test_the_finished_harvests_of_a_catalogue_answer_their_average(self):
        older, newer = now() - timedelta(days=2), now() - timedelta(hours=3)
        self.harvest(Phase.COMPLETED, made=older - timedelta(minutes=30),
                     ended=older)
        self.harvest(Phase.COMPLETED, made=newer - timedelta(minutes=50),
                     ended=newer)

        estimate = harvest_durations([self.csw.pk])[self.csw.pk]
        self.assertEqual(estimate['average'], timedelta(minutes=40))
        self.assertEqual(estimate['last_done'], newer)

    def test_a_harvest_without_a_creation_date_is_measured_by_its_changes(self):
        """the harvesting itself never sets the creation date of a run (#693)

        The moment such a run began is only known by the first row of its change
        log, so that row is what the duration of a real run is measured by.
        """
        job = HarvestingJob.objects.create(
            service=self.csw, phase=Phase.COMPLETED)
        started = job.change_log.order_by('history_date', 'history_id').first()
        HarvestingJob.objects.filter(pk=job.pk).update(
            done_at=started.history_date + timedelta(hours=1))

        estimate = harvest_durations([self.csw.pk])[self.csw.pk]
        self.assertEqual(estimate['average'], timedelta(hours=1))

    def test_a_harvest_which_never_finished_is_no_duration(self):
        ended = now()
        self.harvest(Phase.ABORTED, made=ended - timedelta(minutes=30),
                     ended=ended)
        self.harvest(Phase.DOWNLOAD_RECORDS, made=ended - timedelta(minutes=30))
        self.assertEqual(harvest_durations([self.csw.pk]), {})

    def test_a_catalogue_without_a_harvest_answers_no_estimate(self):
        self.assertEqual(harvest_durations([self.csw.pk]), {})
