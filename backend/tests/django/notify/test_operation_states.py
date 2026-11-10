"""The normalized operation contract of the background activity (#1207).

A background process is where the background job center of the frontend
follows one logical operation from the moment it was made until it decided
about itself. The stored status of a process answers what the last reporter
wrote; the contract answers the questions the drawer renders with one
normalized ``state``, a ``revision`` which orders the events of one
operation, the progress numerator and denominator, the retry state, the
error summary and the related resource which groups the operations.

The state is derived over the stored fields by an annotation -
``OperationStateEnum.derive`` is its python mirror - so these tests hold the
two answers against each other and against the meaning of every case.
"""
from collections import namedtuple
from datetime import timedelta
from itertools import product
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from celery.exceptions import Retry
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils.timezone import now
from notify.enums import (LogTypeEnum, OperationStateEnum, ProcessNameEnum,
                          ProcessStatusEnum)
from notify.filters import BackgroundProcessFilterSet
from notify.models import BackgroundProcess, BackgroundProcessLog
from notify.tasks import BackgroundProcessBased, report_process_retry

Case = namedtuple("Case", "status action window total")
WINDOWS = {
    "none": None,
    "open": timedelta(hours=1),
    "closed": timedelta(hours=-1),
}
#: the terminal stored statuses and the states they always answer
TERMINAL = {
    ProcessStatusEnum.COMPLETED: OperationStateEnum.COMPLETED,
    ProcessStatusEnum.FAILED: OperationStateEnum.FAILED,
    ProcessStatusEnum.ABORTED: OperationStateEnum.ABORTED,
}


def create(**values):
    values.setdefault("phase", "a phase")
    values.setdefault("process_type", ProcessNameEnum.MONITORING.value)
    values.setdefault("description", "an operation of the background activity")
    return BackgroundProcess.objects.create(**values)


def info(pk):
    return BackgroundProcess.objects.process_info().get(pk=pk)


class OperationStateDerivationTests(TestCase):
    """The annotation and its python mirror answer one state per stored case.

    The annotation is what every list row, every websocket payload and the
    state filter read; the python mirror is what an instance rendered
    straight after its creation answers, where no annotation exists yet. The
    two may never disagree about the same stored values.
    """

    CASES = [Case(*combination) for combination in product(
        ProcessStatusEnum,
        [False, True],
        ["none", "open", "closed"],
        [None, 0, 5],
    )]

    @classmethod
    def setUpTestData(cls):
        cls.processes = {}
        for case in cls.CASES:
            window = WINDOWS[case.window]
            cls.processes[case] = BackgroundProcess.objects.create(
                phase="a phase",
                process_type=ProcessNameEnum.MONITORING.value,
                description="an operation of the background activity",
                status=case.status,
                action_required=case.action,
                retry_scheduled_until=(
                    now() + window if window is not None else None),
                total_steps=case.total)

    def test_the_annotation_and_the_python_mirror_answer_the_same_state(self):
        for case, process in self.processes.items():
            with self.subTest(case=case):
                window = WINDOWS[case.window]
                self.assertEqual(
                    OperationStateEnum.derive(
                        case.status,
                        action_required=case.action,
                        retry_scheduled_until=(
                            now() + window if window is not None else None),
                        total_steps=case.total),
                    info(process.pk).state)

    def test_a_process_which_waits_for_a_worker_is_queued(self):
        pending = self.processes[Case(
            ProcessStatusEnum.PENDING, False, "none", None)]
        self.assertEqual(
            OperationStateEnum.QUEUED.value, info(pending.pk).state)

    def test_a_running_process_with_known_steps_runs_determinate(self):
        running = self.processes[Case(
            ProcessStatusEnum.RUNNING, False, "none", 5)]
        self.assertEqual(
            OperationStateEnum.RUNNING.value, info(running.pk).state)

    def test_a_running_process_without_a_denominator_is_indeterminate(self):
        """the epic draws an indeterminate bar where the total is unknown -
        and a total of 0 is no denominator either"""
        for total in (None, 0):
            running = self.processes[Case(
                ProcessStatusEnum.RUNNING, False, "none", total)]
            with self.subTest(total=total):
                self.assertEqual(
                    OperationStateEnum.RUNNING_INDETERMINATE.value,
                    info(running.pk).state)

    def test_an_open_retry_window_reports_retrying(self):
        retrying = self.processes[Case(
            ProcessStatusEnum.RUNNING, False, "open", 5)]
        self.assertEqual(
            OperationStateEnum.RETRYING.value, info(retrying.pk).state)

    def test_a_passed_retry_window_reads_running_again(self):
        """the window closing is no write - the state simply stops holding,
        so a reader sees running again without anybody reporting it"""
        passed = self.processes[Case(
            ProcessStatusEnum.RUNNING, False, "closed", 5)]
        self.assertEqual(
            OperationStateEnum.RUNNING.value, info(passed.pk).state)

    def test_a_process_awaiting_a_human_reports_action_required(self):
        attention = self.processes[Case(
            ProcessStatusEnum.RUNNING, True, "none", 5)]
        self.assertEqual(
            OperationStateEnum.ACTION_REQUIRED.value,
            info(attention.pk).state)

    def test_a_terminal_process_outranks_attention_and_retry(self):
        for status in (ProcessStatusEnum.COMPLETED, ProcessStatusEnum.FAILED,
                       ProcessStatusEnum.ABORTED):
            for window in ("open", "closed"):
                decided = self.processes[Case(status, True, window, None)]
                with self.subTest(status=status, window=window):
                    self.assertEqual(
                        TERMINAL[status].value, info(decided.pk).state)


class ProcessRevisionTests(TestCase):
    """Every state report carries the revision which orders it (#1207).

    The messages of one operation reach a client over a fan out which may
    deliver them out of order, and the client cannot tell a stale answer
    from the newest one by its content alone. The revision is counted by the
    database in the same write which moved the state, so it is monotonic per
    operation across concurrent reporters, and every payload of the operation
    names the revision of the state it carries.
    """

    def setUp(self):
        self.process = create(status=ProcessStatusEnum.PENDING)

    def revision(self):
        return BackgroundProcess.objects.get(pk=self.process.pk).revision

    def test_a_created_process_starts_at_revision_zero(self):
        self.assertEqual(0, self.revision())

    def test_the_reports_of_a_process_bump_the_revision_in_order(self):
        revisions = [self.revision()]
        BackgroundProcess.objects.report(
            self.process.pk, ProcessStatusEnum.RUNNING, total_steps=4)
        revisions.append(self.revision())
        BackgroundProcess.objects.report(
            self.process.pk, ProcessStatusEnum.RUNNING, step_done=True)
        revisions.append(self.revision())
        BackgroundProcess.objects.raise_steps(self.process.pk, 3)
        revisions.append(self.revision())
        BackgroundProcess.objects.report(
            self.process.pk, ProcessStatusEnum.COMPLETED)
        revisions.append(self.revision())

        self.assertEqual([0, 1, 2, 3, 4], revisions)

    def test_the_listeners_learn_the_revision_of_the_state_they_carry(self):
        BackgroundProcess.objects.report(
            self.process.pk, ProcessStatusEnum.RUNNING)
        with patch("notify.managers.post_save") as post_save:
            BackgroundProcess.objects.report(
                self.process.pk, ProcessStatusEnum.RUNNING, step_done=True)

        instance = post_save.send.call_args.kwargs["instance"]
        self.assertEqual(2, instance.revision)
        self.assertEqual(1, instance.done_steps)

    def test_the_task_base_reports_its_writes_with_a_revision(self):
        task = BackgroundProcessBased()
        task.background_process_pk = self.process.pk
        task.update_background_process(phase="parsing")

        self.assertEqual(1, self.revision())

    def test_an_abort_through_save_bumps_the_revision(self):
        process = BackgroundProcess.objects.get(pk=self.process.pk)
        process.phase = "abort"
        with patch.object(
                BackgroundProcess, "get_related_task_ids", return_value=[]):
            process.save()

        self.assertEqual(1, self.revision())
        # the instance which the response of the abort renders answers the
        # number, not the expression the database computed
        self.assertEqual(1, process.revision)

    def test_a_save_through_update_fields_still_bumps_it(self):
        process = BackgroundProcess.objects.get(pk=self.process.pk)
        process.description = "another description"
        process.save(update_fields=["description"])

        self.assertEqual(1, self.revision())


class ErrorSummaryTests(TestCase):
    """The summary of what went wrong is the last error the operation told.

    A failed operation must stay discoverable after a reload (#1203), and the
    drawer has to answer why per row without one query per row: the summary
    is the newest error log of the process, annotated over the list.
    """

    def setUp(self):
        self.process = create(status=ProcessStatusEnum.FAILED)
        self.other = create(status=ProcessStatusEnum.RUNNING)

    def test_the_newest_error_wins(self):
        moment = now()
        BackgroundProcessLog.objects.create(
            background_process=self.process,
            log_type=LogTypeEnum.ERROR,
            description="the first error",
            date=moment - timedelta(minutes=1))
        BackgroundProcessLog.objects.create(
            background_process=self.process,
            log_type=LogTypeEnum.ERROR,
            description="the second error",
            date=moment)

        self.assertEqual(
            "the second error", info(self.process.pk).error_summary)

    def test_a_warning_is_not_the_summary_of_an_error(self):
        BackgroundProcessLog.objects.create(
            background_process=self.process,
            log_type=LogTypeEnum.WARNING,
            description="a warning")

        self.assertIsNone(info(self.process.pk).error_summary)

    def test_an_operation_without_an_error_answers_no_summary(self):
        self.assertIsNone(info(self.other.pk).error_summary)

    def test_the_logs_of_another_operation_do_not_answer_it(self):
        BackgroundProcessLog.objects.create(
            background_process=self.other,
            log_type=LogTypeEnum.ERROR,
            description="the error of another operation")

        self.assertIsNone(info(self.process.pk).error_summary)

    def test_the_summary_is_one_query_over_the_list(self):
        """the payload of every row of the overview is rendered, so the summary
        may not cost one query per row: it rides along in the single query of
        the list as a subquery, which is what this asserts"""
        for _ in range(5):
            process = create()
            BackgroundProcessLog.objects.create(
                background_process=process,
                log_type=LogTypeEnum.ERROR,
                description="an error")

        with CaptureQueriesContext(connection) as queries:
            answered = list(BackgroundProcess.objects.process_info())

        self.assertTrue(answered)
        self.assertEqual(1, len(queries.captured_queries))
        self.assertIn(
            "notify_backgroundprocesslog",
            queries.captured_queries[0]["sql"])


class ReportRetryTests(TestCase):
    """The retry of a task moves the state of the operation it reports.

    A retry neither failed nor progressed: the operation waits for the next
    attempt of one of its tasks. The window until that attempt is due is what
    reads as retrying, and it rewrites itself per retry and closes by itself
    when it passed.
    """

    def setUp(self):
        self.process = create(status=ProcessStatusEnum.RUNNING, total_steps=4)

    def test_a_reported_retry_writes_count_reason_and_window(self):
        until = now() + timedelta(seconds=30)
        updated = BackgroundProcess.objects.report_retry(
            self.process.pk, reason="the remote did not answer", until=until)

        self.assertEqual(1, updated)
        process = info(self.process.pk)
        self.assertEqual(1, process.retry_count)
        self.assertEqual("the remote did not answer", process.retry_reason)
        self.assertEqual(until, process.retry_scheduled_until)
        self.assertEqual(
            OperationStateEnum.RETRYING.value, process.state)

    def test_retries_add_up_and_the_last_reason_stands(self):
        for attempt in range(3):
            BackgroundProcess.objects.report_retry(
                self.process.pk, reason=f"failure {attempt}",
                until=now() + timedelta(seconds=30))

        process = info(self.process.pk)
        self.assertEqual(3, process.retry_count)
        self.assertEqual("failure 2", process.retry_reason)

    def test_a_long_reason_is_truncated_and_not_rejected(self):
        BackgroundProcess.objects.report_retry(
            self.process.pk, reason="x" * 5000, until=now())

        self.assertEqual(512, len(BackgroundProcess.objects.get(
            pk=self.process.pk).retry_reason))

    def test_a_progress_report_ends_the_retry_window(self):
        BackgroundProcess.objects.report_retry(
            self.process.pk, reason="a hiccup",
            until=now() + timedelta(hours=1))
        BackgroundProcess.objects.report(
            self.process.pk, ProcessStatusEnum.RUNNING, step_done=True)

        process = info(self.process.pk)
        self.assertIsNone(process.retry_scheduled_until)
        self.assertEqual(OperationStateEnum.RUNNING.value, process.state)

    def test_a_process_which_decided_about_itself_reports_no_retry(self):
        BackgroundProcess.objects.report(
            self.process.pk, ProcessStatusEnum.COMPLETED)

        self.assertEqual(
            0, BackgroundProcess.objects.report_retry(
                self.process.pk, reason="too late", until=now()))

    def test_a_retry_without_a_process_does_nothing(self):
        self.assertEqual(
            0, BackgroundProcess.objects.report_retry(
                None, reason="nowhere to report", until=now()))


class ActionRequiredTests(TestCase):
    """The flag behind the action-required state is written by its deciders.

    The watchdog of a stalled import (#1038) and the review of an update
    decide that the work stands until a human acts. The flag flips once per
    decision: a reporter which re-reports its stall per beat may not shout a
    message per fire into the open overviews of the frontend.
    """

    def setUp(self):
        self.process = create(status=ProcessStatusEnum.RUNNING, total_steps=2)

    def test_setting_the_flag_flips_the_state_and_bumps_the_revision(self):
        updated = BackgroundProcess.objects.set_action_required(
            self.process.pk, True, phase="import backlog stalled")

        self.assertEqual(1, updated)
        process = info(self.process.pk)
        self.assertTrue(process.action_required)
        self.assertEqual(1, process.revision)
        self.assertEqual("import backlog stalled", process.phase)
        self.assertEqual(
            OperationStateEnum.ACTION_REQUIRED.value, process.state)

    def test_repeating_the_decision_writes_and_broadcasts_nothing(self):
        BackgroundProcess.objects.set_action_required(self.process.pk, True)
        with patch("notify.managers.post_save") as post_save:
            updated = BackgroundProcess.objects.set_action_required(
                self.process.pk, True)

        self.assertEqual(0, updated)
        post_save.send.assert_not_called()

    def test_clearing_the_flag_returns_the_state_to_running(self):
        BackgroundProcess.objects.set_action_required(self.process.pk, True)
        BackgroundProcess.objects.set_action_required(self.process.pk, False)

        process = info(self.process.pk)
        self.assertFalse(process.action_required)
        self.assertEqual(OperationStateEnum.RUNNING.value, process.state)

    def test_a_process_which_decided_about_itself_stays_undecided_by_it(self):
        BackgroundProcess.objects.report(
            self.process.pk, ProcessStatusEnum.ABORTED)

        self.assertEqual(
            0, BackgroundProcess.objects.set_action_required(
                self.process.pk, True))

    def test_a_flag_without_a_process_does_nothing(self):
        self.assertEqual(
            0, BackgroundProcess.objects.set_action_required(None, True))


class TaskRetryReportingTests(TestCase):
    """The celery ``task_retry`` signal reports a retry onto the process.

    The seam is the kwargs the broker transports - the same one the task
    start uses - and the window of the next attempt is answered from what
    celery hands over: the seconds or eta of an explicit retry, or, where a
    retry ran without either, the backoff its own policy would compute.
    """

    class RetryPolicy:
        retry_backoff = 30
        retry_backoff_max = 300
        retry_jitter = False

    def setUp(self):
        self.process = create(status=ProcessStatusEnum.RUNNING, total_steps=4)
        self.request = SimpleNamespace(
            kwargs={"background_process_pk": str(self.process.pk)},
            retries=1)

    def test_a_retry_with_an_explicit_countdown_opens_the_window(self):
        before = now()
        report_process_retry(
            sender=self.RetryPolicy, request=self.request,
            reason=Retry(
                exc=ConnectionError("the remote did not answer"), when=60))

        process = info(self.process.pk)
        self.assertEqual(1, process.retry_count)
        self.assertIn("the remote did not answer", process.retry_reason)
        delta = (process.retry_scheduled_until - before).total_seconds()
        self.assertGreater(delta, 50)
        self.assertLess(delta, 90)

    def test_a_retry_without_a_countdown_answers_its_policies_backoff(self):
        """retries=1 of a 30 s backoff capped at 300 s is 60 s - the number
        celery's own ``get_exponential_backoff_interval`` computes"""
        before = now()
        report_process_retry(
            sender=self.RetryPolicy, request=self.request,
            reason=Retry(exc=TimeoutError("no answer")))

        delta = (info(self.process.pk).retry_scheduled_until
                 - before).total_seconds()
        self.assertGreater(delta, 50)
        self.assertLess(delta, 70)

    def test_a_retry_with_an_explicit_eta_wins(self):
        eta = now() + timedelta(minutes=7)
        report_process_retry(
            sender=self.RetryPolicy, request=self.request,
            reason=Retry(exc=ConnectionError("no answer"), when=eta))

        self.assertEqual(
            eta, info(self.process.pk).retry_scheduled_until)

    def test_a_task_without_a_process_retries_invisibly(self):
        request = SimpleNamespace(kwargs={}, retries=0)
        report_process_retry(
            sender=self.RetryPolicy, request=request,
            reason=Retry(exc=ConnectionError("no answer"), when=60))

        self.assertEqual(
            0, BackgroundProcess.objects.get(
                pk=self.process.pk).retry_count)

    def test_a_broken_report_does_not_break_the_retry(self):
        """the process row is gone - the report has to fail quietly, the
        retry itself must not hinge on it"""
        self.process.delete()
        report_process_retry(
            sender=self.RetryPolicy, request=self.request,
            reason=Retry(exc=ConnectionError("no answer"), when=60))


class StateFilterTests(TestCase):
    """The drawer asks for the states it renders, not for columns.

    The state is an annotation, so the filter answers on the queryset of the
    overview, exactly like the progress annotation before it.
    """

    def setUp(self):
        at = now()
        self.queued = create(status=ProcessStatusEnum.PENDING)
        self.running = create(
            status=ProcessStatusEnum.RUNNING, total_steps=4)
        self.indeterminate = create(status=ProcessStatusEnum.RUNNING)
        self.retrying = create(
            status=ProcessStatusEnum.RUNNING, total_steps=2,
            retry_scheduled_until=at + timedelta(hours=1))
        self.attention = create(
            status=ProcessStatusEnum.RUNNING, total_steps=2,
            action_required=True)
        self.failed = create(status=ProcessStatusEnum.FAILED)

    def filtered(self, **data):
        return BackgroundProcessFilterSet(
            data, queryset=BackgroundProcess.objects.process_info())

    def test_filters_one_state_by_its_name(self):
        self.assertEqual(
            [self.running], list(self.filtered(state="running").qs))

    def test_filters_multiple_states_by_their_names(self):
        self.assertEqual(
            {self.queued.pk, self.failed.pk},
            {p.pk for p in self.filtered(state="queued,failed").qs})

    def test_the_state_lookup_is_askable_with_the_in_suffix(self):
        """the tabs of the job center ask for a set of states the way they ask
        for a set of ids, so `state.in` is a filter of its own (#1207)"""
        self.assertEqual(
            {self.queued.pk, self.failed.pk},
            {p.pk for p in self.filtered(state__in="queued,failed").qs})

    def test_the_indeterminate_state_is_askable_apart(self):
        self.assertEqual(
            [self.indeterminate],
            list(self.filtered(state="running_indeterminate").qs))

    def test_a_state_the_api_does_not_answer_is_refused(self):
        filterset = self.filtered(state="strolling")
        self.assertFalse(filterset.is_valid())
        self.assertIn(
            "invalid_choice",
            filterset.errors["state"].as_data()[0].code)

    def test_filters_the_operations_of_one_related_resource(self):
        group = uuid4()
        for process in (self.queued, self.running):
            BackgroundProcess.objects.filter(pk=process.pk).update(
                related_id=group)

        self.assertEqual(
            {self.queued.pk, self.running.pk},
            {p.pk for p in self.filtered(related_id=str(group)).qs})
        self.assertEqual(
            {self.queued.pk, self.running.pk},
            {p.pk for p in self.filtered(related_id__in=str(group)).qs})
