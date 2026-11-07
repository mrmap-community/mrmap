
import logging

from django.apps import AppConfig
from django.conf import settings
from django.db.models.signals import post_migrate
from django.utils.translation import gettext_lazy as _

#: the name the watchdog of the harvesting imports has in the schedule of beat;
#: the tests look the row up by it
IMPORT_WATCH_TASK_NAME = "watch for harvesting imports which do not drain"


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

    schedule, _ = CrontabSchedule.objects.get_or_create(
        minute="0,5,10,15,20,25,30,35,40,45,50,55",
    )

    PeriodicTask.objects.get_or_create(
        crontab=schedule,
        name="check for new metadata to import",
        task="registry.tasks.harvest.check_for_files_to_import"
    )


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


def find_orphan_metadata_objects(sender, **kwargs):
    import logging
    logger = logging.getLogger(__name__)
    from registry.models.metadata import DatasetMetadataRecord
    orphans = DatasetMetadataRecord.objects.filter(
        resource_relation__isnull=True)
    # TODO: move this to a manager as check function
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
            create_import_watch_task,
            sender=self
        )
        post_migrate.connect(
            find_orphan_metadata_objects,
            sender=self
        )
