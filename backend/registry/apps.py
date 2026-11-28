
import logging

from django.apps import AppConfig
from django.conf import settings
from django.db.models.signals import post_migrate
from django.utils.translation import gettext_lazy as _

#: the name the refresh of the alert rows has in the schedule of beat; the
#: tests look the row up by it
SERVICE_ALERT_REFRESH_TASK_NAME = "refresh the rows of the service alerts"

#: the cadence a deployment which says nothing gets, in seconds. Read through
#: ``settings.SERVICE_ALERT_REFRESH_SECONDS`` at the moment the row is
#: created, so a deployment moves it with ``MRMAP_SERVICE_ALERT_REFRESH_SECONDS``
#: like every other tunable of this app (#1827).
#:
#: On a rig of the size the documentation treats as normal - tens of thousands
#: of services, ~76k alert rows - one rewrite needs 20.4-27.1 s, so this
#: shipped value was a cadence the deployment could never meet and every
#: second fire was thrown away by the singleton lock. A fresh row therefore
#: additionally adapts to what the task measured on this deployment (see
#: ``create_service_alert_refresh_task``).
SERVICE_ALERT_REFRESH_SECONDS = 20

#: the name the watchdog of the harvesting imports has in the schedule of beat;
#: the tests look the row up by it
IMPORT_WATCH_TASK_NAME = "watch for harvesting imports which do not drain"

#: the name the sweep of the stored probe response artifacts has in the
#: schedule of beat; the tests look the row up by it
PROBE_RESPONSE_ARTIFACT_CLEANUP_TASK_NAME = (
    "delete expired monitoring probe response artifacts")

#: the name the cleanup of the stored records of ended harvests has in the
#: schedule of beat; the tests look the row up by it
HARVEST_TEMP_FILE_CLEANUP_TASK_NAME = (
    "delete stored metadata files of ended harvesting jobs")

#: the name the sweep of stale unfinished service-update jobs has in the
#: schedule of beat; the tests look the row up by it
STALE_UPDATE_JOB_SWEEP_TASK_NAME = (
    "sweep stale unfinished service-update jobs")


def create_choice_model_entries(sender, **kwargs):
    """Automatisch alle ChoiceModel-Subklassen erkennen und nur fehlende CHOICES eintragen."""
    from django.apps import apps
    from registry.models import ChoiceModel  # Baseclass

    logger = logging.getLogger(__name__)

    # Alle Modelle der App "registry" holen
    all_models = apps.get_app_config('registry').get_models()

    for model in all_models:
        if issubclass(model, ChoiceModel) and model is not ChoiceModel:
            choices = getattr(model, "CHOICES", [])
            if not choices:
                continue

            # Existierende Werte abrufen
            existing_values = set(
                model.objects.values_list('value', flat=True))

            # Nur die Werte eintragen, die noch fehlen
            missing_values = [value for value,
                              _ in choices if value not in existing_values]

            if missing_values:
                objs = [model(value=value) for value in missing_values]
                model.objects.bulk_create(objs)
                logger.info(
                    f"Inserted {len(objs)} new entries for {model.__name__}")
            else:
                logger.info(f"No new entries needed for {model.__name__}")


def create_file_system_import_task(sender, **kwargs):
    # this will create the periodic task as database object which is
    # required by celery beat to watch for new ISO metadata files to import
    from django_celery_beat.models import CrontabSchedule, PeriodicTask

    # Asked by its whole shape and not by the minutes alone: a deployment
    # which scheduled another task over the same minute string would
    # otherwise make this very lookup answer two rows and the migrate die on
    # MultipleObjectsReturned (#1273, the same fix #1208 gave the notify
    # sweep)
    schedule, _ = CrontabSchedule.objects.get_or_create(
        minute="0,5,10,15,20,25,30,35,40,45,50,55",
        hour="*", day_of_week="*",
        day_of_month="*", month_of_year="*")

    PeriodicTask.objects.get_or_create(
        crontab=schedule,
        name="check for new metadata to import",
        task="registry.tasks.harvest.check_for_files_to_import"
    )


def create_service_alert_refresh_task(sender, **kwargs):
    """Creates the periodic task which keeps the rows of the alerts current.

    The api of the attention answers stored rows instead of re-evaluating the
    whole derivation of the alerts per request (#1030); the rows are current
    because this task rewrites them on the interval of the schedule which the
    header poll used to rely on. Keyed by its name: a deployment which
    re-scheduled the row over the api keeps what it chose.

    Two things keep that cadence reachable at this size (#1827), and both
    apply to a FRESH row only - an existing row stays the operator's:

    *   the interval comes from ``SERVICE_ALERT_REFRESH_SECONDS``, which
        ``MRMAP_SERVICE_ALERT_REFRESH_SECONDS`` sets. It used to be the
        hardcoded 20 s of ``SERVICE_ALERT_REFRESH_SECONDS`` alone, a cadence
        which a deployment of ~35k services and ~76k alert rows cannot meet:
        one rewrite measured 20.4-27.1 s there, so every second fire met the
        singleton lock and the rows were current every ~40 s while the
        deployment believed its own setting.
    *   the row additionally adapts to what the task already measured on THIS
        deployment: with samples of the refresh in the attempt table of
        #1330, the interval is raised to their p95 times
        ``SERVICE_ALERT_REFRESH_HEADROOM``, bounded by
        ``SERVICE_ALERT_REFRESH_MAX_INTERVAL_SECONDS``. Raised, never
        shortened - a deployment which asked for a slower refresh keeps it -
        and switchable off with ``MRMAP_SERVICE_ALERT_REFRESH_ADAPTIVE=off``.
        A migrate on a deployment which never ran the task (no samples yet)
        is unaffected, so a fresh install still gets the shipped cadence.

    The measurement which adapts the row is read through the reachability read
    of #1827, so the interval, the capacity snapshot panel and the #1390
    incident all rest on the same measured p95.
    """
    from django_celery_beat.models import IntervalSchedule, PeriodicTask

    logger = logging.getLogger(__name__)
    interval = max(1, int(getattr(
        settings, "SERVICE_ALERT_REFRESH_SECONDS",
        SERVICE_ALERT_REFRESH_SECONDS)))
    interval = _reachable_refresh_interval(interval)

    schedule, _ = IntervalSchedule.objects.get_or_create(
        every=interval,
        period=IntervalSchedule.SECONDS)

    row, created = PeriodicTask.objects.get_or_create(
        name=SERVICE_ALERT_REFRESH_TASK_NAME,
        defaults={
            "interval": schedule,
            "task": "registry.tasks.alerts.refresh_service_alerts",
        }
    )
    if created and interval != max(1, int(getattr(
            settings, "SERVICE_ALERT_REFRESH_SECONDS",
            SERVICE_ALERT_REFRESH_SECONDS))):
        # only ever reachable through the adaptive step, and worth a line:
        # the deployment's rows are current at a cadence its own setting does
        # not name, and an operator must not have to discover that in a log
        logger.info(
            "Service alerts (#1827): the refresh of the alert rows fires "
            "every %s s instead of the configured %s s, because a measured "
            "run of the refresh needs that long on this deployment. Set "
            "MRMAP_SERVICE_ALERT_REFRESH_SECONDS (or the schedule row) to "
            "choose otherwise.", interval, getattr(
                settings, "SERVICE_ALERT_REFRESH_SECONDS",
                SERVICE_ALERT_REFRESH_SECONDS))
    return row


def _reachable_refresh_interval(configured):
    """The refresh interval which the measured duration of the task allows.

    Returns ``configured`` unchanged when the adaptive step is switched off,
    when nothing has been measured yet, or when the measurement is not past
    the configured cadence - which is the ordinary case of a small deployment
    and the reason a shipped 20 s stays shipped there. Never returns a shorter
    interval than the configured one: this is a floor under the cadence, not a
    scheduler.
    """
    if not getattr(settings, "SERVICE_ALERT_REFRESH_ADAPTIVE", True):
        return configured
    logger = logging.getLogger(__name__)
    try:
        from system.capacity_measures import measured_p95_of_periodic_task
    except ImportError:  # pragma: no cover - system is a hard dependency
        return configured
    try:
        measured = measured_p95_of_periodic_task(
            SERVICE_ALERT_REFRESH_TASK_NAME,
            "registry.tasks.alerts.refresh_service_alerts")
    except Exception as error:
        # a migrate must never fail because the attempt table could not be
        # read; the shipped cadence is the answer and the detector reports
        # the same condition later on
        logger.info("Service alerts (#1827): the refresh interval could not "
                    "be adapted from the measured duration: %s", error)
        return configured
    if measured is None:
        return configured
    headroom = float(getattr(settings, "SERVICE_ALERT_REFRESH_HEADROOM", 1.5))
    bound = int(getattr(
        settings, "SERVICE_ALERT_REFRESH_MAX_INTERVAL_SECONDS", 300))
    wanted = int(-(-measured * headroom // 1))          # round up
    return max(configured, min(wanted, max(configured, bound)))


def create_import_watch_task(sender, **kwargs):
    """Creates the periodic task which bounds the wait of a stranded import.

    The recovery of the harvests asks its question when a worker starts (#891,
    #972), so a deployment which does not restart its containers never looks again
    at a harvest whose import stopped draining: the wait of the import chord ends
    inside celery's builtin unlock, which drops the chord's callback without
    leaving a trace mrmap could read (#1038). Beat reads its schedule out of the
    database, so the watchdog needs a row of ``PeriodicTask`` like the import of
    the metadata files does. Keyed by its name and not by its schedule: a
    deployment which re-scheduled the row over the api keeps what it chose.
    """
    from django_celery_beat.models import IntervalSchedule, PeriodicTask

    interval = max(1, int(getattr(
        settings, "HARVEST_IMPORT_WATCH_INTERVAL_MINUTES", 5)))
    # `every` counts in units of `period`, so the row fires on the very
    # interval the watchdog itself measures a standstill with
    schedule, _ = IntervalSchedule.objects.get_or_create(
        every=interval, period=IntervalSchedule.MINUTES)

    PeriodicTask.objects.get_or_create(
        name=IMPORT_WATCH_TASK_NAME,
        defaults={
            "interval": schedule,
            "task": "registry.tasks.harvest.watch_import_backlogs",
        }
    )


def create_probe_response_artifact_cleanup_task(sender, **kwargs):
    """Creates the periodic task which takes the stored probe responses back.

    The monitoring keeps the body of every stored probe response as an
    artifact of the execution so that an inspector can look at the run and not
    at whatever the service answers today (#682). Nothing but this task takes
    those bodies back, so without the row they would grow with every run of
    every probe. Beat reads its schedule out of the database, so the sweep
    needs a row of ``PeriodicTask`` like the import of the metadata files
    does. Keyed by its name: a deployment which re-scheduled the row over the
    api keeps what it chose.
    """
    from django_celery_beat.models import CrontabSchedule, PeriodicTask

    # at twenty past the hour: a housekeeping sweep, out of the way of the
    # five minute metadata import and the hourly dump sweep at five past.
    # Asked by its whole shape and not by the minute alone: the staggered
    # per-service schedules (system/fields.py) legitimately hold rows at
    # twenty past with any hour, and the bare minute lookup answered them
    # all -- the migrate died on MultipleObjectsReturned (#1273)
    schedule, _ = CrontabSchedule.objects.get_or_create(
        minute="20", hour="*", day_of_week="*",
        day_of_month="*", month_of_year="*")

    PeriodicTask.objects.get_or_create(
        name=PROBE_RESPONSE_ARTIFACT_CLEANUP_TASK_NAME,
        defaults={
            "crontab": schedule,
            "task": ("registry.tasks.monitoring."
                     "delete_expired_probe_response_artifacts"),
        }
    )


def create_harvest_temp_file_cleanup_task(sender, **kwargs):
    """Creates the periodic task which takes the stored records of ended
    harvests back.

    A run stores every downloaded record as a row and a file; the import
    deletes what it consumed and the terminal transitions schedule the cleanup
    of what remains, but a publish the broker swallowed or a cleanup whose
    worker died would otherwise leave the backlog of an ended job forever -
    nothing but this sweep takes the files which no row references anymore
    (#1237). Beat reads its schedule out of the database, so the sweep needs a
    row of ``PeriodicTask`` like the other housekeeping does. Keyed by its
    name: a deployment which re-scheduled the row over the api keeps what it
    chose.
    """
    from django_celery_beat.models import CrontabSchedule, PeriodicTask

    # at twenty to the hour: a housekeeping sweep, out of the way of the
    # five minute metadata import, the hourly dump sweep at five past and the
    # hourly probe artifact sweep at twenty past. Asked by its whole shape
    # and not by the minute alone, for the reason #1273 states at the probe
    # artifact sweep
    schedule, _ = CrontabSchedule.objects.get_or_create(
        minute="40", hour="*", day_of_week="*",
        day_of_month="*", month_of_year="*")

    PeriodicTask.objects.get_or_create(
        name=HARVEST_TEMP_FILE_CLEANUP_TASK_NAME,
        defaults={
            "crontab": schedule,
            "task": "registry.tasks.harvest.sweep_ended_harvest_temp_files",
        }
    )


def create_stale_update_job_sweep_task(sender, **kwargs):
    """Creates the periodic task which fails stale unfinished update jobs.

    The guards of #1453 redeliver a lost message, but a delivery which is gone
    for good leaves its update job unfinished, and nothing but this sweep takes
    such a run back: the constraint of one unfinished job per service would
    block the service's schedule forever (#1460). Beat reads its schedule out of
    the database, so the sweep needs a row of ``PeriodicTask`` like the other
    housekeeping does. Keyed by its name: a deployment which re-scheduled the
    row over the api keeps what it chose.
    """
    from django_celery_beat.models import CrontabSchedule, PeriodicTask

    # at fifty past the hour: a housekeeping sweep, out of the way of the five
    # minute metadata import, the hourly dump sweep at five past, the hourly
    # probe artifact sweep at twenty past and the hourly harvest cleanup at
    # twenty to. Asked by its whole shape and not by the minute alone, for the
    # reason #1273 states at the probe artifact sweep
    schedule, _ = CrontabSchedule.objects.get_or_create(
        minute="50", hour="*", day_of_week="*",
        day_of_month="*", month_of_year="*")

    PeriodicTask.objects.get_or_create(
        name=STALE_UPDATE_JOB_SWEEP_TASK_NAME,
        defaults={
            "crontab": schedule,
            "task": "registry.tasks.update.sweep_stale_update_jobs",
        }
    )


def find_orphan_metadata_objects(sender, **kwargs):
    import logging
    logger = logging.getLogger(__name__)
    from registry.models.metadata import DatasetMetadataRecord
    orphans = DatasetMetadataRecord.objects.filter(
        resource_relation__isnull=True)
    # FUTURE: move this to a manager as check function
    logger.info(f"metadata orphans: {orphans.count()}")


class RegistryConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'registry'
    label = 'registry'
    verbose_name = _('Registry')

    def ready(self):
        # the keyword maintenance of the records: the trigger definitions of
        # registry/triggers.py are registered on their models, which needs the
        # app registry populated; from there the migrations of pgtrigger carry
        # them into the database (#1009)
        import registry.triggers  # noqa: F401

        # Implicitly connect signal handlers decorated with @receiver.
        post_migrate.connect(
            create_choice_model_entries,
            sender=self
        )

        post_migrate.connect(
            create_file_system_import_task,
            sender=self
        )
        post_migrate.connect(
            create_service_alert_refresh_task,
            sender=self
        )
        post_migrate.connect(
            create_import_watch_task,
            sender=self
        )
        post_migrate.connect(
            create_probe_response_artifact_cleanup_task,
            sender=self
        )
        post_migrate.connect(
            create_harvest_temp_file_cleanup_task,
            sender=self
        )
        post_migrate.connect(
            create_stale_update_job_sweep_task,
            sender=self
        )
        post_migrate.connect(
            find_orphan_metadata_objects,
            sender=self
        )
