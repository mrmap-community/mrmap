"""Task-side SQL guards for the singleton fire seam (#1395).

Audit page: ``docs/source/development/celery-task-orm-audit.rst`` ("Family:
the singleton seam"). EVERY task of the beat schedules runs through
``SingletonTask.__call__`` (``extras/tasks.py``), so this is the one SQL
shape every single Celery task of the deployment pays - and the one whose
drift would be multiplied by every task and every interval. What this
pins, per the #1395 coverage checklist:

*   an ACQUIRED fire costs exactly two statements on the dedicated lock
    session: ``pg_try_advisory_lock`` and its ``pg_advisory_unlock`` - no
    drift table, no bookkeeping INSERT, no read of an application table;
*   a REFUSED fire costs exactly one statement and runs no body;
*   the cost is per fire and constant: five fires pay ten statements on
    the lock session, not a growing history of previous fires.

The statements are recorded on the lock session itself - the wrapper
``singleton_connection`` hands out - because a capture of the DEFAULT
connection can never see them: #852's lock deliberately lives on a session
of its own. The numbers are statements, not runtime (V1 scope; #1396 owns
timings).
"""
import threading
from unittest.mock import patch
from uuid import uuid4

from celery import Celery
from django.test import TestCase

from extras.tasks import SingletonTask, singleton_lock_id

# a test thread which does not finish within this many seconds is a broken
# test and not a task which is still running (the neighbour's rule)
TIMEOUT = 15

LOCK_TRY = 'SELECT pg_try_advisory_lock(hashtext(%s))'
LOCK_UNLOCK = 'SELECT pg_advisory_unlock(hashtext(%s))'


class RecordingCursor:
    """A cursor which writes down what its session was asked.

    The lock session is a database wrapper of its own (#852), so the
    only way to read its statements is to hand the lock seam a wrapper
    whose cursors remember. Everything the real cursor can do, this can
    do; on top it appends the SQL text of every execute.
    """

    def __init__(self, inner, sink):
        self._inner = inner
        self._sink = sink

    def execute(self, sql, params=None):
        self._sink.append((sql, params))
        return self._inner.execute(sql, params)

    def __getattr__(self, name):
        return getattr(self._inner, name)

    def __enter__(self):
        self._inner.__enter__()
        return self

    def __exit__(self, *args):
        return self._inner.__exit__(*args)


class SingletonFireStatementShapeTest(TestCase):
    """What one fire of a singleton task costs on the lock session."""

    def setUp(self):
        # a celery app of its own, like the neighbour lock tests: the tasks
        # declared here must not join the registry of the project's app
        self.app = Celery('task-sql-singleton-test', set_as_current=False)
        self.addCleanup(self.app.close)
        self.app.conf.result_backend = 'cache+memory://'
        self.sink = []
        self._patch_lock_session()
        self.ran = []

    def _patch_lock_session(self):
        """Every lock seam this test opens records into ``self.sink``."""
        from extras import tasks as extras_tasks
        real = extras_tasks.singleton_connection

        def recording_connection():
            connection = real()
            inner_cursor = connection.cursor

            def cursor(*args, **kwargs):
                return RecordingCursor(inner_cursor(*args, **kwargs),
                                       self.sink)
            connection.cursor = cursor
            return connection

        patcher = patch.object(extras_tasks, 'singleton_connection',
                               recording_connection)
        patcher.start()
        self.addCleanup(patcher.stop)

    def task(self, name, body):
        return self.app.task(name=name, base=SingletonTask, bind=True)(body)

    def fire(self, task):
        """Fire like a worker: a run reports its state under an id."""
        task.push_request(id=f'fire-{uuid4()}')
        try:
            return task()
        finally:
            task.pop_request()

    def _ran_body(self, name):
        """A task which only answers that it ran.

        A NAMED nested function per the neighbour's note: celery reads the
        signature of a task's callable and a lambda will not do.
        """
        ran = self.ran

        def body(task):
            ran.append(task.name)
            return 'ran'

        return self.task(name, body)

    def _slow_task(self, name):
        """A task whose run holds the lock until the test lets it go."""
        started = threading.Event()
        release = threading.Event()
        ran = self.ran

        def body(task):
            ran.append(task.name)
            started.set()
            release.wait(TIMEOUT)
            return 'ran'

        task = self.task(name, body)
        task.started, task.release = started, release
        return task

    def test_an_acquired_fire_costs_exactly_the_lock_and_its_unlock(self):
        """Two statements, both named, nothing else, no application table.

        This is the shape EVERY scheduled task pays per fire. A drift
        table, a beat bookkeeping write or a read of the app schema
        sneaking into the lock seam shows up here before it is paid by
        every task of the deployment.
        """
        task = self._ran_body('task-sql.singleton.acquired')
        self.assertEqual(self.fire(task), 'ran')
        self.assertEqual(self.ran, [task.name])
        self.assertEqual(
            [sql for sql, _ in self.sink], [LOCK_TRY, LOCK_UNLOCK],
            msg=f'the lock session was asked {self.sink}; the acquired '
                'fire is the lock and its unlock, nothing else')
        for sql, params in self.sink:
            self.assertEqual(
                params, [singleton_lock_id(task.name)],
                'both statements ask THIS task name')

    def test_a_refused_fire_costs_one_statement_and_runs_no_body(self):
        """The skipped fire is one try and nothing after it.

        The beat fires a task whose run outlived the interval; the skip
        must stay this cheap or the long run is punished by a second
        cost on top of its own.
        """
        slow = self._slow_task('task-sql.singleton.refused')
        outcomes = []

        def fire_in_thread():
            try:
                outcomes.append(self.fire(slow))
            finally:
                from django.db import connections
                connections.close_all()

        thread = threading.Thread(target=fire_in_thread)
        thread.start()
        self.addCleanup(thread.join, TIMEOUT)
        self.assertTrue(slow.started.wait(TIMEOUT),
                        'the holding run never started')

        held_since = len(self.sink)  # the holding fire's own TRY is in
        second = self.fire(slow)
        self.assertIn('skipped', second)
        self.assertEqual(self.ran, ['task-sql.singleton.refused'],
                         'the refused fire ran the body a second time')
        self.assertEqual(
            [sql for sql, _ in self.sink[held_since:]], [LOCK_TRY],
            'the refused fire is exactly one statement on the lock session')
        slow.release.set()
        thread.join(TIMEOUT)
        self.assertEqual(outcomes, ['ran'])

    def test_five_fires_cost_ten_statements_not_a_growing_history(self):
        """Per-fire constant: the seam keeps no record of past fires.

        A singleton which writes a heartbeat or a run row per fire would
        fail here - and that row would be the first thing #1396's runtime
        telemetry would be tempted to grow.
        """
        task = self._ran_body('task-sql.singleton.five')
        for _ in range(5):
            self.fire(task)
        self.assertEqual(len(self.sink), 10,
                         msg=f'five acquired fires were answered with '
                             f'{len(self.sink)} lock statements; ten are '
                             f'the lock and unlock of each fire, nothing '
                             f'kept between them')
        self.assertEqual({sql for sql, _ in self.sink},
                         {LOCK_TRY, LOCK_UNLOCK},
                         'the lock session is asked lock statements only')
