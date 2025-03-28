from django.apps import AppConfig
from django.db.models.signals import post_migrate
from django.utils.translation import gettext_lazy as _
from registry.enums.service import (SecureableWFSOperationEnum,
                                    SecureableWMSOperationEnum)


def create_wms_operations(sender, **kwargs):
    from registry.models.security import WebMapServiceOperation
    for key, _ in SecureableWMSOperationEnum.choices:
        WebMapServiceOperation.objects.get_or_create(operation=key)


def create_wfs_operations(sender, **kwargs):
    from registry.models.security import WebFeatureServiceOperation
    for key, _ in SecureableWFSOperationEnum.choices:
        WebFeatureServiceOperation.objects.get_or_create(operation=key)


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
    from registry.models.metadata import DatasetMetadataRecord
    orphans = DatasetMetadataRecord.objects.filter(
        resource_relation__isnull=True)
    # TODO: move this to a manager as check function
    # print info object instead
    print("metadata orphans:", orphans.count())


class RegistryConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'registry'
    label = 'registry'
    verbose_name = _('Registry')

    def ready(self):
        # Implicitly connect signal handlers decorated with @receiver.
        from . import signals  # noqa
        post_migrate.connect(create_wms_operations, sender=self)
        post_migrate.connect(create_wfs_operations, sender=self)

        post_migrate.connect(create_file_system_import_task, sender=self)
        post_migrate.connect(find_orphan_metadata_objects, sender=self)
