"""The legacy mirroring keeps answering the `TaskResult` rows it was given.

Before #1177 a POST which triggered a task was answered with a `TaskResult`
resource and the client polled that resource, whose states were mirrored into
its row by the celery signals connected in notify/tasks.py. The registration
contract has since moved to the `BackgroundProcess` (D01/B of #1175) and the
api publishes no row for new tasks any more; these tests keep the receivers
honest for the rows and messages of the coexistence window until #1179 retires
them.
"""

import json
from uuid import uuid4

from celery import Celery, states
from celery.app.task import Context
from celery.app.trace import build_tracer
from celery.exceptions import Reject, Retry
from celery.signals import task_revoked
from django.db import connection
from django.test import TransactionTestCase
from django.test.utils import CaptureQueriesContext, override_settings
from django_celery_results.models import TaskResult
from notify.enums import ProcessNameEnum, ProcessStatusEnum
from notify.models import BackgroundProcess
from notify.tasks import (MIRROR_TASK_RESULT_STAMP, BackgroundProcessBased,
                          serialize_result)

TASK_RESULT_TABLE = TaskResult._meta.db_table
BACKGROUND_PROCESS_TABLE = BackgroundProcess._meta.db_table


class WorkerRunMixin:
    """Answers tasks the way a worker does, so their signals are really sent.

    The mirroring listens to the signals celery's tracer sends while a task is
    answered, so the tests go through the tracer instead of calling the mirroring
    with hand made arguments. The app is of its own and its result backend is
    celery's in-process one: a broker is not needed to answer a task, and the
    deployment's Redis result backend must not be reached by accident here
    either - these tests are about the mirroring, not about the store the
    deployment chose in #1178.

    A task which the legacy async api published carries the very stamp the
    api used to put on the message it publishes (#1176); `answer` marks an
    opted-in task with it and leaves an untracked one unmarked. Since #1177
    the registration api stamps nothing - the marking is kept so these tests
    can still tell the mirroring's two paths apart.
    """

    def setUp(self):
        super().setUp()
        self.app = Celery('task-result-test', set_as_current=False)
        self.addCleanup(self.app.close)
        self.app.conf.result_backend = 'cache+memory://'
        self.task_id = str(uuid4())

    def task(self, function, **options):
        task = self.app.task(shared=False, **options)(function)
        task._backend = self.app.backend
        return task

    def answer(self, task, task_id=None, task_kwargs=None, opted_in=True):
        request = {'id': task_id or self.task_id}
        if opted_in:
            request['stamped_headers'] = [MIRROR_TASK_RESULT_STAMP]
            request['stamps'] = {MIRROR_TASK_RESULT_STAMP: True}
        trace = build_tracer(task.name, task, app=self.app)
        return trace(task_id or self.task_id, (), task_kwargs or {}, request)

    def publish(self):
        """The row the api leaves behind for the task it has just published."""
        return TaskResult.objects.create(task_id=self.task_id)


class TaskResultMirrorTests(WorkerRunMixin, TransactionTestCase):
    """Every state a task reaches is written into the row published for it.

    A `TransactionTestCase`: answering a task commits for real, because the
    worker's own `task_prerun` handler of this project (`close_connections_before_task`
    in MrMap/celery.py) closes the connection a `TestCase` runs its atomic block on.
    """

    def test_the_row_reads_started_while_the_task_is_running(self):
        @self.task
        def registering():
            # what a client polling the resource reads at this very moment
            return {"while_running": TaskResult.objects.get(
                task_id=self.task_id).status}

        row = self.publish()
        self.answer(registering)

        row.refresh_from_db()
        self.assertEqual(row.status, states.SUCCESS)
        self.assertEqual(
            json.loads(row.result)["while_running"], states.STARTED)
        self.assertIsNotNone(row.date_started)

    def test_a_task_which_answered_writes_its_result(self):
        outcome = {"data": {"type": "WebMapService", "id": str(uuid4())}}

        @self.task
        def registering():
            return outcome

        row = self.publish()
        created = row.date_done
        self.answer(registering)

        row.refresh_from_db()
        self.assertEqual(row.status, states.SUCCESS)
        self.assertDictEqual(json.loads(row.result), outcome)
        self.assertGreater(row.date_done, created)

    def test_a_failing_task_answers_its_error(self):
        @self.task
        def registering():
            raise ValueError('the capabilities document is broken')

        row = self.publish()
        self.answer(registering)

        row.refresh_from_db()
        self.assertEqual(row.status, states.FAILURE)
        self.assertIn('the capabilities document is broken', row.traceback)
        self.assertIsNotNone(row.date_done)

    def test_a_task_waiting_for_a_retry_is_not_reported_as_finished(self):
        @self.task
        def registering():
            raise Retry('the service is currently unreachable')

        row = self.publish()
        created = row.date_done
        self.answer(registering)

        row.refresh_from_db()
        self.assertEqual(row.status, states.RETRY)
        # the column says when the task was completed, so a task which still
        # waits for another attempt leaves it as it was
        self.assertEqual(row.date_done, created)

    def test_a_revoked_task_is_reported(self):
        @self.task
        def registering():
            return None

        row = self.publish()
        # a revoked task is never answered to an end, so no `task_postrun`
        # follows it, and the abort of a background process revokes the tasks it
        # waits for (see BackgroundProcess.save); the request of the revocation
        # carries the stamped headers of the message, as celery's own revoke
        # handling builds it from those headers
        task_revoked.send(
            sender=registering,
            request=Context({
                "id": self.task_id,
                "stamped_headers": [MIRROR_TASK_RESULT_STAMP],
            }),
            terminated=True,
            signum=9,
            expired=False)

        row.refresh_from_db()
        self.assertEqual(row.status, states.REVOKED)
        self.assertIsNotNone(row.date_done)

    def test_no_row_is_made_for_a_task_which_was_never_published(self):
        """The mirroring only writes a row which the api published before.

        Even an opted-in task which somehow lost its row must not leave a new
        one behind: the resource belongs to the api, which inserts the row
        together with the task it answers with.
        """
        @self.task
        def import_record():
            return 'imported'

        self.answer(import_record)

        self.assertEqual(TaskResult.objects.count(), 0)

    def test_a_child_published_inside_a_registration_is_not_marked(self):
        """The opt-in belongs to the one message the api published (#1176).

        Celery carries stamped headers to the callbacks and the chain of a
        message, never to a task the body publishes of its own. The test answers
        the registration eagerly so its body publishes the child for real, and
        both read what their own request was marked with.
        """
        self.app.conf.task_always_eager = True
        self.addCleanup(
            lambda: setattr(self.app.conf, 'task_always_eager', False))
        seen = {}

        @self.task
        def build_layer():
            seen['child'] = build_layer.request.stamped_headers
            return 'layer built'

        @self.task
        def registering():
            seen['root'] = registering.request.stamped_headers
            build_layer.apply_async()
            return 'registered'

        row = self.publish()
        registering.apply(
            task_id=self.task_id,
            stamped_headers=[MIRROR_TASK_RESULT_STAMP],
            **{MIRROR_TASK_RESULT_STAMP: True})

        self.assertIn(
            MIRROR_TASK_RESULT_STAMP, seen['root'] or [],
            'the api marks the task it published itself')
        self.assertNotIn(
            MIRROR_TASK_RESULT_STAMP, seen['child'] or [],
            'a task the body publishes is not marked by that publication')
        # the row follows the root task alone
        row.refresh_from_db()
        self.assertEqual(row.status, states.SUCCESS)

    def test_a_state_the_model_does_not_know_is_left_alone(self):
        @self.task
        def registering():
            raise Reject('nothing to do here', requeue=False)

        row = self.publish()
        self.answer(registering)

        # the resource would answer a status its schema does not declare, and
        # celery's own database backend does not store this state either
        row.refresh_from_db()
        self.assertEqual(row.status, states.STARTED)

    def test_a_result_which_cannot_be_expressed_is_left_out(self):
        # losing the value must not cost the client the state of its task
        with self.assertLogs('MrMap.root', level='WARNING'):
            self.assertIsNone(serialize_result(object()))


@override_settings(CHANNEL_LAYERS={
    "default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}})
class UntrackedTaskTests(WorkerRunMixin, TransactionTestCase):
    """Tasks which the async api did not publish do no `TaskResult` sql (#1176).

    The mirroring of #1164 asked postgres about every task of the deployment -
    the harvesting and the monitoring fan out among them; an indexed `UPDATE`
    which matches no row still costs a database round trip per task and
    signal. Only the opt-in of `AsyncCreateMixin`, read by `mirror_requested`
    from the request of the task, takes part now. These tests answer untracked
    tasks through the tracer and count the sql they cost, not only the rows
    they leave behind.
    """

    def setUp(self):
        super().setUp()
        # the domain table whose reads and writes the tests below tell apart
        # from the mirroring: what an untracked harvesting task legitimately
        # does must stay
        BackgroundProcess.objects.create(
            phase='waiting',
            process_type=ProcessNameEnum.HARVESTING.value,
            description='an unrelated job')

    def assert_no_task_result_sql(self, run):
        """`run` answers no sql against the `TaskResult` table at all.

        A marker query on a table of the domain runs inside the capture: the
        worker's own prerun and postrun handlers of this project close the
        connection around a task, and the marker is what tells a capture which
        saw the run apart from one which saw nothing - an assertion on an
        empty capture would prove nothing.
        """
        with CaptureQueriesContext(connection) as captured:
            run()
            BackgroundProcess.objects.count()

        queries = captured.captured_queries
        self.assertTrue(
            any(BACKGROUND_PROCESS_TABLE in q['sql'] for q in queries),
            'the capture did not see the marker query; asserting the absence '
            'of TaskResult sql on an empty capture means nothing')
        self.assertEqual(
            [q['sql'] for q in queries if TASK_RESULT_TABLE in q['sql']], [],
            'a task which was not published by the async api must not cost '
            'any TaskResult sql')

    def test_a_successful_untracked_task_costs_no_task_result_sql(self):
        @self.task
        def import_record():
            return 'imported'

        row = self.publish()
        self.assert_no_task_result_sql(
            lambda: self.answer(import_record, opted_in=False))

        # the row of an unrelated registration stays exactly as it was
        row.refresh_from_db()
        self.assertEqual(row.status, states.PENDING)
        self.assertEqual(TaskResult.objects.count(), 1)

    def test_a_failing_untracked_task_costs_no_task_result_sql(self):
        @self.task
        def import_record():
            raise ValueError('the endpoint answered garbage')

        row = self.publish()
        self.assert_no_task_result_sql(
            lambda: self.answer(import_record, opted_in=False))

        row.refresh_from_db()
        self.assertEqual(row.status, states.PENDING)

    def test_a_retried_untracked_task_costs_no_task_result_sql(self):
        @self.task
        def import_record():
            raise Retry('the service is currently unreachable')

        row = self.publish()
        self.assert_no_task_result_sql(
            lambda: self.answer(import_record, opted_in=False))

        row.refresh_from_db()
        self.assertEqual(row.status, states.PENDING)

    def test_a_revoked_untracked_task_costs_no_task_result_sql(self):
        @self.task
        def import_record():
            return 'imported'

        row = self.publish()
        # celery builds the request of a revocation from the headers of the
        # message; an untracked one carries no stamped headers
        self.assert_no_task_result_sql(
            lambda: task_revoked.send(
                sender=import_record,
                request=Context({'id': self.task_id}),
                terminated=True,
                signum=9,
                expired=False))

        row.refresh_from_db()
        self.assertEqual(row.status, states.PENDING)

    def test_an_untracked_task_still_writes_its_background_process(self):
        """The count tells the mirroring apart from the writes of the domain.

        An untracked `BackgroundProcessBased` task still reports its progress -
        those writes belong to the domain and stay - while the `TaskResult`
        mirroring is what it must not cost any more.
        """
        process = BackgroundProcess.objects.create(
            phase='waiting',
            process_type=ProcessNameEnum.HARVESTING.value,
            description='a harvesting job')

        def import_record(background_process_pk=None):
            # like the real tasks: the process is handed to the body, the
            # prerun handler of notify reads it back off the signal's kwargs
            return 'imported'

        harvest_records = self.task(
            import_record, base=BackgroundProcessBased)

        with CaptureQueriesContext(connection) as captured:
            self.answer(
                harvest_records,
                task_kwargs={'background_process_pk': process.pk},
                opted_in=False)

        queries = captured.captured_queries
        self.assertEqual(
            [q['sql'] for q in queries if TASK_RESULT_TABLE in q['sql']], [],
            'the mirroring must not touch the table of an untracked task')
        self.assertTrue(
            any(BACKGROUND_PROCESS_TABLE in q['sql']
                and q['sql'].startswith('UPDATE') for q in queries),
            'the reporting of the background process must not be lost with '
            'the mirroring')

        process.refresh_from_db()
        self.assertEqual(process.status, ProcessStatusEnum.RUNNING)
        self.assertEqual(TaskResult.objects.count(), 0)
