from unittest.mock import patch

from celery.app.task import Context
from celery.exceptions import Retry
from celery.signals import task_revoked
from django.db import connection
from django.test import TestCase, TransactionTestCase
from django.test.utils import CaptureQueriesContext
from notify.enums import ProcessNameEnum, ProcessStatusEnum
from notify.models import BackgroundProcess
from notify.tasks import BackgroundProcessBased, get_background_process
from tests.django.utils import WorkerRunMixin

BACKGROUND_PROCESS_TABLE = BackgroundProcess._meta.db_table


class BackgroundProcessTaskTests(TestCase):
    def setUp(self):
        self.process = BackgroundProcess.objects.create(
            process_type='registering', phase='queued', total_steps=4, done_steps=1)
        self.task = BackgroundProcessBased()
        self.task.background_process_pk = self.process.pk

    def info(self):
        return BackgroundProcess.objects.process_info().get(pk=self.process.pk)

    def assert_process_broadcast_once(self, send):
        """The process was broadcast once, whatever else the task saved.

        The patch sits on `post_save.send` itself, so while it is active it
        sees the save of every model: a task which fails leaves a log entry
        beside the process it reports to (#1177). What must not happen is a
        process written twice, once by a transition and once by a late report,
        and that is what the callers of this assert about.
        """
        broadcasts = [
            call for call in send.call_args_list
            if (call.args[0] if call.args else call.kwargs.get("sender"))
            is BackgroundProcess]
        self.assertEqual(
            len(broadcasts), 1,
            f"the process was broadcast {len(broadcasts)} times: "
            f"{send.call_args_list}")

    @patch('notify.tasks.post_save.send')
    def test_start_does_not_require_task_results(self, send):
        get_background_process(self.task, kwargs={'background_process_pk': self.process.pk})
        self.assertEqual(self.info().status, ProcessStatusEnum.RUNNING)
        self.assertEqual(self.info().progress, 25)
        send.assert_called_once()

    @patch('notify.tasks.post_save.send')
    def test_start_does_not_broadcast_a_running_process(self, send):
        self.process.status = ProcessStatusEnum.RUNNING
        self.process.save(update_fields=['status'])
        # der Patch liegt auf dem Signal-Objekt, das save() oben hat also schon
        # einmal ausgeloesen
        send.reset_mock()
        get_background_process(self.task, kwargs={'background_process_pk': self.process.pk})
        self.assertFalse(send.called)
        self.assertEqual(self.info().status, ProcessStatusEnum.RUNNING)

    @patch('notify.tasks.post_save.send')
    def test_broadcast_carries_annotation_and_related_type(self, send):
        self.task.update_background_process(step_done=True)
        instance = send.call_args.kwargs['instance']
        self.assertEqual(instance.progress, 50)
        with self.assertNumQueries(0):
            instance.related_resource_type

    @patch('notify.tasks.post_save.send')
    def test_failure_preserves_progress_and_error(self, send):
        self.task.on_failure(ValueError('broken'), 'task-id', (), {}, None)
        process = self.info()
        self.assertEqual(process.status, ProcessStatusEnum.FAILED)
        self.assertEqual(process.phase, 'An error occurred: broken')
        self.assertEqual(process.progress, 25)
        self.assertEqual(process.done_steps, 1)
        self.assertIsNotNone(process.done_at)
        self.task.update_background_process(completed=True)
        self.task.update_background_process(phase='late update', step_done=True)
        self.assertEqual(self.info().status, ProcessStatusEnum.FAILED)
        self.assertEqual(self.info().phase, process.phase)
        # the two later reports of a process which already failed wrote nothing
        self.assert_process_broadcast_once(send)

    @patch('notify.tasks.post_save.send')
    def test_completion_is_terminal(self, send):
        self.task.update_background_process(completed=True)
        self.task.on_failure(ValueError('late failure'), 'task-id', (), {}, None)
        process = self.info()
        self.assertEqual(process.status, ProcessStatusEnum.COMPLETED)
        self.assertEqual(process.progress, 100)
        self.assertEqual(process.done_steps, 4)
        # the failure which arrived after the completion wrote nothing
        self.assert_process_broadcast_once(send)

    @patch('notify.models.app.control.revoke')
    @patch('notify.models.BackgroundProcess.get_related_task_ids', return_value=[])
    @patch('notify.tasks.post_save.send')
    def test_abort_is_terminal(self, send, task_ids, revoke):
        self.process.phase = 'abort'
        self.process.save(update_fields=['phase'])
        self.task.update_background_process(completed=True)
        self.assertEqual(self.info().status, ProcessStatusEnum.ABORTED)
        self.assertEqual(self.info().progress, 25)

    @patch('notify.tasks.post_save.send')
    def test_zero_total_can_be_set(self, send):
        self.task.update_background_process(total_steps=0)
        self.assertEqual(self.info().total_steps, 0)
        self.assertEqual(self.info().progress, 0)

    @patch('notify.tasks.post_save.send')
    def test_step_reports_are_capped_at_the_total(self, send):
        """A step report never moves the progress past the total (#1258, #1261).

        This path used to write a bare `F("done_steps") + 1`, so a duplicated
        delivery of one step pushed the process beyond 100 %; it now shares
        the capped increment of the manager's report. The cap must not eat
        ordinary steps either: with a total of 4 and one step already done,
        the first three of these six reports still count.
        """
        for _ in range(6):
            self.task.update_background_process(step_done=True)

        process = self.info()
        self.assertEqual(process.total_steps, 4)
        self.assertEqual(process.done_steps, 4)
        self.assertEqual(process.progress, 100)


class NoPerTaskResultBookkeepingTests(WorkerRunMixin, TransactionTestCase):
    """No task of the deployment books itself in a generic per-task result table.

    The mirroring of #1164 wrote a `TaskResult` row for the tasks the
    asynchronous api published, #1176 narrowed it to the opted-in ones, and
    #1180 removes it together with the package. What stays is the property both
    guarded and which #1175 names as its completion criterion: a task at no
    lifecycle stage costs sql against a generic result table, and no per-child
    model takes its place.

    Asked of the sql a run issues, matched on the name such a table carries,
    and never of a model: the guard has to outlive the import of the package it
    guards against.
    """

    def setUp(self):
        super().setUp()
        # the domain table whose reads and writes are told apart from a
        # per-task bookkeeping: what a harvesting task legitimately does must
        # stay
        BackgroundProcess.objects.create(
            phase='waiting',
            process_type=ProcessNameEnum.HARVESTING.value,
            description='an unrelated job')

    def assert_no_per_task_result_sql(self, run):
        """`run` issues no sql against a generic per-task result table.

        A marker query on a table of the domain runs inside the capture: the
        worker's own prerun and postrun handlers of this project close the
        connection around a task, and the marker is what tells a capture which
        saw the run apart from one which saw nothing - an assertion on an empty
        capture would prove nothing.
        """
        with CaptureQueriesContext(connection) as captured:
            run()
            BackgroundProcess.objects.count()

        queries = captured.captured_queries
        self.assertTrue(
            any(BACKGROUND_PROCESS_TABLE in q['sql'] for q in queries),
            'the capture did not see the marker query; asserting the absence '
            'of per-task result sql on an empty capture means nothing')
        self.assertEqual(
            [q['sql'] for q in queries
             if 'celery_results' in q['sql'].lower()], [],
            'a task must not book itself in a generic per-task result table')

    def test_a_successful_task_costs_no_per_task_result_sql(self):
        @self.task
        def import_record():
            return 'imported'

        self.assert_no_per_task_result_sql(
            lambda: self.answer(import_record))

    def test_a_failing_task_costs_no_per_task_result_sql(self):
        @self.task
        def import_record():
            raise ValueError('the endpoint answered garbage')

        self.assert_no_per_task_result_sql(
            lambda: self.answer(import_record))

    def test_a_retried_task_costs_no_per_task_result_sql(self):
        @self.task
        def import_record():
            raise Retry('the service is currently unreachable')

        self.assert_no_per_task_result_sql(
            lambda: self.answer(import_record))

    def test_a_revoked_task_costs_no_per_task_result_sql(self):
        @self.task
        def import_record():
            return 'imported'

        # celery builds the request of a revocation from the headers of the
        # message it revokes
        self.assert_no_per_task_result_sql(
            lambda: task_revoked.send(
                sender=import_record,
                request=Context({'id': self.task_id}),
                terminated=True,
                signum=9,
                expired=False))
