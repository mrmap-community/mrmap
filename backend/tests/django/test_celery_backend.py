from unittest.mock import patch
from uuid import uuid4

from celery import Celery, states
from celery.app.trace import build_tracer
from celery.exceptions import BackendStoreError
from django.conf import settings
from django.test import SimpleTestCase
from redis.exceptions import ConnectionError, TimeoutError
from registry.tasks.harvest import HarvestingTask


class ResultBackendRetryTests(SimpleTestCase):
    def setUp(self):
        self.app = Celery('result-backend-test', set_as_current=False)
        self.addCleanup(self.app.close)
        self.app.conf.update(
            result_backend=settings.CELERY_RESULT_BACKEND,
            result_backend_always_retry=settings.CELERY_RESULT_BACKEND_ALWAYS_RETRY,
            result_backend_max_retries=settings.CELERY_RESULT_BACKEND_MAX_RETRIES,
            cache_backend='local-memory',
        )
        self.backend = self.app.backend
        self.task_id = str(uuid4())
        sleep = patch.object(self.backend, '_sleep')
        self.sleep = sleep.start()
        self.addCleanup(sleep.stop)

    def test_successful_harvesting_task_survives_result_write_timeout(self):
        @self.app.task(base=HarvestingTask, shared=False)
        def import_record(**kwargs):
            return 'imported'

        task = import_record
        task._backend = self.backend
        cache = self.backend.cache_backend
        store = cache.set
        writes = []

        def fail_first_write(*args, **kwargs):
            writes.append(args)
            if len(writes) == 1:
                raise TimeoutError('Timeout reading from socket')
            return store(*args, **kwargs)

        with patch.object(cache, 'set', side_effect=fail_first_write), \
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
        self.assertEqual(self.backend.get_task_meta(self.task_id)['status'], states.SUCCESS)

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
