
import logging

from django.apps import AppConfig
from django.db.models.signals import post_migrate
from django.utils.translation import gettext_lazy as _


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


def find_orphan_metadata_objects(sender, **kwargs):
    import logging
    logger = logging.getLogger(__name__)
    from registry.models.metadata import DatasetMetadataRecord
    orphans = DatasetMetadataRecord.objects.filter(
        resource_relation__isnull=True)
    # TODO: move this to a manager as check function
    logger.info("metadata orphans:", orphans.count())


class RegistryConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'registry'
    label = 'registry'
    verbose_name = _('Registry')

    def ready(self):
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
            find_orphan_metadata_objects,
            sender=self
        )
