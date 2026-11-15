"""The cadence suggestions of #1328: verified alternatives or a stated no.

The engine answers entire alternative crontabs which keep the firing count
of the answered schedule - verified by walking original and candidate
through the canonical Beat stepping over one identical dated horizon - and
only ranks them by the measured worker-seconds of the #1326 snapshot. The
acceptance criteria of the issue are answered case by case: ``*/30`` gains
``7,37`` with an equal firing count while a one-off stays refused; DST,
weekday, month-end, rare and leap patterns are tested against a fixed
clock; unknown cost or topology refuses with its reason instead of ranking
a task-count histogram; and no candidate ever scans the schedule tables.
"""
import json
from datetime import datetime, time, timedelta, timezone
from unittest import mock
from zoneinfo import ZoneInfo

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import SimpleTestCase, TestCase
from django.test.utils import CaptureQueriesContext
from django.test import override_settings
from django.utils.timezone import now
from guardian.shortcuts import assign_perm
from registry.enums.capacity import (EstimateGapEnum, SuggestionGapEnum)
from registry.models.monitoring import WebMapServiceMonitoringSetting
from registry.querys.capacity import (PeriodicCapacityEstimate, ScheduleAnswer,
                                      ScheduleProposal)
from registry.querys.schedule_suggestions import cadence_suggestions
from system import capacity_demand
from tests.django.registry.tests_scheduling_preview import \
    SchedulePreviewTestCase

UTC = timezone.utc
BERLIN = ZoneInfo('Europe/Berlin')

WMS_ONE = 'cd16cc1f-3abb-4625-bb96-fbe80dbe23e3'


def estimate_with(*gaps):
    """An estimate answer whose only relevant part is the schedule gaps."""
    return PeriodicCapacityEstimate(schedule=ScheduleAnswer(gaps=gaps))


def proposal(crontab, tz='UTC', enabled=True, **timing):
    """A draft as the preview view hands it to the engine."""
    return ScheduleProposal(enabled=enabled, crontab=crontab,
                            timezone=tz, **timing)


def snapshot(*, queue='monitoring', start, end, bucket_seconds, histogram,
             rho=0.8, coverage=1.0, samples=25, status='ok',
             confidence='complete', available=True, reason=None,
             occurrences=None):
    """A capacity snapshot as the materialized cache of #1326 answers it.

    The moments travel as ISO text exactly like the cached build does; the
    engine must parse them rather than assume datetime objects.
    """
    if available is False:
        return {'available': False, 'reason': reason or 'no snapshot',
                'confidence': 'unknown', 'gaps': []}
    return {
        'available': True,
        'confidence': confidence,
        'snapshot_at': start.isoformat(),
        'horizon': {
            'start': start.isoformat(), 'end': end.isoformat(),
            'bucket_seconds': bucket_seconds, 'buckets': len(histogram),
        },
        'queues': {queue: {
            'status': status,
            'rho': rho,
            'periodic_demand_coverage': coverage,
            'histogram_seconds': histogram,
            'histogram_occurrences': (occurrences
                                      or [0] * len(histogram)),
            'observed': {'coverage': {'terminal_samples': samples}},
        }},
    }


class CadenceSuggestionEngineTest(SimpleTestCase):
    """The engine alone, driven by a fixed clock and an injected snapshot."""

    def engine(self, crontab, at, snap, tz='UTC', enabled=True, **timing):
        """One engine answer for a monitoring draft over `crontab`."""
        return cadence_suggestions(
            None, proposal(crontab, tz=tz, enabled=enabled, **timing),
            estimate_with(), WebMapServiceMonitoringSetting(),
            at=at, snapshot=snap)

    def window_of(self, crontab_str, lower, upper, tz='UTC', budget=20_000):
        """The instants the crontab fires within, by the same walk."""
        minute, hour, dom, month, dow = crontab_str.split()
        crontab = capacity_demand.CrontabSchedule(
            minute=minute, hour=hour, day_of_month=dom, month_of_year=month,
            day_of_week=dow, timezone=ZoneInfo(tz))
        return capacity_demand.walk_crontab(crontab, lower, upper, budget)

    def spike_histogram(self, start, buckets, heavy_minutes, seconds=10.0,
                        bucket_seconds=60):
        """A minute-resolved histogram loading `heavy_minutes` of the hour."""
        histogram = [0.0] * buckets
        for index in range(buckets):
            if (index * bucket_seconds) // 60 % 60 in heavy_minutes:
                histogram[index] = seconds
        return histogram

    # --- AC 1: cadence equivalence, the example of the issue -------------

    def test_alternative_7_37_keeps_the_firing_count_of_the_30_stepping(self):
        at = datetime(2026, 11, 15, 14, 23, tzinfo=UTC)
        window_start = datetime(2026, 11, 16, 0, 0, tzinfo=UTC)
        buckets = 744
        snap = snapshot(
            start=window_start, end=window_start + timedelta(minutes=buckets),
            bucket_seconds=60,
            histogram=self.spike_histogram(window_start, buckets, (0, 30)))

        answer = self.engine('*/30 * * * *', at, snap)

        self.assertTrue(answer.suggestions, answer.reason)
        crontabs = {s.crontab for s in answer.suggestions}
        self.assertIn('7,37 * * * *', crontabs)
        # every suggestion is an entire crontab keeping the cadence - none
        # of them is a single moment like a one-off 14:37
        for suggestion in answer.suggestions:
            self.assertEqual(5, len(suggestion.crontab.split()))
            self.assertEqual(336, suggestion.firing_count)
            self.assertEqual(7, suggestion.horizon_days)
            self.assertEqual(suggestion.horizon_start, window_start)
        # the count was verified against the original by the same walk
        original, truncated = self.window_of(
            '*/30 * * * *', window_start - timedelta(microseconds=1),
            window_start + timedelta(days=7) - timedelta(microseconds=1))
        self.assertFalse(truncated)
        self.assertEqual(336, len(original))
        # the evidence travels with every suggestion
        first = answer.suggestions[0]
        self.assertEqual(25, first.sample_count)
        self.assertEqual(1.0, first.cost_coverage)
        self.assertLess(first.expected_worker_seconds,
                        first.original_worker_seconds)

    def test_a_one_off_schedule_gets_no_alternative(self):
        """another single moment would change the cadence, not only its time"""
        at = datetime(2026, 11, 15, 14, 23, tzinfo=UTC)
        window_start = datetime(2026, 11, 16, 0, 0, tzinfo=UTC)
        snap = snapshot(start=window_start, end=window_start + timedelta(days=8),
                        bucket_seconds=60, histogram=[1.0] * 100)

        answer = self.engine('37 14 * * *', at, snap, one_off=True)

        self.assertEqual((), answer.suggestions)
        self.assertEqual(SuggestionGapEnum.NOT_PERIODIC.value,
                         answer.reason_code)

    def test_disabled_and_missing_schedule_answers_are_no_cadence(self):
        at = datetime(2026, 11, 15, 14, 23, tzinfo=UTC)
        snap = snapshot(start=at, end=at + timedelta(days=8),
                        bucket_seconds=60, histogram=[1.0] * 100)

        disabled = self.engine('*/30 * * * *', at, snap, enabled=False)
        self.assertEqual(SuggestionGapEnum.NOT_PERIODIC.value,
                         disabled.reason_code)

        gap = cadence_suggestions(
            None, proposal('*/30 * * * *'),
            estimate_with(EstimateGapEnum.SCHEDULE_DISABLED.value),
            WebMapServiceMonitoringSetting(), at=at, snapshot=snap)
        self.assertEqual(SuggestionGapEnum.NOT_PERIODIC.value,
                         gap.reason_code)

    # --- AC 2: zones, DST, weekday, month-end, rare, bounds --------------

    def test_the_spring_change_steps_both_schedules_by_the_same_walk(self):
        """Berlin's 2026-03-29 loses hour 02 on the wall clock. What decides
        here is not a wall-clock assumption but Beat's own arithmetic: the
        canonical step answers the 48 firings of the day for EVERY minute
        field alike (the 02:00+01:00 instant it names is a real UTC instant),
        and the suggestion contract is that original and alternative are
        counted by that very same walk over an identical window"""
        at = datetime(2026, 3, 25, 12, 0, tzinfo=UTC)
        window_start = datetime(2026, 3, 26, 0, 0, tzinfo=BERLIN)
        buckets = 744
        snap = snapshot(
            start=window_start, end=window_start + timedelta(minutes=buckets),
            bucket_seconds=60,
            histogram=self.spike_histogram(window_start, buckets, (0, 30)))

        answer = self.engine('*/30 * * * *', at, snap, tz='Europe/Berlin')

        self.assertTrue(answer.suggestions, answer.reason)
        original, _ = self.window_of(
            '*/30 * * * *', window_start - timedelta(microseconds=1),
            window_start + timedelta(days=7) - timedelta(microseconds=1),
            tz='Europe/Berlin')
        self.assertEqual(336, len(original))
        for suggestion in answer.suggestions:
            self.assertEqual(len(original), suggestion.firing_count)
            self.assertEqual('Europe/Berlin', suggestion.timezone)

    def test_the_autumn_change_counts_the_repeated_hour_once_per_fire(self):
        """the wall clock repeats hour 02 on 2026-10-25; whatever Beat
        decides for that day, it decides it for both schedules - the
        suggestion set is only answered over the identical walk"""
        at = datetime(2026, 10, 18, 12, 0, tzinfo=UTC)
        window_start = datetime(2026, 10, 19, 0, 0, tzinfo=BERLIN)
        buckets = 744
        snap = snapshot(
            start=window_start, end=window_start + timedelta(minutes=buckets),
            bucket_seconds=60,
            histogram=self.spike_histogram(window_start, buckets, (0, 30)))

        answer = self.engine('*/30 * * * *', at, snap, tz='Europe/Berlin')

        self.assertTrue(answer.suggestions, answer.reason)
        original, _ = self.window_of(
            '*/30 * * * *', window_start - timedelta(microseconds=1),
            window_start + timedelta(days=7) - timedelta(microseconds=1),
            tz='Europe/Berlin')
        for suggestion in answer.suggestions:
            self.assertEqual(len(original), suggestion.firing_count)

    def test_a_weekday_pattern_is_suggested_with_its_equal_count(self):
        at = datetime(2026, 11, 15, 14, 23, tzinfo=UTC)  # a Sunday
        window_start = datetime(2026, 11, 16, 0, 0, tzinfo=UTC)  # Monday
        buckets = 744
        histogram = [0.0] * buckets
        histogram[8 * 60] = 10.0  # the Monday 08:00 firing is loaded
        snap = snapshot(start=window_start,
                        end=window_start + timedelta(minutes=buckets),
                        bucket_seconds=60, histogram=histogram)

        answer = self.engine('0 8 * * 1', at, snap)

        self.assertTrue(answer.suggestions, answer.reason)
        for suggestion in answer.suggestions:
            self.assertEqual(1, suggestion.firing_count)
            # the whole day match carries over: only the minute moved
            self.assertTrue(suggestion.crontab.endswith(' 8 * * 1'),
                            suggestion.crontab)

    def test_a_leap_day_pattern_gets_its_long_horizon_and_equal_count(self):
        """nothing fires in the 7 days, so the documented longer horizon
        decides: both fire exactly once - and equal counts over the same
        day bucket answer no improvement, which is the honest refusal"""
        at = datetime(2026, 11, 15, 14, 23, tzinfo=UTC)
        window_start = datetime(2026, 11, 16, 0, 0, tzinfo=UTC)
        buckets = 1500
        histogram = [0.0] * buckets
        snap = snapshot(start=window_start,
                        end=window_start + timedelta(days=buckets),
                        bucket_seconds=86_400, histogram=histogram)

        answer = self.engine('30 0 29 2 *', at, snap)

        # the cadence WAS verified (otherwise this would refuse
        # cadence_not_verifiable): only the load comparison stayed neutral
        self.assertEqual((), answer.suggestions)
        self.assertEqual(SuggestionGapEnum.NO_MEASURED_IMPROVEMENT.value,
                         answer.reason_code)
        self.assertEqual(1461, answer.horizon_days)

    def test_a_month_end_pattern_is_counted_over_the_long_horizon(self):
        at = datetime(2026, 11, 15, 14, 23, tzinfo=UTC)
        window_start = datetime(2026, 11, 16, 0, 0, tzinfo=UTC)
        histogram = [1.0] * 1500  # every day bucket equally loaded
        snap = snapshot(start=window_start,
                        end=window_start + timedelta(days=1500),
                        bucket_seconds=86_400, histogram=histogram)

        answer = self.engine('0 0 31 * *', at, snap)

        self.assertEqual((), answer.suggestions)
        self.assertEqual(SuggestionGapEnum.NO_MEASURED_IMPROVEMENT.value,
                         answer.reason_code)

    def test_a_start_time_after_the_window_ends_the_schedule_for_the_check(self):
        at = datetime(2026, 11, 15, 14, 23, tzinfo=UTC)
        window_start = datetime(2026, 11, 16, 0, 0, tzinfo=UTC)
        snap = snapshot(start=window_start,
                        end=window_start + timedelta(minutes=744),
                        bucket_seconds=60,
                        histogram=self.spike_histogram(
                            window_start, 744, (0, 30)))

        answer = self.engine('*/30 * * * *', at, snap,
                             start_time=at + timedelta(days=10))

        self.assertEqual((), answer.suggestions)
        self.assertEqual(SuggestionGapEnum.SCHEDULE_ENDED.value,
                         answer.reason_code)

    def test_start_time_inside_the_window_bounds_the_equal_count(self):
        at = datetime(2026, 11, 15, 14, 23, tzinfo=UTC)
        window_start = datetime(2026, 11, 16, 0, 0, tzinfo=UTC)
        buckets = 10_080
        snap = snapshot(
            start=window_start, end=window_start + timedelta(days=7),
            bucket_seconds=60,
            histogram=self.spike_histogram(window_start, buckets, (0, 30)))

        answer = self.engine('*/30 * * * *', at, snap,
                             start_time=datetime(2026, 11, 18, 0, 7,
                                                 tzinfo=UTC))

        self.assertTrue(answer.suggestions, answer.reason)
        # Nov 18 from 00:30 on plus the four whole days to Nov 22
        for suggestion in answer.suggestions:
            self.assertEqual(47 + 4 * 48, suggestion.firing_count)

    def test_a_start_time_on_the_firing_instant_refuses_rather_than_shifts(self):
        """a shift cannot keep a count the answered field lost at the bound:
        the original fires 239 times from Nov 18 00:00 (that instant is
        strictly outside the window), every alternative 240 - so no
        cadence-preserving alternative exists and the answer says so"""
        at = datetime(2026, 11, 15, 14, 23, tzinfo=UTC)
        window_start = datetime(2026, 11, 16, 0, 0, tzinfo=UTC)
        buckets = 10_080
        snap = snapshot(
            start=window_start, end=window_start + timedelta(days=7),
            bucket_seconds=60,
            histogram=self.spike_histogram(window_start, buckets, (0, 30)))

        answer = self.engine('*/30 * * * *', at, snap,
                             start_time=datetime(2026, 11, 18, 0, 0,
                                                 tzinfo=UTC))

        self.assertEqual((), answer.suggestions)
        self.assertEqual(SuggestionGapEnum.CADENCE_UNVERIFIABLE.value,
                         answer.reason_code)

    def test_an_expiry_before_the_window_is_answered_as_ended(self):
        at = datetime(2026, 11, 15, 14, 23, tzinfo=UTC)
        snap = snapshot(start=at, end=at + timedelta(days=8),
                        bucket_seconds=60, histogram=[1.0] * 100)

        answer = self.engine('*/30 * * * *', at, snap,
                             expires=datetime(2026, 11, 15, 20, 0,
                                              tzinfo=UTC))

        self.assertEqual((), answer.suggestions)
        self.assertEqual(SuggestionGapEnum.SCHEDULE_ENDED.value,
                         answer.reason_code)

    # --- AC 4: no verified capacity, no suggestion ------------------------

    def test_an_unavailable_snapshot_refuses_without_naming_a_minute(self):
        at = datetime(2026, 11, 15, 14, 23, tzinfo=UTC)
        answer = self.engine(
            '*/30 * * * *', at,
            snapshot(start=at, end=at, bucket_seconds=60, histogram=[],
                     available=False, reason='a capacity snapshot is being '
                                             'built'))

        self.assertEqual((), answer.suggestions)
        self.assertEqual(SuggestionGapEnum.CAPACITY_UNVERIFIED.value,
                         answer.reason_code)
        self.assertIn('being built', answer.reason)

    def test_an_unknown_topology_refuses(self):
        at = datetime(2026, 11, 15, 14, 23, tzinfo=UTC)
        window_start = datetime(2026, 11, 16, 0, 0, tzinfo=UTC)
        snap = snapshot(start=window_start,
                        end=window_start + timedelta(minutes=744),
                        bucket_seconds=60, confidence='unknown',
                        histogram=self.spike_histogram(
                            window_start, 744, (0, 30)))

        answer = self.engine('*/30 * * * *', at, snap)

        self.assertEqual((), answer.suggestions)
        self.assertEqual(SuggestionGapEnum.CAPACITY_UNVERIFIED.value,
                         answer.reason_code)

    def test_a_task_count_histogram_alone_ranks_nothing(self):
        """318 firings at minute 0 are not a capacity statement: without a
        comparable rho the engine refuses instead of ranking the counts"""
        at = datetime(2026, 11, 15, 14, 23, tzinfo=UTC)
        window_start = datetime(2026, 11, 16, 0, 0, tzinfo=UTC)
        buckets = 744
        snap = snapshot(
            start=window_start, end=window_start + timedelta(minutes=buckets),
            bucket_seconds=60, rho=None,  # cost/topology not comparable
            occurrences=[318] * buckets,
            histogram=self.spike_histogram(window_start, buckets, (0, 30)))

        answer = self.engine('*/30 * * * *', at, snap)

        self.assertEqual((), answer.suggestions)
        self.assertEqual(SuggestionGapEnum.CAPACITY_UNVERIFIED.value,
                         answer.reason_code)
        self.assertIn('rho', answer.reason)

    def test_partially_costed_demand_refuses(self):
        at = datetime(2026, 11, 15, 14, 23, tzinfo=UTC)
        window_start = datetime(2026, 11, 16, 0, 0, tzinfo=UTC)
        snap = snapshot(start=window_start,
                        end=window_start + timedelta(minutes=744),
                        bucket_seconds=60, coverage=0.9,
                        histogram=self.spike_histogram(
                            window_start, 744, (0, 30)))

        answer = self.engine('*/30 * * * *', at, snap)

        self.assertEqual((), answer.suggestions)
        self.assertEqual(SuggestionGapEnum.CAPACITY_UNVERIFIED.value,
                         answer.reason_code)

    def test_a_degraded_queue_refuses(self):
        at = datetime(2026, 11, 15, 14, 23, tzinfo=UTC)
        window_start = datetime(2026, 11, 16, 0, 0, tzinfo=UTC)
        snap = snapshot(start=window_start,
                        end=window_start + timedelta(minutes=744),
                        bucket_seconds=60, status='degraded',
                        histogram=self.spike_histogram(
                            window_start, 744, (0, 30)))

        answer = self.engine('*/30 * * * *', at, snap)

        self.assertEqual((), answer.suggestions)
        self.assertEqual(SuggestionGapEnum.CAPACITY_UNVERIFIED.value,
                         answer.reason_code)
        self.assertIn('degraded', answer.reason)

    def test_a_queue_the_snapshot_does_not_answer_refuses_by_name(self):
        """an unobserved queue is no verified capacity, even when every
        other queue of the deployment is measured"""
        at = datetime(2026, 11, 15, 14, 23, tzinfo=UTC)
        window_start = datetime(2026, 11, 16, 0, 0, tzinfo=UTC)
        snap = snapshot(queue='a-different-queue', start=window_start,
                        end=window_start + timedelta(minutes=744),
                        bucket_seconds=60,
                        histogram=self.spike_histogram(
                            window_start, 744, (0, 30)))

        answer = self.engine('*/30 * * * *', at, snap)

        self.assertEqual((), answer.suggestions)
        self.assertEqual(SuggestionGapEnum.CAPACITY_UNVERIFIED.value,
                         answer.reason_code)
        self.assertIn('monitoring', answer.reason)

    def test_a_minute_field_without_shift_space_refuses(self):
        at = datetime(2026, 11, 15, 14, 23, tzinfo=UTC)
        window_start = datetime(2026, 11, 16, 0, 0, tzinfo=UTC)
        snap = snapshot(start=window_start,
                        end=window_start + timedelta(days=7),
                        bucket_seconds=3600, histogram=[10.0] * 168)

        answer = self.engine('* * * * *', at, snap)

        self.assertEqual((), answer.suggestions)
        self.assertEqual(SuggestionGapEnum.CADENCE_NO_SPACE.value,
                         answer.reason_code)

    def test_a_hourly_histogram_says_nothing_about_a_minute_shift(self):
        """the honest reading of coarse evidence: equal per-hour occupancy
        for original and alternative answers no suggestion - the engine
        never claims a "free minute" the data cannot support"""
        at = datetime(2026, 11, 15, 14, 23, tzinfo=UTC)
        window_start = datetime(2026, 11, 16, 0, 0, tzinfo=UTC)
        snap = snapshot(start=window_start,
                        end=window_start + timedelta(days=7),
                        bucket_seconds=3600, histogram=[10.0] * 168)

        answer = self.engine('*/30 * * * *', at, snap)

        self.assertEqual((), answer.suggestions)
        self.assertEqual(SuggestionGapEnum.NO_MEASURED_IMPROVEMENT.value,
                         answer.reason_code)

    @override_settings(SCHEDULING_SUGGESTIONS_MAX_OCCURRENCES=10)
    def test_a_walk_over_the_budget_stays_a_refusal_never_a_guess(self):
        at = datetime(2026, 11, 15, 14, 23, tzinfo=UTC)
        window_start = datetime(2026, 11, 16, 0, 0, tzinfo=UTC)
        snap = snapshot(start=window_start,
                        end=window_start + timedelta(days=7),
                        bucket_seconds=60,
                        histogram=self.spike_histogram(
                            window_start, 744, (0, 30)))

        answer = self.engine('*/30 * * * *', at, snap)

        self.assertEqual((), answer.suggestions)
        self.assertEqual(SuggestionGapEnum.CADENCE_UNVERIFIABLE.value,
                         answer.reason_code)

    def test_the_ranks_prefer_the_biggest_measured_improvement(self):
        at = datetime(2026, 11, 15, 14, 23, tzinfo=UTC)
        window_start = datetime(2026, 11, 16, 0, 0, tzinfo=UTC)
        buckets = 744
        # minutes 7 and 37 of every hour are free, 11 and 41 are light, 13
        # and 43 are half loaded - the three alternatives rank by exactly
        # that, and a shift onto the still loaded minutes is no suggestion
        light = {7: 0.0, 37: 0.0, 11: 4.0, 41: 4.0, 13: 8.0, 43: 8.0}
        histogram = [light.get(index % 60, 10.0) for index in range(buckets)]
        snap = snapshot(start=window_start,
                        end=window_start + timedelta(minutes=buckets),
                        bucket_seconds=60, histogram=histogram)

        answer = self.engine('*/30 * * * *', at, snap)

        self.assertEqual(
            ['7,37 * * * *', '11,41 * * * *', '13,43 * * * *'],
            [s.crontab for s in answer.suggestions])
        seconds = [s.expected_worker_seconds for s in answer.suggestions]
        self.assertEqual(seconds, sorted(seconds))
        self.assertEqual(0.0, seconds[0])
        for suggestion in answer.suggestions:
            self.assertLess(suggestion.expected_worker_seconds,
                            suggestion.original_worker_seconds)
        self.assertLessEqual(len(answer.suggestions), 3)


class CadenceSuggestionDatabaseTest(TestCase):
    """The boundedness promise: 43k settings are not a candidate's cost."""

    def test_the_candidate_search_touches_no_database_row(self):
        from django_celery_beat.models import CrontabSchedule, PeriodicTask
        tz = ZoneInfo('UTC')
        crontab = CrontabSchedule.objects.create(
            minute='0', hour='*', day_of_week='*', day_of_month='*',
            month_of_year='*', timezone=tz)
        for index in range(50):
            PeriodicTask.objects.create(
                name=f'schedule-{index}', task='registry.tasks.noop',
                crontab=crontab, queue='other-queue')

        at = datetime(2026, 11, 15, 14, 23, tzinfo=UTC)
        window_start = datetime(2026, 11, 16, 0, 0, tzinfo=UTC)
        snap = snapshot(
            start=window_start, end=window_start + timedelta(minutes=744),
            bucket_seconds=60,
            histogram=[(10.0 if index % 60 in (0, 30) else 0.0)
                       for index in range(744)])
        with CaptureQueriesContext(connection) as queries:
            answer = cadence_suggestions(
                None, proposal('*/30 * * * *'), estimate_with(),
                WebMapServiceMonitoringSetting(), at=at, snapshot=snap)

        self.assertTrue(answer.suggestions)
        # the snapshot is the reusable one, the candidates cost no query
        # and no per-candidate scan - not one SELECT too many
        self.assertEqual([], [q for q in queries.captured_queries
                              if 'periodicperiodictask'
                              in q['sql'].lower()])


class SuggestionAnswerShapeTest(SimpleTestCase):
    """What a suggestion may and may not contain (redaction, evidence)."""

    def test_a_suggestion_names_no_service_and_carries_its_evidence(self):
        at = datetime(2026, 11, 15, 14, 23, tzinfo=UTC)
        window_start = datetime(2026, 11, 16, 0, 0, tzinfo=UTC)
        snap = snapshot(
            start=window_start, end=window_start + timedelta(minutes=744),
            bucket_seconds=60,
            histogram=[(10.0 if index % 60 in (0, 30) else 0.0)
                       for index in range(744)])

        answer = cadence_suggestions(
            None, proposal('*/30 * * * *'), estimate_with(),
            WebMapServiceMonitoringSetting(), at=at, snapshot=snap)

        self.assertTrue(answer.suggestions)
        from dataclasses import asdict
        for suggestion in answer.suggestions:
            fields = asdict(suggestion)
            self.assertEqual({
                'crontab', 'timezone', 'horizon_days', 'horizon_start',
                'horizon_end', 'firing_count', 'queue',
                'original_worker_seconds', 'expected_worker_seconds',
                'sample_count', 'cost_coverage', 'snapshot_at', 'reason',
            }, set(fields))
            # redaction: a suggestion never names a service, a setting or
            # any neighbouring schedule - queue and window numbers only
            text = json.dumps(
                {k: str(v) for k, v in fields.items()})
            self.assertNotIn(WMS_ONE, text)
            self.assertNotIn('WebMapService', text)


class SuggestionPreviewEndpointTest(SchedulePreviewTestCase):
    """The preview endpoint of #1327 answers the alternatives of #1328.

    The capacity evidence is answered by the materialized snapshot of #1326;
    these tests give the endpoint one to read - and one that says there is
    nothing verified to read - so the answered contract of both directions
    is the one a schedule screen actually receives.
    """

    def evidence(self, queue='monitoring', loaded=(0, 30), **overrides):
        """A snapshot over the whole UTC days the preview evaluates from.

        The window starts at the next midnight exactly like the engine's own
        walk; only `loaded` minutes of each hour carry worker-seconds.
        """
        start = datetime.combine(
            now().astimezone(UTC).date() + timedelta(days=1), time.min,
            tzinfo=UTC)
        buckets = 10_080
        histogram = [(10.0 if index % 60 in loaded else 0.0)
                     for index in range(buckets)]
        defaults = dict(queue=queue, start=start,
                        end=start + timedelta(minutes=buckets),
                        bucket_seconds=60, histogram=histogram)
        defaults.update(overrides)
        return snapshot(**defaults)

    def test_the_preview_answers_entire_alternatives_with_their_evidence(self):
        with mock.patch(
                'registry.querys.schedule_suggestions.get_capacity_snapshot',
                return_value=self.evidence()) as reader:
            response, attributes = self.ask(
                self.draft(scheduling='*/30 * * * *'), self.manager)

        self.assertEqual(response.status_code, 200, response.content)
        reader.assert_called_once()
        suggestions = attributes['suggestions']
        self.assertTrue(suggestions)
        for suggestion in suggestions:
            # the whole schedule is answered, not the shifted minute
            self.assertEqual(5, len(suggestion['crontab'].split()))
            self.assertTrue(suggestion['crontab'].endswith(' * * * *'))
            self.assertEqual(suggestion['timezone'], 'UTC')
            self.assertEqual(7, suggestion['horizonDays'])
            self.assertEqual(336, suggestion['firingCount'])
            self.assertEqual(25, suggestion['sampleCount'])
            self.assertEqual(1.0, suggestion['costCoverage'])
            self.assertLess(suggestion['expectedWorkerSeconds'],
                            suggestion['originalWorkerSeconds'])
            self.assertTrue(suggestion['reason'])
            # a suggestion is about the queue, never about a neighbour
            self.assertNotIn('serviceId', suggestion)
            self.assertNotIn('service_id', suggestion)
        self.assertIsNone(attributes['suggestionsReason'])
        self.assertIsNone(attributes['suggestionsReasonCode'])
        self.assertEqual(7, attributes['suggestionsHorizonDays'])
        # the #1327 contract of the same answer is untouched
        self.assertEqual(attributes['scheduling'], '*/30 * * * * UTC')
        self.assertEqual(len(attributes['nextOccurrences']), 3)

    def test_an_unverified_snapshot_refuses_without_losing_the_preview(self):
        """the answer keeps informing, it only stops suggesting"""
        with mock.patch(
                'registry.querys.schedule_suggestions.get_capacity_snapshot',
                return_value=snapshot(
                    start=now(), end=now(), bucket_seconds=60, histogram=[],
                    available=False,
                    reason='no worker of this deployment was observed')):
            response, attributes = self.ask(
                self.draft(scheduling='*/30 * * * *'), self.manager)

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual([], attributes['suggestions'])
        self.assertEqual(SuggestionGapEnum.CAPACITY_UNVERIFIED.value,
                         attributes['suggestionsReasonCode'])
        self.assertIn('observed', attributes['suggestionsReason'])
        self.assertEqual(attributes['scheduling'], '*/30 * * * * UTC')
        self.assertTrue(attributes['capacityReason'])

    def test_a_disabled_schedule_refuses_without_reading_the_snapshot(self):
        """no cadence to preserve - the capacity question is never asked"""
        setting = self.monitoring_setting(scheduling='0 8 * * *',
                                          enabled=False)
        assign_perm('registry.change_webmapservicemonitoringsetting',
                    self.manager, setting)
        with mock.patch(
                'registry.querys.schedule_suggestions.get_capacity_snapshot'
        ) as reader:
            response, attributes = self.ask(
                {'operation': 'monitoring', 'service_kind': 'WebMapService',
                 'service_id': str(self.wms.pk), 'setting_id': setting.pk},
                self.manager)

        self.assertEqual(response.status_code, 200, response.content)
        reader.assert_not_called()
        self.assertEqual([], attributes['suggestions'])
        self.assertEqual(SuggestionGapEnum.NOT_PERIODIC.value,
                         attributes['suggestionsReasonCode'])

    def test_a_harvesting_draft_is_answered_through_its_family_queue(self):
        """the harvesting family decides its queue inside its own `__init__`,
        and a draft of it must be suggestable without a row of its own - and
        without the write that initialisation would otherwise do"""
        with mock.patch(
                'registry.querys.schedule_suggestions.get_capacity_snapshot',
                return_value=self.evidence(queue='default')):
            with CaptureQueriesContext(connection) as queries:
                response, attributes = self.ask({
                    'operation': 'harvest',
                    'service_kind': 'CatalogueService',
                    'service_id': str(self.csw.pk),
                    'scheduling': '0 12 * * 1-5',
                    'timezone': 'UTC',
                    'enabled': True}, self.admin)

        self.assertEqual(response.status_code, 200, response.content)
        suggestions = attributes['suggestions']
        self.assertTrue(suggestions, attributes['suggestionsReason'])
        for suggestion in suggestions:
            self.assertEqual('default', suggestion['queue'])
            self.assertEqual(5, suggestion['firingCount'])
            self.assertTrue(suggestion['crontab'].endswith(' 12 * * 1-5'),
                            suggestion['crontab'])
        writing = [q['sql'] for q in queries.captured_queries
                   if q['sql'].lstrip().upper().startswith(
                       ('INSERT', 'UPDATE', 'DELETE'))]
        self.assertEqual(writing, [])

    def test_a_refused_caller_is_answered_no_suggestion_data(self):
        """the queue occupancy behind a suggestion is not public information"""
        nobody = get_user_model().objects.create_user(
            username='preview-no-suggest')
        response, _ = self.ask(self.draft(scheduling='*/30 * * * *'), nobody)
        self.assertEqual(response.status_code, 403, response.content)
        self.assertNotIn(b'suggestions', response.content)
