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
from django.core.exceptions import ObjectDoesNotExist, MultipleObjectsReturned, ValidationError
from django_celery_beat.models import PeriodicTask, IntervalSchedule

from monitoring.enums import MonitoringSettingEnum
from monitoring.models import MonitoringSetting, MonitoringRun
from monitoring.monitoring import Monitoring as Monitor


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
        except Exception as e:
            pass
    end_time = datetime.datetime.now(pytz.utc)
    duration = end_time - monitoring_run.start
    monitoring_run.end = end_time
    monitoring_run.duration = duration
    monitoring_run.save()
    if setting.type.value == MonitoringSettingEnum.SPORADICALLY.value:
        setting.delete()
