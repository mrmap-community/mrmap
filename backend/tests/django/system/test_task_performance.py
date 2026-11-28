"""Continuous slow-task detection of #1390: the acceptance criteria.

The detector reads the attempt samples #1330 writes and decides four separate
conditions per task class. What these tests pin down is the list of cases the
issue names, because every one of them is a case a naive elapsed-time check
gets wrong:

*   a 4 h queue wait in front of a 2 s execution is NOT a 4 h slow task, and a
    4 h active execution IS detectable while it is still running;
*   a p50/p95 shift is a regression, an isolated spike is not, a normal heavy
    tail is not, and a small sample answers ``insufficient`` with no number
    attached;
*   long-running detection survives a delayed inspection, an unreachable
    worker, a retry redelivery, a worker death and the completion race;
*   incidents deduplicate, resolve on recovery and stay permission-filtered
    through #1319's one rule;
*   the fire is bounded in statements and in writes, and an outage of the
    collector costs telemetry, never an execution.

The broker inspection is patched on ``celery.app.control.Control.inspect``
exactly as the watchdog tests of #1320 patch it - ``inspect`` is a
cached_property, so only a class patch reaches it.
"""
import uuid
from datetime import timedelta
from unittest.mock import patch

from django.contrib.contenttypes.models import ContentType
from django_celery_beat.models import PeriodicTask
from django.test import TestCase, override_settings
from django.utils import timezone

from MrMap.celery import app
from notify.enums import (IncidentSeverityEnum, IncidentSourceEnum,
                          IncidentStatusEnum, ProcessStatusEnum)
from notify.models import BackgroundProcess, OperationalIncident
from registry.models.service import CatalogueService
from system.apps import (TASK_PERFORMANCE_DETECTION_TASK_NAME,
                         create_task_performance_detection_task)
from system.models import AttemptQuality, CeleryTaskAttempt
from system.task_performance import (CODE_COVERAGE_DISABLED,
                                     CODE_COVERAGE_STALE,
                                     CODE_COVERAGE_STAMP, CODE_LONG_RUNNING,
                                     CODE_COMPLETED_SLOW, CODE_REGRESSION,
                                     class_code, evaluate_long_running,
                                     evaluate_task_performance,
                                     judge_completed_slow, judge_long_running,
                                     judge_regression)

# the inspection is patched on the class, like #1320: `Control.inspect` is a
# cached_property, so an instance-path patch never reaches it
INSPECT = "celery.app.control.Control.inspect"

CSW_PK = "9cc4889d-0cd4-4c3b-8975-58de6d30db41"

TASK = "registry.tasks.harvest.fetch_md_metadata"
SLOW_TASK = "registry.tasks.harvest.run_harvesting"

#: the switch of the detector plus budgets small enough for a fixture to
#: cross them deterministically
DETECT = override_settings(
    TASK_PERFORMANCE_ENABLED=True,
    TASK_PERFORMANCE_MIN_SAMPLES=5,
    TASK_PERFORMANCE_DEFAULT_BUDGET_SECONDS=10,
    TASK_PERFORMANCE_DEFAULT_LONG_SECONDS=30,
    TASK_PERFORMANCE_LONG_MIN_ACTIVE_SECONDS=1,
    TASK_PERFORMANCE_LONG_GRACE_SECONDS=300,
    TASK_PERFORMANCE_REGRESSION_FACTOR=2.0,
    TASK_PERFORMANCE_SPIKE_SHARE=0.10,
    TASK_PERFORMANCE_REGRESSION_MIN_BASELINE_SECONDS=1.0,
    TASK_PERFORMANCE_COVERAGE_MIN_STAMPED=0.5,
    CAPACITY_TELEMETRY_ENABLED=True,
    CAPACITY_TELEMETRY_ABANDON_GRACE_HOURS=48)


def slow_code(task_name=TASK, queue=""):
    return class_code(CODE_COMPLETED_SLOW, task_name, queue)


def regression_code(task_name=TASK, queue=""):
    return class_code(CODE_REGRESSION, task_name, queue)


def long_code(task_name=TASK, queue=""):
    return class_code(CODE_LONG_RUNNING, task_name, queue)


def seed(task_name=TASK, queue="", outcome="success", active=1.0, wait=0.0,
         started_ago=0, task_id=None, attempt_no=0, worker="celery@w1",
         quality=None):
    """One attempt row as the collector of #1330 would have written it."""
    started = timezone.now() - timedelta(seconds=started_ago)
    terminal = outcome != ""
    return CeleryTaskAttempt.objects.create(
        task_id=task_id or str(uuid.uuid4()),
        attempt_no=attempt_no,
        task_name=task_name,
        queue=queue,
        worker=worker,
        published_at=started - timedelta(seconds=wait)
        if (terminal and wait is not None) else None,
        started_at=started,
        finished_at=started + timedelta(seconds=active) if terminal else None,
        active_seconds=active if terminal else None,
        wait_seconds=float(wait) if (terminal and wait is not None) else None,
        outcome=outcome,
        quality=quality or [],
    )


def seed_class(count, active, task_name=TASK, queue="", started_every=60,
               started_ago_offset=0, **kwargs):
    """``count`` terminal attempts of one class, spaced inside a window."""
    return [seed(task_name=task_name, queue=queue, active=active,
                 started_ago=index * started_every + 5 + started_ago_offset,
                 **kwargs)
            for index in range(count)]


def broker(inspect, active=None, conf=None, dark=False):
    """The answers one fire reads from the broker (see #1320's helper).

    ``dark`` is the honest case of a broker which reached no worker at all;
    otherwise every view answers its empty shape unless named, and ``conf``
    defaults to the one answering worker - the normal state nothing may be
    claimed against. A previously cached inspection is dropped first, because
    ``Control.inspect`` is a cached_property.
    """
    app.control.__dict__.pop("inspect", None)
    views = inspect.return_value
    if dark:
        for name in ("active", "conf"):
            getattr(views, name).return_value = None
        return
    answers = {
        "active": active if active is not None else {},
        "conf": conf if conf is not None else {"celery@w1": {}},
    }
    for name, value in answers.items():
        getattr(views, name).return_value = value


def active_entry(task_id, worker="celery@w1"):
    """One inspected worker entry which reports the attempt as its own."""
    return {worker: [{"id": str(task_id), "request": {"id": str(task_id)}}]}


class DetectorTestMixin:
    """The incident-side reading shared by the fire tests."""

    def active(self, code=None):
        query = OperationalIncident.objects.filter(
            status=IncidentStatusEnum.ACTIVE.value)
        return query.filter(code=code) if code else query


class CompletedSlowTests(DetectorTestMixin, TestCase):
    """The queue/execution split of #1390's first acceptance criterion."""

    fixtures = ["test_users.json", "test_keywords.json", "test_crs.json",
                "test_wms.json", "test_csw.json"]

    @DETECT
    def test_a_four_hour_wait_in_front_of_two_seconds_is_not_slow(self):
        # the acceptance example verbatim: 4 h of broker waiting, 2 s of
        # execution - the wait is a capacity finding (#1324), never a slow task
        seed_class(6, active=2.0, wait=4 * 3600)
        with patch(INSPECT) as inspect:
            broker(inspect)
            summary = evaluate_task_performance()
        self.assertEqual(summary["published"], [])
        self.assertEqual(self.active().count(), 0)

    @DETECT
    def test_a_finished_attempt_over_its_budget_is_one_incident(self):
        seed_class(5, active=12.0)
        with patch(INSPECT) as inspect:
            broker(inspect)
            summary = evaluate_task_performance()
        self.assertEqual(len(summary["published"]), 1)
        incident = self.active(slow_code()).get()
        self.assertEqual(incident.source, IncidentSourceEnum.SYSTEM.value)
        self.assertEqual(incident.scope, "system")
        self.assertEqual(incident.severity,
                         IncidentSeverityEnum.WARNING.value)
        self.assertEqual(incident.details["task_name"], TASK)
        self.assertAlmostEqual(
            incident.details["observed_max_active_seconds"], 12.0)
        self.assertEqual(incident.details["budget_seconds"], 10)
        # the queue-wait numbers travel with the verdict, labelled apart
        self.assertIsNotNone(incident.details["max_wait_seconds"])

    @DETECT
    def test_a_recurring_slow_class_stays_one_incident_with_a_count(self):
        seed_class(5, active=12.0)
        with patch(INSPECT) as inspect:
            broker(inspect)
            evaluate_task_performance()
            evaluate_task_performance()
        incidents = self.active(slow_code())
        self.assertEqual(incidents.count(), 1)
        self.assertEqual(incidents.get().occurrence_count, 2)

    @DETECT
    def test_recovery_resolves_the_standing_slow_incident(self):
        slow = seed_class(5, active=12.0)
        with patch(INSPECT) as inspect:
            broker(inspect)
            evaluate_task_performance()
        self.assertEqual(self.active(slow_code()).count(), 1)
        # the next window answers inside the budget: recovery, proven by the
        # same evidence which raised the verdict
        for row in slow:
            CeleryTaskAttempt.objects.filter(pk=row.pk).update(
                active_seconds=2.0)
        with patch(INSPECT) as inspect:
            broker(inspect)
            summary = evaluate_task_performance()
        self.assertEqual(summary["resolved"], 1)
        self.assertEqual(self.active(slow_code()).count(), 0)
        self.assertEqual(
            OperationalIncident.objects.get(code=slow_code()).status,
            IncidentStatusEnum.RESOLVED.value)

    @DETECT
    def test_two_slow_classes_are_two_incidents(self):
        # the class is part of the code, so one recovery never resolves the
        # other class's standing verdict
        seed_class(5, active=12.0, task_name=TASK)
        seed_class(5, active=12.0, task_name=SLOW_TASK)
        with patch(INSPECT) as inspect:
            broker(inspect)
            summary = evaluate_task_performance()
        self.assertEqual(len(summary["published"]), 2)
        self.assertEqual(self.active(slow_code()).count(), 1)
        self.assertEqual(
            self.active(slow_code(SLOW_TASK)).count(), 1)

    @DETECT
    def test_a_class_silenced_by_its_policy_reports_nothing(self):
        seed_class(5, active=12.0, task_name=SLOW_TASK)
        with override_settings(TASK_PERFORMANCE_POLICY={
                SLOW_TASK: {"disabled": True}}):
            with patch(INSPECT) as inspect:
                broker(inspect)
                summary = evaluate_task_performance()
        self.assertEqual(summary["published"], [])
        self.assertEqual(self.active().count(), 0)

    @DETECT
    def test_a_congested_route_is_named_as_the_suspected_latency(self):
        # a slow class whose queue waited more than its baseline too carries
        # the suspicion that the route in front of it is the reason - labelled
        # as #1324's capacity question, never as the slow task itself
        seed_class(6, active=2.0, wait=1.0, started_every=3600 * 3,
                   started_ago_offset=3600 * 25)
        seed_class(6, active=12.0, wait=600.0)
        with patch(INSPECT) as inspect:
            broker(inspect)
            summary = evaluate_task_performance(publish=False)
        slow = next(item for item in summary["verdicts"]
                    if item.get("code") == slow_code())
        self.assertEqual(slow["suspected_external_latency"]["suspected"],
                         "queue_backlog")
        self.assertEqual(slow["suspected_external_latency"]["owner"], "#1324")

    @DETECT
    def test_a_slow_class_with_a_free_route_suspects_nothing(self):
        seed_class(6, active=12.0, wait=1.0, started_every=3600 * 3,
                   started_ago_offset=3600 * 25)
        seed_class(6, active=12.0, wait=1.0)
        with patch(INSPECT) as inspect:
            broker(inspect)
            summary = evaluate_task_performance(publish=False)
        slow = next(item for item in summary["verdicts"]
                    if item.get("code") == slow_code())
        self.assertIsNone(slow["suspected_external_latency"])

    @DETECT
    def test_a_queue_policy_overrides_the_default_budget(self):
        # the class is slow for the global default and fine for its own queue
        seed_class(5, active=12.0, queue="harvest-import")
        with override_settings(TASK_PERFORMANCE_POLICY={
                "queue:harvest-import": {"budget_seconds": 60}}):
            with patch(INSPECT) as inspect:
                broker(inspect)
                summary = evaluate_task_performance()
        self.assertEqual(summary["published"], [])
        self.assertEqual(self.active().count(), 0)

    @DETECT
    def test_a_sparse_class_is_never_judged(self):
        # never alert merely because the sample is thin: no number, no verdict
        seed_class(2, active=12.0)
        with patch(INSPECT) as inspect:
            broker(inspect)
            summary = evaluate_task_performance()
        self.assertEqual(summary["published"], [])
        self.assertEqual(self.active().count(), 0)

    @DETECT
    def test_no_data_at_all_publishes_nothing(self):
        with patch(INSPECT) as inspect:
            broker(inspect)
            summary = evaluate_task_performance()
        self.assertEqual(summary["classes"], 0)
        self.assertEqual(summary["published"], [])
        self.assertEqual(self.active().count(), 0)


class RegressionTests(DetectorTestMixin, TestCase):
    """p95/slot-cost shift vs isolated spike vs heavy tail vs small sample."""

    fixtures = ["test_users.json", "test_keywords.json", "test_crs.json",
                "test_wms.json", "test_csw.json"]

    @DETECT
    def test_a_p95_shift_is_a_regression(self):
        # the baseline window (25..47 h ago) at 2 s, the current window at
        # 8 s: the whole distribution moved and nothing merely spiked
        seed_class(6, active=2.0, started_every=3600 * 3,
                   started_ago_offset=3600 * 25)
        seed_class(6, active=8.0, started_every=3600 * 3)
        with patch(INSPECT) as inspect:
            broker(inspect)
            summary = evaluate_task_performance()
        regression = [item for item in summary["verdicts"]
                      if item.get("code") == regression_code()]
        self.assertEqual(len(regression), 1)
        self.assertEqual(regression[0]["comparison"], "active_p95")
        self.assertGreater(regression[0]["p95_ratio"], 2.0)
        self.assertEqual(self.active(regression_code()).count(), 1)

    @DETECT
    def test_an_isolated_spike_is_a_slow_finding_not_a_regression(self):
        # nine attempts at 2 s and one at 60 s: the p95 of ten samples lands
        # right on the spike and moved far past the factor, yet only 1 of 10
        # exceeded the budget - a spike is called what it is (completed_slow)
        # and never also a regression (#1390)
        seed_class(6, active=2.0, started_every=3600 * 3,
                   started_ago_offset=3600 * 25)
        seed_class(9, active=2.0, started_every=3600 * 2)
        seed(active=60.0, started_ago=30)
        with patch(INSPECT) as inspect:
            broker(inspect)
            summary = evaluate_task_performance()
        codes = [item.get("code") for item in summary["verdicts"]]
        self.assertIn(slow_code(), codes)
        self.assertNotIn(regression_code(), codes)
        self.assertEqual(self.active(regression_code()).count(), 0)
        # and the slow finding says what it is: one sample over the budget
        spike = next(item for item in summary["verdicts"]
                     if item.get("code") == slow_code())
        self.assertEqual(spike["samples_over_budget"], 1)
        self.assertAlmostEqual(spike["exceeded_share"], 0.1)

    @DETECT
    def test_a_normal_heavy_tail_is_no_regression(self):
        # a class which legitimately runs long sometimes is answered by its
        # own class policy - a budget which says how long it may take and a
        # factor which says how much of its own history is normal noise - not
        # by re-baselining it here
        seed_class(6, active=2.0, started_every=3600 * 3,
                   started_ago_offset=3600 * 25)
        seed_class(6, active=8.0, started_every=3600 * 3)
        with override_settings(TASK_PERFORMANCE_POLICY={
                TASK: {"budget_seconds": 20, "regression_factor": 5.0}}):
            with patch(INSPECT) as inspect:
                broker(inspect)
                summary = evaluate_task_performance()
        self.assertEqual(summary["published"], [])
        self.assertEqual(self.active().count(), 0)

    @DETECT
    def test_a_sub_second_baseline_is_no_ratio(self):
        # a sub-second baseline multiplied by a factor is false precision:
        # the comparison answers insufficient and publishes nothing
        seed_class(6, active=0.4, started_every=3600 * 3,
                   started_ago_offset=3600 * 25)
        seed_class(6, active=1.8, started_every=3600 * 3)
        with patch(INSPECT) as inspect:
            broker(inspect)
            summary = evaluate_task_performance()
        self.assertEqual(self.active(regression_code()).count(), 0)
        self.assertEqual(summary["classes"], 1)
        verdicts = [item for item in summary["verdicts"]
                    if item.get("code") == regression_code()]
        self.assertEqual(verdicts, [])

    @DETECT
    def test_a_small_baseline_sample_is_no_regression(self):
        seed_class(2, active=2.0, started_every=3600 * 3,
                   started_ago_offset=3600 * 25)
        seed_class(6, active=9.0, started_every=3600 * 3)
        with patch(INSPECT) as inspect:
            broker(inspect)
            summary = evaluate_task_performance()
        self.assertEqual(self.active(regression_code()).count(), 0)
        self.assertEqual([item for item in summary["verdicts"]
                          if item.get("code") == regression_code()], [])


class LongRunningTests(DetectorTestMixin, TestCase):
    """The currently-active condition and its failure cases."""

    fixtures = ["test_users.json", "test_keywords.json", "test_crs.json",
                "test_wms.json", "test_csw.json"]

    def long_attempt(self, minutes=120, task_id=None, worker="celery@w1"):
        return seed(outcome="", active=None, wait=None,
                    started_ago=minutes * 60, task_id=task_id,
                    worker=worker)

    @DETECT
    def test_a_four_hour_active_execution_is_detectable_now(self):
        # the acceptance example: detectable WHILE it runs, worker confirming
        attempt = self.long_attempt(minutes=240)
        with patch(INSPECT) as inspect:
            broker(inspect, active=active_entry(attempt.task_id))
            summary = evaluate_task_performance()
        self.assertEqual(len(summary["published"]), 1)
        incident = self.active(long_code()).get()
        self.assertEqual(incident.severity, IncidentSeverityEnum.ERROR.value)
        self.assertEqual(incident.details["task_id"], attempt.task_id)
        self.assertEqual(incident.details["confidence"], "high")
        self.assertGreater(incident.details["active_seconds"], 4 * 3600 - 60)

    @DETECT
    def test_an_attempt_below_its_budget_is_not_long_running(self):
        self.long_attempt(minutes=1)
        with patch(INSPECT) as inspect:
            broker(inspect)
            summary = evaluate_task_performance()
        self.assertEqual(summary["published"], [])
        self.assertEqual(self.active().count(), 0)

    @DETECT
    def test_a_queued_message_is_no_execution_at_all(self):
        # queue waiting is not execution: a message which never started has
        # no attempt row, and 4 h of waiting in front of 2 s of work stays a
        # capacity answer, not a long task (#1324)
        seed(outcome="success", active=2.0, wait=4 * 3600, started_ago=60)
        with patch(INSPECT) as inspect:
            broker(inspect)
            summary = evaluate_task_performance()
        self.assertEqual(summary["published"], [])

    @DETECT
    def test_an_unreachable_owner_is_unknown_not_healthy_or_confirmed(self):
        attempt = self.long_attempt(minutes=240, worker="celery@dead")
        with patch(INSPECT) as inspect:
            # another worker answers; the owner of the attempt does not
            broker(inspect, conf={"celery@other": {}})
            summary = evaluate_task_performance()
        self.assertEqual(summary["published"], [])
        self.assertEqual(self.active().count(), 0)
        suspicion = next(item for item in summary["verdicts"]
                         if item.get("code") == long_code())
        self.assertEqual(suspicion["task_id"], attempt.task_id)
        self.assertEqual(suspicion["measured"], "unknown")
        self.assertEqual(suspicion["confidence"], "low")
        self.assertEqual(suspicion["reason"], "worker_unreachable")

    @DETECT
    def test_a_dark_broker_claims_nothing_about_current_activity(self):
        self.long_attempt(minutes=240)
        with patch(INSPECT) as inspect:
            broker(inspect, dark=True)
            summary = evaluate_task_performance()
        self.assertEqual(summary["worker_inspection"], "unknown")
        self.assertIn("worker_inspection", summary["unknown"])
        self.assertEqual(summary["published"], [])
        self.assertEqual(self.active().count(), 0)

    @DETECT
    def test_a_delayed_inspection_still_catches_a_long_attempt_later(self):
        # a fire which reached nothing about the worker publishes nothing;
        # the next fire, with the worker answering, makes it actionable -
        # detection missed nothing, it only stayed unknown meanwhile
        attempt = self.long_attempt(minutes=400)
        with patch(INSPECT) as inspect:
            broker(inspect)
            first = evaluate_task_performance()
            self.assertEqual(first["published"], [])
            broker(inspect, active=active_entry(attempt.task_id))
            summary = evaluate_task_performance()
        self.assertEqual(len(summary["published"]), 1)

    @DETECT
    def test_a_finished_attempt_is_no_long_running_verdict(self):
        # the completion race: the owning worker answered and does not report
        # the attempt - it finished between the row and the inspection
        attempt = self.long_attempt(minutes=240)
        CeleryTaskAttempt.objects.create(
            task_id=attempt.task_id, attempt_no=0, task_name=TASK,
            queue="", worker="celery@w1",
            started_at=attempt.started_at,
            finished_at=timezone.now(), active_seconds=240 * 60,
            # a stamped terminal row: the class' coverage stays intact, so
            # the only verdict this fire could publish is a long-running one
            wait_seconds=1.0, outcome="success")
        with patch(INSPECT) as inspect:
            broker(inspect)
            summary = evaluate_task_performance()
        self.assertEqual(summary["published"], [])
        self.assertEqual(self.active(CODE_LONG_RUNNING).count(), 0)

    @DETECT
    def test_a_worker_death_past_the_grace_is_coverage_not_a_long_task(self):
        # an attempt older than the abandon grace is crash residue: reporting
        # it as still running would name a dead worker a slow task. It is
        # inside the retention of the samples, where the row really does
        # still stand open in the table.
        attempt = self.long_attempt(minutes=60 * 60)
        CeleryTaskAttempt.objects.filter(pk=attempt.pk).update(
            quality=[AttemptQuality.ABANDONED.value])
        with patch(INSPECT) as inspect:
            broker(inspect, active=active_entry(
                attempt.task_id, worker="celery@dead"))
            summary = evaluate_task_performance()
        codes = [item.get("code") for item in summary["verdicts"]]
        self.assertNotIn(long_code(), codes)
        self.assertIn(CODE_COVERAGE_STALE, codes)

    @DETECT
    def test_a_retry_redelivery_is_the_attempt_which_reports_itself(self):
        # celery retries under the same uuid: attempt 0 ended, attempt 1 runs;
        # only the attempt an active worker reports becomes the verdict
        first = seed(outcome="retry", active=5.0, started_ago=4 * 3600)
        second = seed(outcome="", active=None, wait=None,
                      started_ago=3 * 3600, task_id=first.task_id,
                      attempt_no=1)
        with patch(INSPECT) as inspect:
            broker(inspect, active=active_entry(second.task_id))
            summary = evaluate_task_performance()
        self.assertEqual(len(summary["published"]), 1)
        incident = self.active(long_code()).get()
        self.assertEqual(incident.details["attempt_no"], 1)

    @DETECT
    def test_a_standing_long_running_incident_resolves_when_work_stops(self):
        attempt = self.long_attempt(minutes=240)
        with patch(INSPECT) as inspect:
            broker(inspect, active=active_entry(attempt.task_id))
            evaluate_task_performance()
        self.assertEqual(self.active(long_code()).count(), 1)
        # the worker answers and no longer reports it: the attempt completed,
        # died or was redelivered - the evidence of the verdict is gone
        with patch(INSPECT) as inspect:
            broker(inspect)
            summary = evaluate_task_performance()
        self.assertGreaterEqual(summary["resolved"], 1)
        self.assertEqual(self.active(long_code()).count(), 0)

    @DETECT
    def test_a_dark_fire_keeps_a_standing_long_running_incident_standing(self):
        # the observer's blindness is not evidence that the work stopped: a
        # fire which reached no worker neither claims current activity nor
        # resolves it (#1390 - unknown is never conclusively healthy)
        attempt = self.long_attempt(minutes=240)
        with patch(INSPECT) as inspect:
            broker(inspect, active=active_entry(attempt.task_id))
            evaluate_task_performance()
        self.assertEqual(self.active(long_code()).count(), 1)
        with patch(INSPECT) as inspect:
            broker(inspect, dark=True)
            summary = evaluate_task_performance()
        self.assertEqual(summary["worker_inspection"], "unknown")
        self.assertEqual(summary["resolved"], 0)
        self.assertEqual(self.active(long_code()).count(), 1)
        # the next fire which does reach the worker decides, with evidence
        with patch(INSPECT) as inspect:
            broker(inspect)
            summary = evaluate_task_performance()
        self.assertGreaterEqual(summary["resolved"], 1)
        self.assertEqual(self.active(long_code()).count(), 0)

    @DETECT
    def test_an_unreachable_owner_never_resolves_a_long_running_incident(self):
        # partial blindness is still blindness: the fleet answered, only not
        # the worker which owns the attempt, so nothing proves it stopped
        attempt = self.long_attempt(minutes=240, worker="celery@dead")
        with patch(INSPECT) as inspect:
            broker(inspect,
                   active=active_entry(attempt.task_id, worker="celery@dead"),
                   conf={"celery@dead": {}, "celery@w1": {}})
            evaluate_task_performance()
        self.assertEqual(self.active(long_code()).count(), 1)
        with patch(INSPECT) as inspect:
            broker(inspect, conf={"celery@w1": {}})
            summary = evaluate_task_performance()
        self.assertEqual(summary["resolved"], 0)
        self.assertEqual(self.active(long_code()).count(), 1)

    @DETECT
    def test_a_completed_long_running_attempt_resolves_its_incident(self):
        # the completion race's honest end: the collector writes the terminal
        # row BESIDE the open one, and that pair is a finished execution - the
        # same reading the candidate side of this module uses, so the standing
        # error incident of a confirmed long task ends when it completes
        attempt = self.long_attempt(minutes=240)
        with patch(INSPECT) as inspect:
            broker(inspect, active=active_entry(attempt.task_id))
            evaluate_task_performance()
        self.assertEqual(self.active(long_code()).count(), 1)
        CeleryTaskAttempt.objects.create(
            task_id=attempt.task_id, attempt_no=attempt.attempt_no,
            task_name=TASK, started_at=attempt.started_at,
            finished_at=timezone.now(), active_seconds=240 * 60,
            outcome="success")
        with patch(INSPECT) as inspect:
            broker(inspect)
            summary = evaluate_task_performance()
        self.assertGreaterEqual(summary["resolved"], 1)
        self.assertEqual(self.active(long_code()).count(), 0)

    @DETECT
    def test_a_terminal_row_alone_resolves_without_the_open_row(self):
        # retention may have flushed the open row of the same identity
        # already; the terminal twin alone is the completion, too
        attempt = self.long_attempt(minutes=240)
        with patch(INSPECT) as inspect:
            broker(inspect, active=active_entry(attempt.task_id))
            evaluate_task_performance()
        self.assertEqual(self.active(long_code()).count(), 1)
        CeleryTaskAttempt.objects.filter(pk=attempt.pk).update(
            outcome="success", finished_at=timezone.now(), active_seconds=240 * 60)
        with patch(INSPECT) as inspect:
            broker(inspect)
            summary = evaluate_task_performance()
        self.assertGreaterEqual(summary["resolved"], 1)
        self.assertEqual(self.active(long_code()).count(), 0)

    @DETECT
    def test_a_dead_attempt_resolves_on_evidence_and_becomes_coverage(self):
        # the worker death of #1390: past the abandon grace the row is crash
        # residue, which the coverage condition owns - so the long-running
        # incident ends and the coverage one takes its place
        attempt = self.long_attempt(minutes=240, worker="celery@dead")
        with patch(INSPECT) as inspect:
            broker(inspect,
                   active=active_entry(attempt.task_id, worker="celery@dead"),
                   conf={"celery@dead": {}, "celery@w1": {}})
            evaluate_task_performance()
        self.assertEqual(self.active(long_code()).count(), 1)
        CeleryTaskAttempt.objects.filter(pk=attempt.pk).update(
            started_at=timezone.now() - timedelta(seconds=55 * 3600))
        with patch(INSPECT) as inspect:
            broker(inspect, conf={"celery@w1": {}})
            summary = evaluate_task_performance()
        self.assertGreaterEqual(summary["resolved"], 1)
        self.assertEqual(self.active(long_code()).count(), 0)
        self.assertEqual(self.active(CODE_COVERAGE_STALE).count(), 1)

    def test_confirmation_is_matched_per_worker(self):
        # celery retries keep the task uuid: another worker reporting the same
        # id confirms nothing about this attempt (#1390's redelivery case)
        decision = judge_long_running(
            4 * 3600, 3600, True, own_worker_answered=False)
        self.assertEqual(decision["condition"], "long_running")
        self.assertEqual(decision["measured"], "unknown")
        self.assertEqual(decision["confidence"], "low")
        self.assertEqual(decision["reason"], "worker_unreachable")

    def test_only_the_owning_worker_confirmation_is_high_confidence(self):
        decision = judge_long_running(
            4 * 3600, 3600, True, own_worker_answered=True)
        self.assertEqual(decision["condition"], "long_running")
        self.assertEqual(decision["measured"], "measured")
        self.assertEqual(decision["confidence"], "high")
        # a reported attempt the owning worker does not report is the
        # completion race: healthy, with the reason named
        raced = judge_long_running(
            4 * 3600, 3600, False, own_worker_answered=True)
        self.assertEqual(raced["condition"], "healthy")
        self.assertEqual(raced["reason"], "finished_or_died")

    @DETECT
    def test_a_long_running_verdict_names_the_process_resource(self):
        service = CatalogueService.objects.get(pk=CSW_PK)
        process = BackgroundProcess.objects.create(
            process_type="harvesting", phase="records to db",
            description="a harvest whose task runs for hours",
            status=ProcessStatusEnum.RUNNING.value,
            related_resource_type=ContentType.objects.get_for_model(service),
            related_id=service.pk)
        attempt = self.long_attempt(minutes=240)
        process.append_celery_task_ids([attempt.task_id])

        with patch(INSPECT) as inspect:
            broker(inspect, active=active_entry(attempt.task_id))
            evaluate_task_performance()

        incident = self.active(long_code()).get()
        self.assertEqual(incident.scope, "resource")
        self.assertEqual(incident.source, IncidentSourceEnum.HARVESTING.value)
        self.assertEqual(incident.catalogue_service_id, service.pk)
        self.assertEqual(
            incident.details["background_process"], str(process.pk))

    @DETECT
    def test_a_completed_execution_is_never_a_long_running_candidate(self):
        # a finished attempt keeps its open row beside its terminal one
        # (#1330); that pair is a completed execution, not a running task
        open_row = self.long_attempt(minutes=240)
        CeleryTaskAttempt.objects.create(
            task_id=open_row.task_id, attempt_no=0, task_name=TASK,
            started_at=open_row.started_at, finished_at=timezone.now(),
            active_seconds=240 * 60, outcome="success")
        confirmed, suspicions = evaluate_long_running(
            timezone.now(), {"active": {}, "conf": {"celery@w1": {}}})
        self.assertEqual(confirmed, [])
        self.assertEqual(suspicions, [])


class CoverageTests(DetectorTestMixin, TestCase):
    """The fourth condition: what the telemetry cannot see."""

    fixtures = ["test_users.json", "test_keywords.json", "test_crs.json",
                "test_wms.json", "test_csw.json"]

    @DETECT
    def test_unstamped_attempts_are_reported_as_blind_waiting(self):
        # attempts ran, but without a publish stamp their waiting is unknown
        seed_class(6, active=2.0, wait=None)
        with patch(INSPECT) as inspect:
            broker(inspect)
            evaluate_task_performance()
        incident = self.active(CODE_COVERAGE_STAMP).get()
        self.assertEqual(incident.scope, "system")
        self.assertEqual(incident.details["stamped_share"], 0.0)

    @DETECT
    def test_stamp_coverage_at_the_bound_is_silent(self):
        # half of the window stamped is exactly the bound: silence (#1390
        # reports inadequate coverage, not merely imperfect coverage)
        seed_class(3, active=2.0, wait=None)
        seed_class(3, active=2.0, wait=1.0)
        with patch(INSPECT) as inspect:
            broker(inspect)
            evaluate_task_performance()
        self.assertEqual(self.active(CODE_COVERAGE_STAMP).count(), 0)

    @DETECT
    def test_open_attempts_past_the_grace_are_a_coverage_verdict(self):
        old = seed(outcome="", active=None, wait=None,
                   started_ago=55 * 3600)
        CeleryTaskAttempt.objects.filter(pk=old.pk).update(
            quality=[AttemptQuality.ABANDONED.value])
        with patch(INSPECT) as inspect:
            broker(inspect)
            evaluate_task_performance()
        self.assertEqual(self.active(CODE_COVERAGE_STALE).count(), 1)

    @DETECT
    def test_telemetry_switched_off_while_work_stands_open_is_coverage(self):
        BackgroundProcess.objects.create(
            process_type="harvesting", phase="records to db",
            description="work with nobody measuring it",
            status=ProcessStatusEnum.RUNNING.value)
        with override_settings(CAPACITY_TELEMETRY_ENABLED=False):
            with patch(INSPECT) as inspect:
                broker(inspect)
                evaluate_task_performance()
        self.assertEqual(self.active(CODE_COVERAGE_DISABLED).count(), 1)

    @DETECT
    def test_coverage_verdicts_resolve_when_the_reading_is_complete(self):
        old = seed(outcome="", active=None, wait=None,
                   started_ago=55 * 3600)
        CeleryTaskAttempt.objects.filter(pk=old.pk).update(
            quality=[AttemptQuality.ABANDONED.value])
        with patch(INSPECT) as inspect:
            broker(inspect)
            evaluate_task_performance()
        self.assertEqual(self.active(CODE_COVERAGE_STALE).count(), 1)
        CeleryTaskAttempt.objects.filter(pk=old.pk).delete()
        with patch(INSPECT) as inspect:
            broker(inspect)
            summary = evaluate_task_performance()
        self.assertGreaterEqual(summary["resolved"], 1)
        self.assertEqual(self.active(CODE_COVERAGE_STALE).count(), 0)


class OutageAndBudgetTests(DetectorTestMixin, TestCase):
    """Detection must never touch the work it observes (#1390's last AC)."""

    fixtures = ["test_users.json", "test_keywords.json", "test_crs.json",
                "test_wms.json", "test_csw.json"]

    @DETECT
    def test_a_broken_sample_read_costs_nothing_but_the_fire(self):
        with patch("system.task_performance._aggregate_classes") as aggregate:
            aggregate.side_effect = RuntimeError("the database did not answer")
            with patch(INSPECT) as inspect:
                broker(inspect)
                summary = evaluate_task_performance()
        self.assertEqual(summary["published"], [])
        self.assertEqual(summary["resolved"], 0)
        self.assertEqual(summary["unknown"], ["sample_read"])
        self.assertEqual(self.active().count(), 0)

    @DETECT
    def test_one_fire_costs_its_fixed_reads_and_nothing_per_task(self):
        # the windowed aggregate of the current window, the same aggregate of
        # the baseline window (one batched read for all classes, never one per
        # class), the coverage aggregate, the stale-open count, one exceedance
        # count per judged class and the open-attempt read - fixed per fire
        # and per class, independent of the 24 attempts in the window. The
        # reachability condition of #1827 adds exactly two more, both grouped
        # and bounded: the attempt aggregate of the window and one read of the
        # beat rows.
        for index in range(4):
            seed_class(6, active=2.0, task_name=f"task.class.{index}")
        with patch(INSPECT) as inspect:
            broker(inspect)
            with self.assertNumQueries(11):
                evaluate_task_performance(publish=False)

    def test_detection_off_evaluates_nothing(self):
        with override_settings(TASK_PERFORMANCE_ENABLED=False):
            summary = evaluate_task_performance()
        self.assertEqual(summary["status"], "disabled")
        self.assertEqual(self.active().count(), 0)

    @DETECT
    def test_a_mass_slowdown_is_bounded_by_the_verdict_ceiling(self):
        for index in range(4):
            seed_class(5, active=12.0, task_name=f"slow.class.{index}")
        with override_settings(TASK_PERFORMANCE_MAX_VERDICTS_PER_FIRE=2):
            with patch(INSPECT) as inspect:
                broker(inspect)
                summary = evaluate_task_performance()
        self.assertEqual(len(summary["published"]), 2)
        self.assertEqual(
            self.active().filter(
                code__startswith=CODE_COMPLETED_SLOW).count(), 2)


class ResolutionSafetyTests(DetectorTestMixin, TestCase):
    """Only this module's own incidents are ever resolved."""

    fixtures = ["test_users.json", "test_keywords.json", "test_crs.json",
                "test_wms.json", "test_csw.json"]

    @DETECT
    def test_a_foreign_incident_of_another_family_stands(self):
        OperationalIncident.objects.report(
            code="operational_retry_window_expired",
            source=IncidentSourceEnum.SYSTEM.value,
            severity=IncidentSeverityEnum.WARNING.value,
            summary="another watchdog's verdict",
            details={"task_name": TASK, "queue": ""})
        with patch(INSPECT) as inspect:
            broker(inspect)
            summary = evaluate_task_performance()
        self.assertEqual(summary["resolved"], 0)
        self.assertEqual(
            self.active("operational_retry_window_expired").count(), 1)


class PureJudgeTests(TestCase):
    """The decision core without a database: the defined outcomes of #1390."""

    ROW = {"samples": 10, "active_max": 12.0, "active_p50": 2.0,
           "active_p95": 2.5, "slot_seconds": 20.0, "wait_max": 4 * 3600,
           "last_started": None}

    def test_small_sample_answers_insufficient_not_a_number(self):
        verdict = judge_completed_slow(
            dict(self.ROW, samples=2), budget=10, samples_over=2)
        self.assertEqual(verdict["condition"], "insufficient")
        self.assertNotIn("observed_max_active_seconds", verdict)

    def test_stale_class_answers_no_data(self):
        verdict = judge_completed_slow(self.ROW, budget=10, samples_over=9,
                                       stale=True)
        self.assertEqual(verdict["condition"], "no_data")

    def test_regression_needs_both_windows_sampled(self):
        baseline = {"samples": 1, "active_p95": 2.0, "active_p50": 2.0,
                    "slot_seconds": 20.0}
        verdict = judge_regression(
            self.ROW, baseline, factor=2.0, min_baseline=1.0,
            spike_allowance=0.1, samples_over_baseline=0)
        self.assertEqual(verdict["condition"], "insufficient")

    def test_no_comparable_baseline_answers_insufficient(self):
        baseline = {"samples": 10, "active_p95": 0.2, "active_p50": 0.2,
                    "slot_seconds": 0.3}
        verdict = judge_regression(
            dict(self.ROW, active_p95=0.9, slot_seconds=3.0), baseline,
            factor=2.0, min_baseline=1.0, spike_allowance=0.1,
            samples_over_baseline=0)
        self.assertEqual(verdict["condition"], "insufficient")
        self.assertIsNone(verdict["p95_ratio"])

    def test_a_shift_is_a_regression_and_a_spike_is_not(self):
        baseline = {"samples": 10, "active_p95": 2.2, "active_p50": 2.0,
                    "slot_seconds": 22.0}
        # the whole distribution moved: the middle of the window is beyond the
        # factor too, which is what a shift is
        shifted = judge_regression(
            dict(self.ROW, active_p50=4.5, active_p95=5.0), baseline,
            factor=2.0, min_baseline=1.0, spike_allowance=0.1,
            samples_over_baseline=0)
        self.assertEqual(shifted["condition"], "regression")
        # only the tail moved: the middle of the window stayed where it was and
        # one attempt of ten is beyond the class' old p95 - the spike of
        # #1390, which completed_slow already called slow
        spiked = judge_regression(
            dict(self.ROW, active_p95=5.0), baseline, factor=2.0,
            min_baseline=1.0, spike_allowance=0.1, samples_over_baseline=1)
        self.assertEqual(spiked["condition"], "healthy")
        self.assertTrue(spiked["spike_only"])

    def test_slot_cost_regression_without_a_p95_ratio(self):
        # no p95 anywhere means no old range which could have been exceeded,
        # which is exactly what the caller passes (see _evaluate_class): the
        # spike question has no answer here and must not silence the move
        baseline = {"samples": 10, "active_p95": None, "active_p50": None,
                    "slot_seconds": 22.0}
        verdict = judge_regression(
            dict(self.ROW, active_p50=None, active_p95=None,
                 slot_seconds=48.0), baseline, factor=2.0, min_baseline=1.0,
            spike_allowance=0.1)
        self.assertEqual(verdict["condition"], "regression")
        self.assertEqual(verdict["comparison"], "slot_cost")
        self.assertIsNone(verdict["exceeded_share"])

    def test_a_sub_second_slot_cost_is_no_comparison_either(self):
        # the false-precision guard is not a p95-only rule: two windows of ten
        # attempts each, a quarter of a second per attempt, multiplied into a
        # "2.8x slower" - never
        baseline = {"samples": 10, "active_p95": None, "active_p50": None,
                    "slot_seconds": 2.5}
        verdict = judge_regression(
            dict(self.ROW, active_p50=None, active_p95=None,
                 slot_seconds=7.0), baseline, factor=2.0, min_baseline=1.0,
            spike_allowance=0.1, samples_over_baseline=0)
        self.assertEqual(verdict["condition"], "insufficient")

    def test_more_executions_alone_is_no_slot_cost_regression(self):
        # the slot-cost arm compares PER ATTEMPT: a class which merely ran
        # twice as often has double the totals and the same cost per
        # execution, which is volume, not a slowdown (#1390's false precision)
        baseline = {"samples": 10, "active_p95": None, "active_p50": None,
                    "slot_seconds": 20.0}
        verdict = judge_regression(
            dict(self.ROW, samples=40, active_p50=None, active_p95=None,
                 slot_seconds=80.0), baseline, factor=2.0, min_baseline=1.0,
            spike_allowance=0.1, samples_over_baseline=0)
        self.assertEqual(verdict["condition"], "healthy")
        self.assertNotIn("comparison", verdict)
        # the totals still travel as reported numbers, the ratio does not
        self.assertAlmostEqual(verdict["slot_cost_ratio"], 1.0)
        self.assertAlmostEqual(verdict["cost_per_attempt"], 2.0)
        self.assertAlmostEqual(verdict["baseline_cost_per_attempt"], 2.0)
        self.assertAlmostEqual(verdict["slot_seconds"], 80.0)
        self.assertAlmostEqual(verdict["baseline_slot_seconds"], 20.0)

    def test_a_slot_cost_regression_survives_a_change_in_volume(self):
        # the same arm still answers when the cost per execution really moved,
        # whether or not the window also holds more of them
        baseline = {"samples": 10, "active_p95": None, "active_p50": None,
                    "slot_seconds": 20.0}
        verdict = judge_regression(
            dict(self.ROW, samples=40, active_p50=None, active_p95=None,
                 slot_seconds=180.0), baseline, factor=2.0, min_baseline=1.0,
            spike_allowance=0.1, samples_over_baseline=10)
        self.assertEqual(verdict["condition"], "regression")
        self.assertEqual(verdict["comparison"], "slot_cost")
        self.assertAlmostEqual(verdict["slot_cost_ratio"], 2.25)

    def test_an_isolated_spike_is_no_slot_cost_regression_either(self):
        # both arms answer the same question with the same rule: an isolated
        # spike, seen only through the occupied cost, is the spike
        # completed_slow already called and not a second verdict
        baseline = {"samples": 10, "active_p95": None, "active_p50": None,
                    "slot_seconds": 20.0}
        verdict = judge_regression(
            dict(self.ROW, samples=40, active_p50=None, active_p95=None,
                 slot_seconds=180.0), baseline, factor=2.0, min_baseline=1.0,
            spike_allowance=0.1, samples_over_baseline=1)
        self.assertEqual(verdict["condition"], "healthy")
        self.assertTrue(verdict["spike_only"])

    def test_a_cost_arm_spike_needs_no_p95_ratio_to_be_filtered(self):
        # a sub-second p95 on both sides routes the comparison to the cost
        # arm; there the exceedance share over the class' own old p95 still
        # answers the spike question, so volume, tail or shift is decided the
        # same way as in the p95 arm
        baseline = {"samples": 10, "active_p95": 0.4, "active_p50": 0.3,
                    "slot_seconds": 20.0}
        spiked = judge_regression(
            dict(self.ROW, samples=40, active_p95=0.9, active_p50=0.3,
                 slot_seconds=180.0), baseline, factor=2.0, min_baseline=1.0,
            spike_allowance=0.1, samples_over_baseline=1)
        self.assertEqual(spiked["condition"], "healthy")
        self.assertTrue(spiked["spike_only"])
        # most of the window beyond the old range is not a tail any more
        shifted = judge_regression(
            dict(self.ROW, samples=40, active_p95=0.9, active_p50=0.3,
                 slot_seconds=180.0), baseline, factor=2.0, min_baseline=1.0,
            spike_allowance=0.1, samples_over_baseline=30)
        self.assertEqual(shifted["condition"], "regression")
        self.assertEqual(shifted["comparison"], "slot_cost")


class BeatRowTests(TestCase):
    """The detector runs on beat, as a row keyed by its name."""

    def test_beat_hands_the_detection_over_on_an_interval(self):
        create_task_performance_detection_task(sender=None)
        row = PeriodicTask.objects.get(
            name=TASK_PERFORMANCE_DETECTION_TASK_NAME)
        self.assertEqual(row.task, "system.tasks.detect_task_performance")
        self.assertEqual(row.interval.every, 15)
        self.assertEqual(row.interval.period, "minutes")
        # idempotent like every beat row of this deployment
        create_task_performance_detection_task(sender=None)
        self.assertEqual(
            PeriodicTask.objects.filter(
                name=TASK_PERFORMANCE_DETECTION_TASK_NAME).count(), 1)
