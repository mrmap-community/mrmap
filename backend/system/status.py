"""Read Docker's recorded health; never run service probes in HTTP requests."""
import json
import time

import requests
from django.conf import settings
from django.utils import timezone

SERVICES = {'database': 'postgis', 'redis': 'redis', 'workers': 'celery-worker', 'beat': 'celery-beat'}


def container_observation(container):
    state = container['State']
    lifecycle = state.get('Status')
    health = state.get('Health', {}).get('Status')
    if lifecycle in ('exited', 'dead', 'created', 'removing'):
        status = 'down'
    elif lifecycle in ('restarting', 'paused'):
        status = 'degraded'
    elif lifecycle != 'running':
        status = 'unknown'
    else:
        status = {'healthy': 'healthy', 'unhealthy': 'degraded'}.get(health, 'unknown')
    return {
        'name': container.get('Name', '').lstrip('/'),
        'status': status,
        'detail': f'{lifecycle or "unknown"}: {health or "no healthcheck"}',
    }


def component_observation(containers):
    if not containers:
        return {'status': 'unknown', 'detail': 'No matching container found'}
    states = {container['status'] for container in containers}
    if states == {'down'}:
        status = 'down'
    elif states & {'down', 'degraded'}:
        status = 'degraded'
    elif 'unknown' in states:
        status = 'unknown'
    else:
        status = 'healthy'
    return {'status': status, 'detail': '; '.join(
        f'{container["name"]}: {container["detail"]}' for container in containers)}


def get_status_snapshot():
    project = settings.SYSTEM_STATUS_DOCKER_PROJECT
    components = {key: {'status': 'unknown', 'detail': 'Docker API unavailable'} for key in SERVICES}
    snapshot = {'id': 'current', 'observed_at': timezone.now(), 'stale': False,
                'stale_after': 45, 'components': components}
    if not project:
        snapshot['stale'] = True
        for component in components.values():
            component['detail'] = 'Docker Compose project is not configured'
        return snapshot

    deadline = time.monotonic() + 2
    with requests.Session() as session:
        session.trust_env = False

        def get(path, **kwargs):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise requests.Timeout('Docker status deadline exceeded')
            response = session.get(settings.SYSTEM_STATUS_DOCKER_URL.rstrip('/') + path,
                                   timeout=min(0.5, remaining), allow_redirects=False, **kwargs)
            response.raise_for_status()
            return response.json()

        try:
            containers = get('/containers/json', params={'all': 'true', 'filters': json.dumps({
                'label': [f'com.docker.compose.project={project}'],
            })})
            grouped = {service: [] for service in SERVICES.values()}
            for container in containers:
                labels = container.get('Labels') or {}
                service = labels.get('com.docker.compose.service')
                if (labels.get('com.docker.compose.project') != project or service not in grouped
                        or labels.get('com.docker.compose.oneoff', '').lower() == 'true'):
                    continue
                try:
                    observation = container_observation(get(f'/containers/{container["Id"]}/json'))
                except (requests.RequestException, ValueError, KeyError, TypeError):
                    observation = {'name': container['Id'][:12], 'status': 'unknown',
                                   'detail': 'Container inspection unavailable'}
                grouped[service].append(observation)
            for component, service in SERVICES.items():
                components[component] = component_observation(grouped[service])
        except (requests.RequestException, ValueError, KeyError, TypeError):
            snapshot['stale'] = True
    return snapshot
