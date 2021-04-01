"""
Author: Jan Suleiman
Organization: terrestris GmbH & Co. KG, Bonn, Germany
Contact: suleiman@terrestris.de
Created on: 26.02.2020

"""
from celery import shared_task
from celery.signals import beat_init
from django.core.exceptions import ObjectDoesNotExist, MultipleObjectsReturned
from django.db import transaction
from django.utils import timezone
from monitoring.models import MonitoringSetting, MonitoringRun
from monitoring.monitoring import Monitoring as Monitor
from monitoring.settings import monitoring_logger
from service.models import Metadata
from django.utils.translation import gettext_lazy as _


@beat_init.connect
def init_periodic_tasks(sender, **kwargs):
    """ Load MonitoringSettings and create/update PeriodicTask records

    Args:
        sender:
        kwargs:
    Returns:

    """
    monitoring_settings = MonitoringSetting.objects.all()
    for setting in monitoring_settings:
        setting.update_periodic_tasks()


@shared_task(name='run_service_monitoring')
@transaction.atomic
def run_monitoring(setting_id, *args, **kwargs):
    monitoring_run = MonitoringRun.objects.create()

    try:
        setting = MonitoringSetting.objects.get(pk=setting_id)
    except (ObjectDoesNotExist, MultipleObjectsReturned):
        print(f'Could not retrieve setting with id {setting_id}')
        return
    metadatas = setting.metadatas.all()
    for metadata in metadatas:
        try:
            monitor = Monitor(metadata=metadata, monitoring_run=monitoring_run, )
            monitor.run_checks()
            monitoring_logger.debug(f'Health checks completed for {metadata}')
        except Exception as e:
            monitoring_logger.exception(e, exc_info=True, stack_info=True)

    end_time = timezone.now()
    duration = end_time - monitoring_run.start
    monitoring_run.end = end_time
    monitoring_run.duration = duration
    monitoring_run.save()


@shared_task(name='run_manual_service_monitoring')
def run_manual_service_monitoring(monitoring_run, *args, **kwargs):
    print(monitoring_run)
    monitoring_run = MonitoringRun.objects.get(pk=monitoring_run)
    monitoring_run.start = timezone.now()
    print(monitoring_run.metadatas.all())
    for metadata in monitoring_run.metadatas.all():
        try:
            monitor = Monitor(metadata=metadata, monitoring_run=monitoring_run, )
            monitor.run_checks()
            monitoring_logger.debug(f'Health checks completed for {metadata}')
        except Exception as e:
            monitoring_logger.error(msg=_(f'Something went wrong while monitoring {metadata}'))
            monitoring_logger.exception(e, exc_info=True, stack_info=True, )

    end_time = timezone.now()
    duration = end_time - monitoring_run.start
    monitoring_run.end = end_time
    monitoring_run.duration = duration
    monitoring_run.save()
