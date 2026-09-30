from datetime import timedelta
from threading import Event, Thread
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import SimpleTestCase
from django.utils import timezone
from rest_framework.test import APIClient

from system.status import StatusSnapshotCache, status_snapshot


def report():
    return {
        'observed_at': timezone.now().isoformat(), 'tasks': [],
        'checks': {'database': {'status': 'OK'}, 'redis': {'status': 'OK'},
                   'beat': {'status': 'OK', 'detail': 'Beat connected to PostgreSQL (1 sessions)'},
                   'workers': {'status': 'OK', 'responding': ['worker'], 'missing_queues': []},
                   'schedules': {'status': 'OK'}},
    }


class StatusApiTests(SimpleTestCase):
    def test_endpoint_requires_staff(self):
        client = APIClient()
        self.assertIn(client.get('/status/current').status_code, (401, 403))
        client.force_authenticate(User(username='reader', is_staff=False))
        self.assertEqual(client.get('/status/current').status_code, 403)

    def test_jsonapi_shape_and_connected_beat(self):
        client = APIClient()
        client.force_authenticate(User(username='admin', is_staff=True))
        with patch('system.views.get_status_snapshot', return_value=status_snapshot(report())):
            response = client.get('/status/current')
        self.assertEqual(response.status_code, 200)
        data = response.json()['data']
        self.assertEqual((data['type'], data['id']), ('SystemStatus', 'current'))
        self.assertIn('observedAt', data['attributes'])
        self.assertEqual(data['attributes']['components']['beat']['status'], 'connected')
        self.assertEqual(client.post('/status/current', {}).status_code, 405)

    def test_schedule_table_is_bounded_without_losing_counts(self):
        current = report()
        current['tasks'] = [{'name': str(i), 'status': 'SCHEDULED'} for i in range(201)]
        current['tasks'].append({'name': 'overdue', 'status': 'OVERDUE'})
        snapshot = status_snapshot(current)
        self.assertEqual(len(snapshot['tasks']), 200)
        self.assertEqual(snapshot['task_total'], 202)
        self.assertEqual(snapshot['tasks'][0]['name'], 'overdue')
        self.assertEqual(sum(snapshot['task_counts'].values()), 202)


class SystemInfoTests(SimpleTestCase):
    def test_database_metadata_uses_one_query(self):
        from system.views import SystemView

        with patch('system.views.connection') as connection:
            cursor = connection.cursor.return_value.__enter__.return_value
            cursor.fetchone.return_value = ('PostgreSQL 16 (test build)', 'mrmap', '42 MB')
            result = SystemView().get_object()
        cursor.execute.assert_called_once_with(
            'SELECT version(), current_database(), '
            'pg_size_pretty(pg_database_size(current_database()))')
        self.assertEqual(result['postgresql_version'], 'PostgreSQL 16')
        self.assertEqual(result['database_name'], 'mrmap')
        self.assertEqual(result['database_size'], '42 MB')


class LocalStatusTests(SimpleTestCase):
    def test_cold_requests_return_without_waiting_and_share_one_refresh(self):
        cache = StatusSnapshotCache()
        entered, release = Event(), Event()
        def probe(**kwargs):
            entered.set()
            if not release.wait(5):
                raise RuntimeError('Test timed out')
            return report()

        threads = []
        def start_thread(**kwargs):
            thread = Thread(**kwargs)
            threads.append(thread)
            return thread

        with patch('system.status.collect_status', side_effect=probe) as collect:
            with patch('system.status.threading.Thread', side_effect=start_thread):
                try:
                    self.assertTrue(cache.get()['stale'])
                    self.assertTrue(entered.wait(2))
                    for _ in range(10):
                        self.assertFalse(cache.get()['tasks_available'])
                    collect.assert_called_once_with(timeout=2)
                finally:
                    release.set()
                    for thread in threads:
                        thread.join(5)
                        self.assertFalse(thread.is_alive())
            self.assertFalse(cache.get()['stale'])
            self.assertTrue(cache.get()['tasks_available'])
            collect.assert_called_once()

    def test_fresh_snapshot_needs_no_external_cache_or_new_probe(self):
        cache = StatusSnapshotCache()
        with patch('system.status.collect_status', return_value=report()):
            cache._refresh()
        cache._next_refresh = float('inf')
        with patch('redis.Redis.from_url', side_effect=AssertionError('External cache accessed')):
            with patch('system.status.collect_status') as collect:
                snapshot = cache.get()
                self.assertFalse(snapshot['stale'])
                snapshot['components']['database']['status'] = 'changed by caller'
                self.assertEqual(cache.get()['components']['database']['status'], 'healthy')
                collect.assert_not_called()

    def test_refresh_returns_old_observations_and_marks_age(self):
        for age, stale in ((20, False), (60, True)):
            with self.subTest(age=age):
                cache = StatusSnapshotCache()
                old = report()
                old['observed_at'] = (timezone.now() - timedelta(seconds=age)).isoformat()
                with patch('system.status.collect_status', return_value=old):
                    cache._refresh()
                with patch('system.status.threading.Thread') as thread:
                    snapshot = cache.get()
                    self.assertEqual(snapshot['observed_at'], old['observed_at'])
                    self.assertEqual(snapshot['stale'], stale)
                    cache.get()
                    thread.return_value.start.assert_called_once()

    def test_failure_preserves_observations_and_allows_retry(self):
        cache = StatusSnapshotCache()
        with patch('system.status.collect_status', return_value=report()):
            cache._refresh()
        observed = cache._snapshot['observed_at']
        with patch('system.status.collect_status', side_effect=RuntimeError):
            with self.assertLogs('system.status', level='ERROR'):
                cache._refresh()
        self.assertFalse(cache._refreshing)
        self.assertEqual(cache._snapshot['observed_at'], observed)
        with patch('system.status.threading.Thread') as thread:
            cache.get()
            thread.return_value.start.assert_called_once()

    def test_thread_start_failure_does_not_block_future_refreshes(self):
        cache = StatusSnapshotCache()
        with patch('system.status.threading.Thread') as thread:
            thread.return_value.start.side_effect = RuntimeError
            with self.assertLogs('system.status', level='ERROR'):
                self.assertTrue(cache.get()['stale'])
        self.assertFalse(cache._refreshing)
        with patch('system.status.time.monotonic', return_value=cache._next_refresh + 1):
            with patch('system.status.threading.Thread') as thread:
                cache.get()
                thread.return_value.start.assert_called_once()

    def test_reset_clears_inherited_refresh_state(self):
        cache = StatusSnapshotCache()
        cache._refreshing = True
        cache._next_refresh = float('inf')
        cache.reset()
        with patch('system.status.threading.Thread') as thread:
            self.assertTrue(cache.get()['stale'])
            thread.return_value.start.assert_called_once()
