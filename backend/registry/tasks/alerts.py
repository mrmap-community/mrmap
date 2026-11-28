"""The refresh which keeps the rows of the alerts current.

The states of the services which need attention are derived from the runs and
jobs behind them and stored as the rows of the alerts, so that the api of the
attention answers one bounded query instead of re-evaluating the whole
derivation on every read (#1030). Two things run this refresh:

- beat, on the interval which the schedule of the deployment gives it -
  created on migrate, see `registry.apps.create_service_alert_refresh_task`;
  the interval also answers the schedules which become overdue by the clock
  alone, which is what the polling fallback of the header did before, and
- the invalidations which the states of the services publish
  (`notify.utils.invalidate_service_alerts`), so that an alert which appears
  or disappears is answered shortly after its commit instead of after the
  next beat fire.

It runs as a singleton on the ``db-routines`` queue: two refreshes over one
state have nothing to add to each other, and the one which finds the lock
taken is skipped.

What "skipped" costs is stated here rather than promised away (#1827): the
state a dropped fire missed is answered by the next fire which actually RUNS.
On a deployment which meets its schedule that is the next beat fire, one
interval later. On one which does not - a rewrite which needs longer than the
interval it is scheduled with, the size-dependent case of #1827 - every second
beat fire meets the lock too, so the answer arrives one interval plus one run
duration later and the rows are current at half the configured cadence. That
condition is no longer invisible: a fire dropped by the lock is recorded as its
own attempt outcome (#1330), the capacity snapshot of #1326 answers the dropped
share per schedule under ``reachability``, and the detector of #1390 publishes
an incident when a beat schedule's measured p95 costs more than its interval.
"""

from logging import Logger

from celery import shared_task
from django.conf import settings

from extras.tasks import SingletonTask
from MrMap import celery_queues

logger: Logger = settings.ROOT_LOGGER


@shared_task(queue=celery_queues.DB_ROUTINES, bind=True, base=SingletonTask)
def refresh_service_alerts(self, *args, **kwargs):
    """Rewrite the rows of the alerts from the states of the services."""
    from registry.querys.alerts import refresh_service_alerts as project

    rows = project()
    logger.info(f"refreshed the rows of the alerts: {rows} rows")
    return rows
