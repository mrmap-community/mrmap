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
taken is skipped - the state which it missed is answered by the next beat fire
at the latest.
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
