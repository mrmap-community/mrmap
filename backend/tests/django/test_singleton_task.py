"""The singleton lock of a task belongs to its run, not to a clock (mrmap#852).

`SingletonTask` used to keep its instances apart with a cache lock whose timeout
equalled the beat interval. A run which took longer than that interval met the
next fire with a free lock and started a second concurrent run of itself, which is
how the rebuild chains of #837 stacked up. The lock is an advisory lock of one
dedicated database session now, and these tests ask exactly that:

* a fire which finds the lock taken does not run its body,
* the run which holds the lock leaves it to the fire which comes after it,
* the lock of one task does not hold another task,
* the death of the session which holds the lock is what frees it, so a killed
  worker leaves nothing behind.
"""

import threading
from uuid import uuid4

from celery import Celery
from django.conf import settings
from django.db import connection, connections
from django.test import TestCase

from extras.tasks import SingletonTask, singleton_lock, singleton_lock_id

# a test thread which does not finish within this many seconds is a broken test
# and not a task which is still running
TIMEOUT = 15


def ran_body(task):
    """The body of a task which only answers that it has run.

    A named function: celery reads the signature of a task's callable to build
    its header, and it cannot do that with a lambda.

    Args:
        task: the task which is running, because these tasks are bound

    Returns:
        str: what the fire of such a task answers
    """
    return 'ran'


class SingletonTaskTest(TestCase):
    """What a fire of a singleton task answers while another one runs."""

    def setUp(self):
        # a celery app of its own: the tasks declared here must not join the
        # registry of the project's app
        self.app = Celery('singleton-task-test', set_as_current=False)
        self.addCleanup(self.app.close)
        # a run reports its state to celery, so it needs a result backend -
        # celery's in-process one is enough for that and keeps redis out of here
        self.app.conf.result_backend = 'cache+memory://'
        self.ran = []

    def task(self, name, body):
        """One singleton task of its own, with a body of its own.

        Args:
            name: the name the task locks under
            body: the callable to run, bound like a celery task's method
        """
        return self.app.task(name=name, base=SingletonTask, bind=True)(body)

    def slow_task(self, name='singleton.test.slow'):
        """A task whose run stays inside its body until the test lets it go."""
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

    def fire(self, task):
        """Fires a task in this thread the way a worker fires it.

        A worker gives a run its id before it calls the task, and a run reports
        its state to celery under that id, so a fire without one is not a fire.

        Args:
            task: the task to run

        Returns:
            what the run of that task answers
        """
        task.push_request(id=f'fire-{uuid4()}')
        try:
            return task()
        finally:
            task.pop_request()

    def fire_in_thread(self, task):
        """Fires a task in a thread of its own, the way another worker would.

        Returns:
            tuple: the thread and the list the answer of that fire lands in
        """
        outcomes = []

        def fire():
            try:
                outcomes.append(self.fire(task))
            finally:
                # the session this thread opened with the task is not needed
                # anymore, and the test process would keep it otherwise
                connections.close_all()

        thread = threading.Thread(target=fire)
        thread.start()
        self.addCleanup(thread.join, TIMEOUT)
        return thread, outcomes

    def test_two_overlapping_fireings_result_in_exactly_one_run(self):
        """a task whose first run outlives its beat interval is not run twice:
        the second fire is skipped while the first one is still in its body"""
        task = self.slow_task()
        first, outcomes = self.fire_in_thread(task)
        self.assertTrue(task.started.wait(TIMEOUT), 'the first run never started')

        with self.assertLogs(settings.ROOT_LOGGER, level='INFO') as told:
            second = self.fire(task)

        task.release.set()
        first.join(TIMEOUT)

        self.assertEqual(self.ran, [task.name],
                         'the second fire ran the body a second time')
        self.assertEqual(outcomes, ['ran'],
                         'the first fire did not answer its body')
        self.assertIn('skipped', second,
                      'the second fire is not answered as skipped')
        self.assertIn(task.name, second,
                      'the skip does not name the task it skipped')
        self.assertIn('another instance is running', '\n'.join(told.output),
                      'the skip is not told')

    def test_a_run_leaves_the_lock_to_the_fire_which_comes_after_it(self):
        """the lock belongs to one run and not to the task: a finished run may
        not hold the next fire off"""
        task = self.task('singleton.test.twice', ran_body)

        self.assertEqual(self.fire(task), 'ran')
        self.assertEqual(self.fire(task), 'ran')

    def test_the_lock_of_one_task_does_not_hold_another_task(self):
        """a run which is slow does not stop the schedule of a different task"""
        slow = self.slow_task()
        other = self.task('singleton.test.other', ran_body)
        first, _ = self.fire_in_thread(slow)
        self.assertTrue(slow.started.wait(TIMEOUT), 'the slow run never started')

        try:
            self.assertEqual(self.fire(other), 'ran')
        finally:
            slow.release.set()
            first.join(TIMEOUT)

        self.assertEqual(self.ran, [slow.name])

    def test_the_death_of_the_run_which_holds_the_lock_frees_it(self):
        """a killed worker leaves no lock behind: the server ends the session of a
        run with the run and its lock with it, so the next fire is not locked out
        until some timeout expires"""
        name = 'singleton.test.killed'
        with self.assertLogs(settings.ROOT_LOGGER, level='WARNING') as told:
            with singleton_lock(name) as held:
                self.assertTrue(held, 'the test could not take the lock')
                self.assertFalse(
                    self.lock_is_free(name),
                    'another session can take the lock this run is holding')
                holders = self.advisory_holders()
                self.assertEqual(
                    len(holders), 1,
                    f'{holders} hold an advisory lock, expected this run alone')
                # the way a killed worker ends: the server drops the backend, and
                # with it the locks of that backend
                self.terminate(holders[0])
                # leaving the block now unlocks a session which is gone, which is
                # told and not raised: the run of the dead worker is not the
                # failure the operator has to see, a missing lock is not either

        self.assertTrue(self.lock_is_free(name),
                        'the lock of the killed run is still taken')
        task = self.task(name, ran_body)
        self.assertEqual(self.fire(task), 'ran',
                         'the fire which comes after the killed run is skipped')
        self.assertIn('could not be unlocked', '\n'.join(told.output))

    # ------------------------------------------------------------------
    # the database side of that lock
    # ------------------------------------------------------------------

    def advisory_holders(self):
        """The other sessions which hold an advisory lock in this database.

        While these tests run, the run of a singleton is the only holder, so what
        answers here is the session which holds the lock the test is about.
        """
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT pid FROM pg_locks
                WHERE locktype = 'advisory' AND pid <> pg_backend_pid()
                ORDER BY pid
                """)
            return [row[0] for row in cursor.fetchall()]

    def terminate(self, pid):
        """Asks the server to end one session, the way a dead worker ends one."""
        with connection.cursor() as cursor:
            cursor.execute('SELECT pg_terminate_backend(%s)', [pid])

    def lock_is_free(self, name):
        """Whether this session can take the advisory lock of one task name."""
        with connection.cursor() as cursor:
            cursor.execute(
                'SELECT pg_try_advisory_lock(hashtext(%s))',
                [singleton_lock_id(name)])
            free = cursor.fetchone()[0]
            if free:
                cursor.execute(
                    'SELECT pg_advisory_unlock(hashtext(%s))',
                    [singleton_lock_id(name)])
            return free
