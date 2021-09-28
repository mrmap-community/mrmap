"""
Author: Jan Suleiman
Organization: terrestris GmbH & Co. KG
Contact: suleiman@terrestris.de
Created on: 27.10.20

"""
import json
import sys

from celery import shared_task
from celery.utils.log import get_task_logger
from django.utils import timezone

from jobs.enums import TaskStatusEnum
from jobs.tasks import CurrentTask, NewJob
from registry.helper.plugins.etf import QualityEtf, EtfClient
from registry.helper.plugins.internal import QualityInternal
from registry.enums.conformity import ConformityTypeEnum, ReportType
from registry.models import ConformityCheckRun, ConformityCheckConfigurationExternal

logger = get_task_logger(__name__)


@shared_task(name='async_run_conformity_check',
             base=NewJob,
             bind=True)
def run_conformity_check(self, run_id: int, **kwargs):
    run = ConformityCheckRun.objects.get(id=run_id)
    if run is None:
        raise Exception(f'No conformity check run with id {run_id}')
    config = run.config
    if config.conformity_type == ConformityTypeEnum.INTERNAL.value:
        task = run_conformity_check_internal.s(run_id, **kwargs)
    elif config.conformity_type == ConformityTypeEnum.ETF.value:
        task = run_conformity_check_etf.s(run_id, **kwargs)
    else:
        raise Exception(
            f"Could not check conformity. Invalid conformity type: "
            f"{config.conformity_type}.")
    task.apply_async()
    return self.job.pk


@shared_task(name='async_run_conformity_check_etf',
             base=CurrentTask,
             bind=True)
def run_conformity_check_etf(self, run_id: int, **kwargs):
    if self.task:
        self.task.status = TaskStatusEnum.STARTED.value
        self.task.phase = "performing ETF-based conformity check..."
        self.task.started_at = timezone.now()
        self.task.save()

    try:
        run = ConformityCheckRun.objects.get(id=run_id)
        if run is None:
            raise Exception(f'No conformity check run with id {run_id}')
        config_ext = ConformityCheckConfigurationExternal.objects.get(
            pk=run.config.id)
        client = EtfClient(config_ext.external_url)
        checker = QualityEtf(run, config_ext, client)
        run = checker.run()
    except:
        logger.exception('ETF conformity check failure', exc_info=sys.exc_info()[0])
        run.passed = False
        run.report = json.dumps({
            "Unexpected error": str(sys.exc_info())
        })
        run.report_type = ReportType.JSON.value
        run.save()

        e = sys.exc_info()[0]
        self.task.progress = 100
        self.task.status = TaskStatusEnum.FAILURE
        self.task.done_at = timezone.now()
        self.task.phase = f'Failure. <a href="{ConformityCheckRun.get_table_url()}?id__in={run_id}">Conformity check results</a>'
        self.task.save()
        return run.pk

    if self.task:
        self.task.progress = 100
        self.task.status = TaskStatusEnum.SUCCESS.value
        self.task.done_at = timezone.now()
        self.task.phase = f'Done. <a href="{ConformityCheckRun.get_table_url()}?id__in={run_id}">Conformity check results</a>'
        self.task.save()
    return run.pk


@shared_task(name='async_run_conformity_check_internal',
             base=CurrentTask,
             bind=True)
def run_conformity_check_internal(self, run_id: int, **kwargs):
    if self.task:
        self.task.status = TaskStatusEnum.STARTED.value
        self.task.phase = "performing internal conformity check..."
        self.task.started_at = timezone.now()
        self.task.save()

    try:
        run = ConformityCheckRun.objects.get(id=run_id)
        if run is None:
            raise Exception(f'No conformity check run with id {run_id}')
        checker = QualityInternal(run)
        run = checker.run()
    except:
        logger.exception('Internal conformity check failure', exc_info=sys.exc_info()[0])
        run.passed = False
        run.report = json.dumps({
            "Unexpected error": str(sys.exc_info())
        })
        run.report_type = ReportType.JSON.value
        run.save()

        e = sys.exc_info()[0]
        self.task.progress = 100
        self.task.status = TaskStatusEnum.FAILURE
        self.task.done_at = timezone.now()
        self.task.phase = f'Failure. <a href="{ConformityCheckRun.get_table_url()}?id__in={run_id}">Conformity check results</a>'
        self.task.save()
        return run.pk

    if self.task:
        self.task.progress = 100
        self.task.status = TaskStatusEnum.SUCCESS.value
        self.task.done_at = timezone.now()
        self.task.phase = f'Done. <a href="{ConformityCheckRun.get_table_url()}?id__in={run_id}">Conformity check results</a>'
        self.task.save()
    return run.pk