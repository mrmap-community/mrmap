"""What the result backend owes the chords of registration and harvesting.

Since #1178 the deployment stores results in Celery's native Redis result
backend; before that, `extras.celery:RetryingCacheBackend` - a wrapper over the
cache backend of the django-celery-results package - retried transient Redis
errors on the way. These tests keep the contract that wrapper was introduced
for (#816) against the backend which replaced it, and they cover the chord
bookkeeping the native backend does in Redis itself:

* a transient Redis connection error during a result read or write is retried
  within a finite budget, and a task body which has completed is never run
  again merely because writing its result had to be retried;
* a programming error is raised at once instead of being retried;
* a chord collects its parts in Redis, counts a redelivered part once, and
  dispatches its callback exactly once over the broker;
* a failing member fails the chord instead of publishing the callback, and that
  failure is readable from Redis as the result of the callback task.

The tests run against the Redis of the stack the way the deployment runs: the
configured backend is the one under test, not a Django local-memory double.
Task and group ids are UUIDs, a published chord body is routed to a queue of
the test's own, and every key a test wrote is deleted again.
"""

from unittest.mock import patch
from uuid import uuid4

from celery import Celery, states
from celery.app.task import Context
from celery.app.trace import build_tracer
from celery.backends.redis import RedisBackend
from celery.exceptions import BackendStoreError, ChordError
from django.conf import settings
from django.test import SimpleTestCase
from redis.exceptions import ConnectionError, TimeoutError
from registry.tasks.harvest import HarvestingTask


class ResultBackendRetryTests(SimpleTestCase):
    """Transient Redis errors cost retries, never task bodies (#816).

    The budget is the one of the deployment settings: `always_retry` with a
    finite `max_retries`; the native backend decides what is transient by
    asking its connection errors, so the retry loop and its exceptions are
    exactly the ones a worker runs with.
    """

    def setUp(self):
        self.app = Celery('result-backend-test', set_as_current=False)
        self.addCleanup(self.app.close)
        self.app.conf.update(
            result_backend=settings.CELERY_RESULT_BACKEND,
            result_backend_always_retry=settings.CELERY_RESULT_BACKEND_ALWAYS_RETRY,
            result_backend_max_retries=settings.CELERY_RESULT_BACKEND_MAX_RETRIES,
            result_serializer=settings.CELERY_RESULT_SERIALIZER,
            result_extended=settings.CELERY_RESULT_EXTENDED,
            result_expires=settings.CELERY_RESULT_EXPIRES,
        )
        self.backend = self.app.backend
        # the guard against sliding back to a package-backed cache backend:
        # what the configured URL builds must be celery's own Redis backend,
        # which imports neither django-celery-results nor the Django cache
        self.assertIsInstance(self.backend, RedisBackend)
        self.task_id = str(uuid4())
        self.addCleanup(
            self.backend.delete, self.backend.get_key_for_task(self.task_id))
        sleep = patch.object(self.backend, '_sleep')
        self.sleep = sleep.start()
        self.addCleanup(sleep.stop)

    def test_successful_harvesting_task_survives_result_write_timeout(self):
        @self.app.task(base=HarvestingTask, shared=False)
        def import_record(**kwargs):
            return 'imported'

        task = import_record
        task._backend = self.backend
        store = self.backend.set
        writes = []

        def fail_first_write(*args, **kwargs):
            writes.append(args)
            if len(writes) == 1:
                raise TimeoutError('Timeout reading from socket')
            return store(*args, **kwargs)

        with patch.object(self.backend, 'set', side_effect=fail_first_write), \
                patch.object(task, 'run', wraps=task.run) as run, \
                patch.object(task, 'on_failure') as failure, \
                patch.object(self.backend, 'on_chord_part_return') as chord_part:
            trace = build_tracer(task.name, task, app=self.app)
            result = trace(self.task_id, (), {'harvesting_job_id': 7},
                           {'id': self.task_id, 'group': str(uuid4()),
                            'chord': task.s()})

        self.assertIsNone(result.info)
        run.assert_called_once_with(harvesting_job_id=7)
        failure.assert_not_called()
        chord_part.assert_called_once()
        self.assertEqual(chord_part.call_args.args[1:], (states.SUCCESS, 'imported'))
        self.assertEqual(len(writes), 2)
        self.sleep.assert_called_once()
        # the result which survived its retried write is what a consumer reads
        # back from Redis: the value of a successful task, deserialised
        meta = self.backend.get_task_meta(self.task_id)
        self.assertEqual(meta['status'], states.SUCCESS)
        self.assertEqual(meta['result'], 'imported')

    def test_transient_redis_errors_retry_result_reads_and_writes(self):
        for error in (TimeoutError, ConnectionError):
            with self.subTest(error=error):
                with patch.object(self.backend, '_store_result', side_effect=[error('offline'), None]) as store:
                    self.backend.store_result(self.task_id, 'imported', states.SUCCESS)
                self.assertEqual(store.call_count, 2)
                with patch.object(self.backend, '_get_task_meta_for', side_effect=[
                        error('offline'), {'status': states.SUCCESS}]) as read:
                    self.assertEqual(self.backend.get_task_meta(self.task_id, cache=False)['status'], states.SUCCESS)
                self.assertEqual(read.call_count, 2)

    def test_programming_errors_are_not_retried(self):
        with patch.object(self.backend, '_store_result', side_effect=ValueError('invalid result')) as store:
            with self.assertRaisesMessage(ValueError, 'invalid result'):
                self.backend.store_result(self.task_id, None, states.SUCCESS)
        store.assert_called_once()
        self.sleep.assert_not_called()

    def test_persistent_outage_has_bounded_retries(self):
        with patch.object(self.backend, '_store_result', side_effect=ConnectionError('offline')) as store:
            with self.assertRaises(BackendStoreError):
                self.backend.store_result(self.task_id, None, states.SUCCESS)
        self.assertEqual(store.call_count, settings.CELERY_RESULT_BACKEND_MAX_RETRIES + 1)
        self.assertEqual(self.sleep.call_count, settings.CELERY_RESULT_BACKEND_MAX_RETRIES)


class RedisChordTests(SimpleTestCase):
    """What a chord gets from the Redis which keeps its bookkeeping.

    The sender half of a chord publication ends in two backend calls - the
    backend learns the body and the size of the header - before it publishes
    the header messages, and every header task which a worker answers ends in
    `on_chord_part_return`. The tests make these calls the way `celery.canvas`
    and the celery tracer do, so the Redis bookkeeping, the completion
    decision and the callback publish run for real; only a worker consuming
    the published messages is not part of a unit test.
    """

    def setUp(self):
        self.app = Celery('redis-chord-test', set_as_current=False)
        self.addCleanup(self.app.close)
        self.app.conf.update(
            broker_url=settings.CELERY_BROKER_URL,
            result_backend=settings.CELERY_RESULT_BACKEND,
            result_backend_always_retry=settings.CELERY_RESULT_BACKEND_ALWAYS_RETRY,
            result_backend_max_retries=settings.CELERY_RESULT_BACKEND_MAX_RETRIES,
            result_serializer=settings.CELERY_RESULT_SERIALIZER,
            result_extended=settings.CELERY_RESULT_EXTENDED,
            result_expires=settings.CELERY_RESULT_EXPIRES,
        )
        self.backend = self.app.backend
        self.client = self.backend.client
        self.group_ids = []

        @self.app.task(name='tests.redis-chord.body', shared=False)
        def chord_body(results):
            return results

        self.chord_body = chord_body

    def tearDown(self):
        for group_id in self.group_ids:
            for key in self.client.keys(f'celery-taskset-meta-{group_id}*'):
                self.client.delete(key)
        super().tearDown()

    def begin_chord(self, size, queue):
        """The backend half of publishing a chord of `size` parts.

        Returns the group id, the id the callback answers under - a chord
        callback carries its own task id, as the harvesting code of #970 sets
        one - and the body signature whose return publishes it.
        """
        group_id = str(uuid4())
        self.group_ids.append(group_id)
        header = self.app.GroupResult(
            group_id, [self.app.AsyncResult(str(uuid4())) for _ in range(size)])
        callback_id = str(uuid4())
        body = self.chord_body.s().set(queue=queue, task_id=callback_id)
        self.backend.apply_chord((group_id, header.results), body)
        self.backend.set_chord_size(group_id, size)
        return group_id, callback_id, body

    def part_returned(self, task_id, group_id, index, body, state, result):
        """What the tracer of a worker calls after it answered one part."""
        self.backend.on_chord_part_return(
            Context(id=task_id, group=group_id, group_index=index, chord=body),
            state, result)

    def body_message(self, queue):
        """Read the one message the broker holds on `queue`.

        Through kombu, the way a worker reads it, so what comes back is the
        deserialised payload of the task publication.
        """
        with self.app.connection_for_read() as connection:
            with connection.SimpleQueue(queue, no_ack=True) as simple:
                return simple.get()

    def test_a_chord_dispatches_its_callback_exactly_once(self):
        queue = f'tests-redis-chord-{uuid4()}'
        self.addCleanup(self.client.delete, queue)
        group_id, callback_id, body = self.begin_chord(3, queue)
        self.addCleanup(self.backend.forget, callback_id)
        part_ids = [str(uuid4()) for _ in range(3)]

        self.part_returned(part_ids[0], group_id, 0, body, states.SUCCESS, 'first')
        # the same header task answered twice - a redelivery after a lost
        # worker, which the harvest's acks_late tasks really do - must not
        # count twice: the chord is not complete with one part
        self.part_returned(part_ids[0], group_id, 0, body, states.SUCCESS, 'first again')
        self.assertEqual(self.client.llen(queue), 0,
                         'a chord may not dispatch its callback before all parts returned')

        self.part_returned(part_ids[1], group_id, 1, body, states.SUCCESS, 'second')
        self.assertEqual(self.client.llen(queue), 0)

        self.part_returned(part_ids[2], group_id, 2, body, states.SUCCESS, 'third')
        self.assertEqual(self.client.llen(queue), 1,
                         'the last part must dispatch the callback exactly once')
        message = self.body_message(queue)
        # the callback goes out as the task it is, under its own id, with the
        # joined results in header order and with the single entry per part
        # which the dedup above kept. celery sends the task body as the
        # [args, kwargs, options] message its protocol defines
        args, kwargs, options = message.payload
        self.assertEqual(message.headers['task'], 'tests.redis-chord.body')
        self.assertEqual(message.properties['correlation_id'], callback_id)
        self.assertEqual(args, [['first', 'second', 'third']])
        self.assertEqual(kwargs, {})
        self.assertIsNone(options['chord'],
                          'the dispatched body is not itself under a chord')

        # a late copy of the last part which arrives after the chord cleaned
        # up after itself must not dispatch the callback a second time: with
        # the one message read off the queue, the queue must stay empty
        self.part_returned(part_ids[2], group_id, 2, body, states.SUCCESS, 'third')
        self.assertEqual(self.client.llen(queue), 0)

    def test_a_failing_member_fails_the_chord_instead_of_the_callback(self):
        queue = f'tests-redis-chord-{uuid4()}'
        self.addCleanup(self.client.delete, queue)
        group_id, callback_id, body = self.begin_chord(2, queue)
        self.addCleanup(self.backend.forget, callback_id)

        self.part_returned(str(uuid4()), group_id, 0, body, states.SUCCESS, 'ok')
        self.part_returned(str(uuid4()), group_id, 1, body, states.FAILURE,
                           ValueError('the endpoint answered garbage'))

        # the body was not published with a failed dependency in its join;
        # instead the failure is the chord's own result, readable from Redis as
        # any task result and deserialising back to its error
        self.assertEqual(self.client.llen(queue), 0,
                         'a failed member must not dispatch the callback')
        meta = self.backend.get_task_meta(callback_id)
        self.assertEqual(meta['status'], states.FAILURE)
        self.assertIsInstance(meta['result'], ChordError)
        self.assertIn('the endpoint answered garbage', str(meta['result']))
