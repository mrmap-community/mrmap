"""System probes and cached observations for the JSON:API status view."""
import logging
import os
import threading
import time
from copy import deepcopy
from datetime import timedelta

QUEUES = {'default', 'download', 'db-routines', 'monitoring', 'update'}


def next_expected(task):
    if not task.enabled or (task.one_off and task.total_run_count):
        return None
    baseline = task.last_run_at or task.date_changed
    if task.clocked_id:
        expected = task.clocked.clocked_time
    elif task.crontab_id:
        from extras.scheduling import next_run_expected_at
        expected = next_run_expected_at(task)
    elif task.interval_id and baseline:
        expected = baseline + task.interval.schedule.run_every
        if task.start_time:
            expected = max(expected, task.start_time)
    elif task.solar_id and baseline:
        schedule = task.solar.schedule
        schedule.nowfun = lambda: baseline
        expected = baseline + schedule.remaining_estimate(baseline)
    else:
        return None
    return None if task.expires and expected and expected >= task.expires else expected


def schedule_status(task, now, grace):
    expected = next_expected(task)
    if not task.enabled:
        status = 'DISABLED'
    elif task.one_off and task.total_run_count:
        status = 'ONE_OFF_DISPATCHED'
    elif task.expires and now >= task.expires:
        status = 'EXPIRED'
    elif expected and now > expected + timedelta(seconds=grace):
        status = 'OVERDUE'
    elif task.last_run_at is None:
        status = 'NEVER_DISPATCHED'
    else:
        status = 'SCHEDULED' if expected else 'UNKNOWN'
    return {
        'name': task.name, 'status': status,
        'last_scheduled_at': task.last_run_at.isoformat() if task.last_run_at else None,
        'next_expected_at': expected.isoformat() if expected else None,
        'schedule_count': task.total_run_count,
    }


def beat_status(connection, application_name="mrmap-celery-beat"):
    """Presence of Beat's DB session, independent of how often tasks are due."""
    if connection.vendor != 'postgresql':
        return {'status': 'UNKNOWN', 'detail': 'Beat connection detection requires PostgreSQL'}
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT count(*) FROM pg_stat_activity "
                "WHERE datname = current_database() AND application_name = %s "
                "AND pid <> pg_backend_pid()",
                [application_name],
            )
            sessions = cursor.fetchone()[0]
        return {
            'status': 'OK' if sessions else 'WARNING',
            'detail': (f'Beat connected to PostgreSQL ({sessions} sessions)'
                       if sessions else 'No labeled Beat database session detected'),
            'sessions': sessions,
        }
    except Exception as exc:
        return {'status': 'UNKNOWN', 'detail': f'Beat connection check failed: {type(exc).__name__}'}


def collect_status(timeout=3, grace=300):
    """Read-only probes; no scheduler instrumentation or execution history."""
    from django.conf import settings
    from django.db import connections
    from django.utils import timezone
    from django_celery_beat.models import PeriodicTask
    from MrMap.celery import app
    from redis import Redis
    from redis.backoff import NoBackoff
    from redis.retry import Retry

    result = {'observed_at': timezone.now().isoformat(), 'checks': {}, 'tasks': []}
    checks = result['checks']
    # Use a private, unpooled connection so web requests keep their normal settings.
    connection = connections['default'].copy(alias='system-status-probe')
    connection.settings_dict = deepcopy(connection.settings_dict)
    if connection.vendor == 'postgresql':
        connection.settings_dict['OPTIONS'] = {
            'connect_timeout': timeout, 'options': f'-c statement_timeout={timeout * 1000}',
            'application_name': 'mrmap-system-status',
        }
    connections['system-status-probe'] = connection
    try:
        try:
            with connection.cursor() as cursor:
                cursor.execute('SELECT 1')
                cursor.fetchone()
            checks['database'] = {'status': 'OK'}
        except Exception as exc:
            checks['database'] = {'status': 'UNKNOWN', 'detail': type(exc).__name__}
        checks['beat'] = (beat_status(connection, getattr(settings, 'SYSTEM_STATUS_BEAT_APPLICATION_NAME', 'mrmap-celery-beat'))
                          if checks['database']['status'] == 'OK' else
                          {'status': 'UNKNOWN', 'detail': 'Database unavailable'})
        try:
            with Redis.from_url(settings.CELERY_BROKER_URL, socket_timeout=timeout,
                                socket_connect_timeout=timeout, retry=Retry(NoBackoff(), 0)) as client:
                client.ping()
            checks['redis'] = {'status': 'OK'}
        except Exception as exc:
            checks['redis'] = {'status': 'UNKNOWN', 'detail': type(exc).__name__}
        try:
            with app.connection_for_read(connect_timeout=timeout, transport_options={
                'socket_timeout': timeout, 'socket_connect_timeout': timeout,
                'retry_policy': {'max_retries': 0},
            }) as broker:
                broker.ensure_connection(max_retries=0)
                inspector = app.control.inspect(timeout=timeout, connection=broker)
                workers = inspector.active_queues() or {}
                queues = {queue['name'] for worker in workers.values() for queue in worker}
                missing = sorted(QUEUES - queues)
                checks['workers'] = {
                    'status': 'OK' if workers and not missing else 'WARNING',
                    'responding': sorted(workers), 'missing_queues': missing,
                    'detail': f'{len(workers)} workers responding',
                }
        except Exception as exc:
            checks['workers'] = {'status': 'UNKNOWN', 'detail': type(exc).__name__}
        if checks['database']['status'] == 'OK':
            try:
                tasks = PeriodicTask.objects.using('system-status-probe').select_related('crontab', 'interval', 'clocked', 'solar').order_by('name')
                now = timezone.now()
                for task in tasks:
                    try:
                        result['tasks'].append(schedule_status(task, now, grace))
                    except Exception as exc:
                        result['tasks'].append({'name': task.name, 'status': 'UNKNOWN', 'detail': type(exc).__name__})
                overdue = sum(task['status'] == 'OVERDUE' for task in result['tasks'])
                unknown = sum(task['status'] == 'UNKNOWN' for task in result['tasks'])
                checks['schedules'] = {
                    'status': 'WARNING' if overdue or unknown else 'OK',
                    'detail': f'{len(result["tasks"])} schedules; {overdue} overdue; {unknown} unknown',
                }
            except Exception as exc:
                checks['schedules'] = {'status': 'UNKNOWN', 'detail': type(exc).__name__}
        else:
            checks['schedules'] = {'status': 'UNKNOWN', 'detail': 'Database unavailable'}
        return result
    finally:
        try:
            connection.close()
        finally:
            del connections['system-status-probe']


def status_snapshot(report):
    """Adapt probe observations for the dashboard without claiming task success."""
    checks = report['checks']
    components = {
        name: {
            'status': {'OK': 'healthy', 'WARNING': 'degraded'}.get(check['status'], 'unknown'),
            'detail': check.get('detail', check['status']),
            **({'workers': check['responding'], 'missing_queues': check['missing_queues']}
               if 'responding' in check else {}),
        }
        for name, check in checks.items() if name != 'schedules'
    }
    if components.get('workers', {}).get('missing_queues'):
        components['workers']['detail'] += '; no responding consumer for ' + ', '.join(components['workers']['missing_queues'])
    if 'beat' in checks:
        components['beat']['status'] = {'OK': 'connected', 'WARNING': 'disconnected'}.get(checks['beat']['status'], 'unknown')
    else:
        components['beat'] = {'status': 'unknown', 'detail': 'Beat connection was not checked'}
    states = {'OVERDUE': 'overdue', 'DISABLED': 'disabled', 'EXPIRED': 'expired',
              'SCHEDULED': 'scheduled', 'NEVER_DISPATCHED': 'neverDispatched',
              'ONE_OFF_DISPATCHED': 'oneOffDispatched', 'UNKNOWN': 'unknown'}
    tasks = []
    counts = {}
    for task in report['tasks']:
        state = states[task['status']]
        counts[state] = counts.get(state, 0) + 1
        tasks.append({
            **task, 'id': task['name'], 'status': state,
            'detail': task.get('detail', ''),
        })
    tasks.sort(key=lambda task: (task['status'] not in ('overdue', 'unknown'), task['name']))
    return {
        'id': 'current', 'observed_at': report['observed_at'], 'stale': False,
        'stale_after': 45, 'components': components, 'tasks': tasks[:200],
        'task_counts': counts, 'task_total': len(tasks),
        'tasks_available': checks['schedules']['status'] != 'UNKNOWN',
    }


def unavailable_snapshot(detail):
    from django.utils import timezone

    snapshot = status_snapshot({
        'observed_at': timezone.now().isoformat(), 'tasks': [],
        'checks': {name: {'status': 'UNKNOWN', 'detail': detail}
                   for name in ('database', 'redis', 'workers', 'beat', 'schedules')},
    })
    snapshot['stale'] = True
    return snapshot


class StatusSnapshotCache:
    """Request-driven refresh in this backend process, with no external storage."""

    def __init__(self):
        self.reset()

    def reset(self):
        # Forked web workers must not inherit another process's lock or thread state.
        self._lock = threading.Lock()
        self._snapshot = None
        self._refreshing = False
        self._next_refresh = 0

    def get(self):
        from django.utils import timezone
        from django.utils.dateparse import parse_datetime

        with self._lock:
            if not self._refreshing and time.monotonic() >= self._next_refresh:
                self._refreshing = True
                self._next_refresh = time.monotonic() + 15
                try:
                    threading.Thread(target=self._refresh, name='system-status', daemon=True).start()
                except Exception:
                    self._refreshing = False
                    logging.getLogger(__name__).exception('Could not start status collection')
            snapshot = deepcopy(self._snapshot)
        if snapshot is None:
            return unavailable_snapshot('Waiting for backend status collection')
        age = (timezone.now() - parse_datetime(snapshot['observed_at'])).total_seconds()
        snapshot['stale'] = age >= snapshot['stale_after']
        return snapshot

    def _refresh(self):
        try:
            snapshot = status_snapshot(collect_status(timeout=2))
            with self._lock:
                self._snapshot = snapshot
        except Exception:
            logging.getLogger(__name__).exception('Status collection failed; retaining previous observations')
        finally:
            with self._lock:
                self._refreshing = False


_snapshots = StatusSnapshotCache()
if hasattr(os, 'register_at_fork'):
    os.register_at_fork(after_in_child=_snapshots.reset)


def get_status_snapshot():
    return _snapshots.get()
