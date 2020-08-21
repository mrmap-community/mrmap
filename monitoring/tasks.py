"""
Author: Jan Suleiman
Organization: terrestris GmbH & Co. KG, Bonn, Germany
Contact: suleiman@terrestris.de
Created on: 26.02.2020

"""
import pytz
import datetime

from celery import shared_task
from celery.signals import beat_init
from django.core.exceptions import ObjectDoesNotExist, MultipleObjectsReturned
from django.db import transaction

from monitoring.models import MonitoringSetting, MonitoringRun
from monitoring.monitoring import Monitoring as Monitor
from monitoring.settings import monitoring_logger
from service.models import Metadata


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
            monitor = Monitor(metadata, monitoring_run, setting)
            monitor.run_checks()
            monitoring_logger.debug(f'Health checks completed for {metadata}')
        except Exception as e:
            monitoring_logger.exception(e, exc_info=True, stack_info=True)

    end_time = datetime.datetime.now(pytz.utc)
    duration = end_time - monitoring_run.start
    monitoring_run.end = end_time
    monitoring_run.duration = duration
    monitoring_run.save()


@shared_task(name='run_manual_service_monitoring')
@transaction.atomic
def run_manual_monitoring(metadatas, *args, **kwargs):
    monitoring_run = MonitoringRun.objects.create()

    for metadata_id in metadatas:
        try:
            metadata = Metadata.objects.get(id=metadata_id)
            monitor = Monitor(metadata, monitoring_run)
            monitor.run_checks()
            monitoring_logger.debug(f'Health checks completed for {metadata}')
        except Exception as e:
            monitoring_logger.exception(e, exc_info=True, stack_info=True, )

    end_time = datetime.datetime.now(pytz.utc)
    duration = end_time - monitoring_run.start
    monitoring_run.end = end_time
    monitoring_run.duration = duration
    monitoring_run.save()
