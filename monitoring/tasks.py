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
from django.core.exceptions import ObjectDoesNotExist
from django_celery_beat.models import PeriodicTask, IntervalSchedule

from monitoring.models import MonitoringSetting, MonitoringRun
from monitoring.monitoring import Monitoring as Monitor
from service.models import Metadata


@beat_init.connect
def setup_periodic_tasks(sender, **kwargs):
    # NOTE: We expect that the first entry is the default setting, as it was created on app setup
    monitoring_setting = MonitoringSetting.objects.first()
    interval = monitoring_setting.interval.total_seconds()
    schedule, created = IntervalSchedule.objects.get_or_create(every=interval, period=IntervalSchedule.SECONDS)
    periodic_task_name = 'run monitoring'
    # check if task with name already exists, if not, create it
    try:
        PeriodicTask.objects.get(name=periodic_task_name)
    except ObjectDoesNotExist:
        PeriodicTask.objects.create(
            interval=schedule, name='run monitoring', task='run_service_monitoring'
        )


@shared_task(name='run_service_monitoring')
def run_monitoring():
    monitoring_run = MonitoringRun.objects.create()
    metadatas = Metadata.objects.all()
    for metadata in metadatas:
        try:
            monitor = Monitor(metadata, monitoring_run)
            monitor.run_checks()
        except Exception as e:
            # print(f'Monitoring of metadata with id {metadata.pk} failed. {e}')
            pass
    end_time = datetime.datetime.now(pytz.utc)
    duration = end_time - monitoring_run.start
    monitoring_run.end = end_time
    monitoring_run.duration = duration
    monitoring_run.save()
