from django.apps import AppConfig
from django.db.models.signals import post_migrate
from django.utils.translation import gettext_lazy as _

#: the name the sweep of the job history has in the schedule of beat; the
#: tests look the row up by it
BACKGROUND_PROCESS_CLEANUP_TASK_NAME = "delete old background processes"

#: the name the sweep of the resolved incidents has in the schedule of beat
#: (#1319); the tests look the row up by it
OPERATIONAL_INCIDENT_CLEANUP_TASK_NAME = "delete old operational incidents"

#: the name the operational watchdog of #1320 has in the schedule of beat;
#: the tests look the row up by it
OPERATIONAL_INCIDENT_WATCH_TASK_NAME = "watch operational incidents"


def create_background_process_cleanup_task(sender, **kwargs):
    """Creates the periodic task which keeps the job history bounded.

    Every background operation leaves a process row behind, and the history
    of the job drawer answers exactly those rows (#1208). Nothing but this
    task takes the decided ones back, so without the row the history would
    grow with every operation of the deployment. Beat reads its schedule out
    of the database, so the sweep needs a row of ``PeriodicTask`` like the
    import of the metadata files does. Keyed by its name and not by its
    schedule: a deployment which re-scheduled the row over the api keeps what
    it chose.
    """
    from django_celery_beat.models import CrontabSchedule, PeriodicTask

    # at half past the hour: a housekeeping sweep, out of the way of the five
    # minute metadata import, the hourly dump sweep at five past and the probe
    # artifact sweep at twenty past. Asked by its whole shape and not by the
    # minute alone: a deployment which schedules another task at half past
    # would otherwise make this very lookup answer two rows (#1208)
    schedule, _ = CrontabSchedule.objects.get_or_create(
        minute="30", hour="*", day_of_week="*",
        day_of_month="*", month_of_year="*")

    PeriodicTask.objects.get_or_create(
        name=BACKGROUND_PROCESS_CLEANUP_TASK_NAME,
        defaults={
            "crontab": schedule,
            "task": "notify.tasks.delete_expired_background_processes",
        }
    )


def create_operational_incident_cleanup_task(sender, **kwargs):
    """Creates the periodic task which keeps the incident history bounded.

    A resolved incident has told what it had to tell; the authoritative
    history of the reported operation stays in the job history of #1208,
    which its own sweep bounds. Without this row the incident table would
    grow with every resolved problem of the deployment. Keyed by its name
    like the sweep of the processes: a deployment which re-scheduled the
    row over the api keeps what it chose.
    """
    from django_celery_beat.models import CrontabSchedule, PeriodicTask

    # at forty past the hour: the housekeeping of the deployment is spread
    # over the hour (import every five minutes, dump at :05, probe artifacts
    # at :20, job history at :30) and this sweep takes the next free slot
    schedule, _ = CrontabSchedule.objects.get_or_create(
        minute="40", hour="*", day_of_week="*",
        day_of_month="*", month_of_year="*")

    PeriodicTask.objects.get_or_create(
        name=OPERATIONAL_INCIDENT_CLEANUP_TASK_NAME,
        defaults={
            "crontab": schedule,
            "task": "notify.tasks.delete_expired_operational_incidents",
        }
    )


def create_operational_incident_watch_task(sender, **kwargs):
    """Creates the periodic task which runs the operational watchdog (#1320).

    A stuck operation cannot report its own standing - the silent chord of
    #1038 is the pattern this watchdog exists to see - so the look must
    come from outside, on a schedule which stands beside the work. Like
    the import watchdog of #1038 it fires on an interval rather than a
    crontab slot; the grace it judges an expired retry window with is its
    own setting (`OPERATIONAL_WATCH_RETRY_GRACE_MINUTES`, comfortably
    above this interval so no fire can judge a window the next has not
    seen scheduled). Keyed by its name like every other row of beat.
    """
    from django.conf import settings
    from django_celery_beat.models import IntervalSchedule, PeriodicTask

    interval = max(1, int(getattr(
        settings, "OPERATIONAL_WATCH_INTERVAL_MINUTES", 5)))
    schedule, _ = IntervalSchedule.objects.get_or_create(
        every=interval, period=IntervalSchedule.MINUTES)

    PeriodicTask.objects.get_or_create(
        name=OPERATIONAL_INCIDENT_WATCH_TASK_NAME,
        defaults={
            "interval": schedule,
            "task": "notify.tasks.watch_operational_incidents",
        }
    )


class NotifyConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'notify'
    label = 'notify'
    verbose_name = _('Notify')

    def ready(self):
        import notify.signals  # noqa
        # the incident publishers of #1320: the celery seams connect on the
        # import (like the retry reporting of #1207 in notify.tasks), the
        # process-state receiver is wired here
        from notify.incident_reporting import register_incident_reporting
        register_incident_reporting()
        post_migrate.connect(
            create_background_process_cleanup_task,
            sender=self
        )
        post_migrate.connect(
            create_operational_incident_cleanup_task,
            sender=self
        )
        post_migrate.connect(
            create_operational_incident_watch_task,
            sender=self
        )
