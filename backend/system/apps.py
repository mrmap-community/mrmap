
from django.apps import AppConfig
from django.db.models.signals import post_migrate
from django.utils.translation import gettext_lazy as _

#: the name the sweep of the slow request dumps has in the schedule of beat; the
#: tests look the row up by it
SLOW_REQUEST_DUMP_CLEANUP_TASK_NAME = "delete old slow request dumps"

#: the name the bounding sweep of the #1330 attempt samples has in the schedule
#: of beat; the tests look the row up by it
TASK_ATTEMPT_BOUNDING_TASK_NAME = "bound celery task attempt samples"

#: the name the capacity snapshot refresh of #1326 has in the schedule of
#: beat; the tests look the row up by it
CAPACITY_SNAPSHOT_REFRESH_TASK_NAME = "refresh capacity snapshot"

#: the name the task-performance exporter of #1391 has in the schedule of
#: beat; the tests look the row up by it
TASK_PERFORMANCE_EXPORT_TASK_NAME = "publish celery task performance"

#: the name the slow-task detector of #1390 has in the schedule of beat; the
#: tests look the row up by it
TASK_PERFORMANCE_DETECTION_TASK_NAME = "detect task performance"


def create_slow_request_dump_cleanup_task(sender, **kwargs):
    """Creates the periodic task which keeps the slow request dumps bounded.

    Beat reads its schedule out of the database, so a task which shall run on its
    own has to exist as a row of ``PeriodicTask``, like the import of the metadata
    files does (#888). Keyed by its name and not by its schedule: a deployment which
    re-scheduled the row over the api keeps what it chose, while a ``get_or_create``
    over the crontab would answer a conflicting insert for the unique name.
    """
    from django_celery_beat.models import CrontabSchedule, PeriodicTask

    # at five past the hour, out of the way of the five minute metadata
    # import. Asked by its whole shape and not by the minute alone: the
    # staggered per-service schedules (system/fields.py) legitimately hold
    # rows at five past with any hour, and the bare minute lookup answered
    # them all -- the migrate died on MultipleObjectsReturned (#1273)
    schedule, _ = CrontabSchedule.objects.get_or_create(
        minute="5", hour="*", day_of_week="*",
        day_of_month="*", month_of_year="*")

    PeriodicTask.objects.get_or_create(
        name=SLOW_REQUEST_DUMP_CLEANUP_TASK_NAME,
        defaults={
            "crontab": schedule,
            "task": "system.tasks.delete_old_slow_request_dumps",
        }
    )


def create_task_attempt_bounding_task(sender, **kwargs):
    """Creates the periodic task which keeps the #1330 attempt samples bounded.

    The attempt rows are the measurement source of the capacity snapshots,
    and rows of an abandoned attempt are of use only until the grace declared
    them uncertain: retention and the row cap of ``system.tasks`` take them
    back. Like every other beat schedule of this deployment the row lives in
    the database, keyed by its name.
    """
    from django_celery_beat.models import CrontabSchedule, PeriodicTask

    # at ten to the hour: the housekeeping of the deployment is spread over
    # the hour (import every five minutes, dump at :05, probe artifacts at
    # :20, job history at :30, incidents at :40) and this sweep takes the
    # next free slot
    schedule, _ = CrontabSchedule.objects.get_or_create(
        minute="50", hour="*", day_of_week="*",
        day_of_month="*", month_of_year="*")

    PeriodicTask.objects.get_or_create(
        name=TASK_ATTEMPT_BOUNDING_TASK_NAME,
        defaults={
            "crontab": schedule,
            "task": "system.tasks.bound_task_attempt_samples",
        }
    )


def create_capacity_snapshot_refresh_task(sender, **kwargs):
    """Creates the periodic task which keeps the #1326 snapshot materialized.

    The endpoint is a cache read by contract; the walk of the schedules it
    serves is beat's work, not an administrator's request. Twice an hour
    bounds the age of what a deployment can be told, and the row is cheap
    to skip: ``refresh`` answers "unchanged" when the TTL has not expired
    and the schedule fingerprint has not moved. Like every other beat
    schedule of this deployment the row lives in the database, keyed by its
    name - a deployment which re-scheduled it over the api keeps its choice.
    """
    from django_celery_beat.models import CrontabSchedule, PeriodicTask

    # every quarter of an hour, offset from the :00 import beat and the
    # other housekeeping rows (dump at :05, probe artifacts at :20, job
    # history at :30, incidents at :40, attempt bounding at :50): the
    # cadence must stay below ``CAPACITY_SNAPSHOT_TTL_SECONDS`` or the
    # snapshot would age past its own freshness promise between refreshes
    schedule, _ = CrontabSchedule.objects.get_or_create(
        minute="13,28,43,58", hour="*", day_of_week="*",
        day_of_month="*", month_of_year="*")

    PeriodicTask.objects.get_or_create(
        name=CAPACITY_SNAPSHOT_REFRESH_TASK_NAME,
        defaults={
            "crontab": schedule,
            "task": "system.tasks.refresh_capacity_snapshot",
        }
    )


def _export_schedule_fields(cadence_minutes):
    """The crontab fields for one fire every ``cadence_minutes`` minutes.

    :02 keeps the offset from the metadata import at :00 and from the other
    housekeeping rows of this app (:05 dumps, :13 snapshots, :20 probe
    artifacts, :30 job history, :40 incidents, :50 bounding). A cadence which
    does not divide the hour fires as often as a crontab can express it - a
    seven minute cadence gives :02 :09 ... :58 - and a cadence of whole hours
    steps the hour field instead.
    """
    cadence = max(1, int(cadence_minutes))
    if cadence % 60 == 0:
        hours = max(1, cadence // 60)
        return "2", "*" if hours == 1 else "*/%d" % hours
    minutes = list(range(2 % cadence, 60, cadence))
    return (",".join(str(minute) for minute in minutes)
            if len(minutes) < 60 else "*"), "*"


def create_task_performance_export_task(sender, **kwargs):
    """Creates the periodic task which publishes the #1391 performance series.

    The dashboard of #1391 reads a log store; the row below is what writes it.
    Unlike every other beat row of this app it is created only while
    ``TASK_PERFORMANCE_EXPORT_ENABLED`` is on, and removed while it is off:
    the export is off by default, and a deployment which never installed the
    dashboard should not pay a beat fire every window to discover that. The
    row is keyed by its own name, so an operator who re-scheduled it over the
    api keeps the cadence they chose for as long as the mode stays on.
    """
    from django.conf import settings
    from django_celery_beat.models import CrontabSchedule, PeriodicTask

    if not getattr(settings, "TASK_PERFORMANCE_EXPORT_ENABLED", False):
        # only this function's own row is touched; a row the operator renamed
        # is theirs and stays
        PeriodicTask.objects.filter(
            name=TASK_PERFORMANCE_EXPORT_TASK_NAME).delete()
        return

    # one fire per exported window: the cadence IS
    # MRMAP_TASK_PERFORMANCE_EXPORT_WINDOW_MINUTES, so the knob which names
    # the span of a window also moves the row which produces it. The
    # exporter's window continues where the last one ended, so a fire which is
    # late widens the next window instead of shifting or double counting it.
    minute, hour = _export_schedule_fields(
        getattr(settings, "TASK_PERFORMANCE_EXPORT_WINDOW_MINUTES", 5))
    schedule, _ = CrontabSchedule.objects.get_or_create(
        minute=minute, hour=hour, day_of_week="*",
        day_of_month="*", month_of_year="*")

    PeriodicTask.objects.get_or_create(
        name=TASK_PERFORMANCE_EXPORT_TASK_NAME,
        defaults={
            "crontab": schedule,
            "task": "system.tasks.publish_task_performance",
        }
    )


def create_task_performance_detection_task(sender, **kwargs):
    """Creates the periodic task which looks for slow tasks (#1390).

    Slow execution must be detectable before a user complains about it, and
    the look must not be per task or per request - so it is a scheduled fire
    over the attempt samples of #1330, beside the watchdog of #1320 which
    asks a different question (standing vs slow). Like the watchdog it fires
    on an interval rather than a crontab slot, because the budgets it judges
    are shorter than an hour; the row is keyed by its name, so a deployment
    which re-scheduled it over the api keeps its choice.

    The switch of the work itself is the setting ``TASK_PERFORMANCE_ENABLED``
    - the row stays created when detection is off, so a deployment can enable
    detection by environment alone, without a migrate.
    """
    from django.conf import settings
    from django_celery_beat.models import IntervalSchedule, PeriodicTask

    interval = max(1, int(getattr(
        settings, "TASK_PERFORMANCE_INTERVAL_MINUTES", 15)))
    schedule, _ = IntervalSchedule.objects.get_or_create(
        every=interval, period=IntervalSchedule.MINUTES)

    PeriodicTask.objects.get_or_create(
        name=TASK_PERFORMANCE_DETECTION_TASK_NAME,
        defaults={
            "interval": schedule,
            "task": "system.tasks.detect_task_performance",
        }
    )


class SystemConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'system'
    label = 'system'
    verbose_name = _('System')

    def ready(self):
        # the attempt collector of #1330: the celery seams connect on the
        # import, like the incident publishers of #1320; the receivers read
        # the settings at every signal, so a process which is not a worker
        # (or a deployment which turned the telemetry off) stays inert
        import system.capacity_telemetry  # noqa
        # the opt-in root-cause profiler of #1389 attaches the same way and
        # stays equally inert unless its mode is enabled for a task allowlist
        import system.task_profiling  # noqa
        post_migrate.connect(
            create_slow_request_dump_cleanup_task,
            sender=self
        )
        post_migrate.connect(
            create_task_attempt_bounding_task,
            sender=self
        )
        post_migrate.connect(
            create_capacity_snapshot_refresh_task,
            sender=self
        )
        post_migrate.connect(
            create_task_performance_detection_task,
            sender=self
        )
        post_migrate.connect(
            create_task_performance_export_task,
            sender=self
        )
