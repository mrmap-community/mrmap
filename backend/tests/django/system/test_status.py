from unittest.mock import MagicMock, patch

import requests
from django.contrib.auth.models import User
from django.test import SimpleTestCase, override_settings
from rest_framework.test import APIClient

from system.status import component_observation, container_observation, get_status_snapshot


def listed(service='celery-worker', project='test', oneoff='False', identifier='a' * 64):
    return {'Id': identifier, 'Labels': {'com.docker.compose.project': project,
            'com.docker.compose.service': service, 'com.docker.compose.oneoff': oneoff}}


def inspected(state='running', health='healthy'):
    return {'Name': '/worker', 'State': {'Status': state, 'Health': {'Status': health}}}


@override_settings(ROOT_URLCONF='system.urls', SYSTEM_STATUS_DOCKER_PROJECT='test',
                   SYSTEM_STATUS_DOCKER_URL='http://docker-api:2375')
class StatusTests(SimpleTestCase):
    def test_health_and_lifecycle_mapping(self):
        for state, health, expected in [('running', 'healthy', 'healthy'),
                                       ('running', 'unhealthy', 'degraded'),
                                       ('running', 'starting', 'unknown'),
                                       ('running', None, 'unknown'),
                                       ('exited', 'healthy', 'down'),
                                       ('restarting', 'healthy', 'degraded'),
                                       ('paused', 'healthy', 'degraded')]:
            with self.subTest(state=state, health=health):
                self.assertEqual(container_observation(inspected(state, health))['status'], expected)

    def test_replica_aggregation(self):
        for states, expected in [([], 'unknown'), (['healthy', 'healthy'], 'healthy'),
                                 (['healthy', 'down'], 'degraded'), (['down', 'down'], 'down'),
                                 (['healthy', 'unknown'], 'unknown')]:
            with self.subTest(states=states):
                observations = [{'name': str(i), 'status': state, 'detail': state}
                                for i, state in enumerate(states)]
                self.assertEqual(component_observation(observations)['status'], expected)

    def test_only_project_services_are_inspected(self):
        with patch('system.status.requests.Session') as session:
            client = session.return_value.__enter__.return_value
            client.get.return_value.json.side_effect = [
                [listed(), listed(project='other'), listed(oneoff='True'), listed(service='backend')],
                inspected(),
            ]
            snapshot = get_status_snapshot()
        self.assertEqual(client.get.call_count, 2)
        self.assertEqual(snapshot['components']['workers']['status'], 'healthy')
        self.assertEqual(snapshot['components']['database']['status'], 'unknown')
        self.assertFalse(snapshot['stale'])
        self.assertFalse(client.trust_env)
        self.assertEqual(client.get.call_args_list[0].kwargs['params']['all'], 'true')
        self.assertNotIn('tasks', snapshot)

    def test_inspect_failure_does_not_hide_other_services(self):
        with patch('system.status.requests.Session') as session:
            client = session.return_value.__enter__.return_value
            listing, healthy = MagicMock(), MagicMock()
            listing.json.return_value = [listed(), listed(service='redis', identifier='b' * 64)]
            healthy.json.return_value = inspected()
            client.get.side_effect = [listing, requests.Timeout(), healthy]
            snapshot = get_status_snapshot()
        self.assertEqual(snapshot['components']['workers']['status'], 'unknown')
        self.assertEqual(snapshot['components']['redis']['status'], 'healthy')

    def test_docker_failure_reports_unknown(self):
        with patch('system.status.requests.Session') as session:
            session.return_value.__enter__.return_value.get.side_effect = requests.ConnectionError()
            snapshot = get_status_snapshot()
        self.assertTrue(snapshot['stale'])
        self.assertTrue(all(item['status'] == 'unknown' for item in snapshot['components'].values()))

    def test_deadline_prevents_further_inspections(self):
        with patch('system.status.requests.Session') as session:
            client = session.return_value.__enter__.return_value
            client.get.return_value.json.return_value = [listed()]
            with patch('system.status.time.monotonic', side_effect=[0, 0, 3]):
                snapshot = get_status_snapshot()
        client.get.assert_called_once()
        self.assertEqual(snapshot['components']['workers']['status'], 'unknown')

    @override_settings(SYSTEM_STATUS_DOCKER_PROJECT='')
    def test_unconfigured_project_does_not_query_all_containers(self):
        with patch('system.status.requests.Session') as session:
            self.assertTrue(get_status_snapshot()['stale'])
            session.assert_not_called()

    def test_endpoint_requires_staff(self):
        client = APIClient()
        self.assertIn(client.get('/status/current').status_code, (401, 403))
        client.force_authenticate(User(username='reader', is_staff=False))
        self.assertEqual(client.get('/status/current').status_code, 403)

    def test_jsonapi_contains_only_component_observations(self):
        client = APIClient()
        client.force_authenticate(User(username='admin', is_staff=True))
        with patch('system.status.requests.Session') as session:
            session.return_value.__enter__.return_value.get.return_value.json.return_value = []
            response = client.get('/status/current')
        self.assertEqual(response.status_code, 200)
        data = response.json()['data']
        self.assertEqual((data['type'], data['id']), ('SystemStatus', 'current'))
        self.assertEqual(set(data['attributes']), {'observedAt', 'stale', 'staleAfter', 'components'})
        self.assertEqual(client.post('/status/current', {}).status_code, 405)


class BeatHealthTests(SimpleTestCase):
    def test_successful_tick_updates_heartbeat(self):
        from system.scheduler import HealthcheckScheduler
        with patch('system.scheduler.DatabaseScheduler.tick', return_value=5), patch('system.scheduler.HEARTBEAT') as heartbeat:
            self.assertEqual(HealthcheckScheduler.tick(HealthcheckScheduler.__new__(HealthcheckScheduler)), 5)
            heartbeat.touch.assert_called_once()

    def test_failed_tick_does_not_update_heartbeat(self):
        from system.scheduler import HealthcheckScheduler
        with patch('system.scheduler.DatabaseScheduler.tick', side_effect=RuntimeError), patch('system.scheduler.HEARTBEAT') as heartbeat:
            with self.assertRaises(RuntimeError):
                HealthcheckScheduler.tick(HealthcheckScheduler.__new__(HealthcheckScheduler))
            heartbeat.touch.assert_not_called()


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
