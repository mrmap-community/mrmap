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
from registry.enums.conformity import ConformityTypeEnum, ReportType
from registry.helper.plugins.etf import EtfClient, QualityEtf
from registry.helper.plugins.internal import QualityInternal
from registry.models import (ConformityCheckConfigurationExternal,
                             ConformityCheckRun)

logger = get_task_logger(__name__)


@shared_task(name='async_run_conformity_check')
def run_conformity_check(run_id: int, **kwargs):
    """Dispatch the conformity check of one run to its kind.

    The read joins the run's ``config`` because the branch below decides on
    ``conformity_type`` (#1394; the plan rule of #1397 names the read each
    relation is in). The status/phase writes of the retired DB task-result
    store are gone: django-celery-results was removed with #1178/#1180 and
    the result backend is Redis, so those ``self.task``/``self.job`` reads
    never answered rows anymore - the run row itself is the record of the
    check and answers the terminal ``passed``/``report`` state.
    """
    run = ConformityCheckRun.objects.for_check_execution().get(id=run_id)
    config = run.config
    if config.conformity_type == ConformityTypeEnum.INTERNAL.value:
        task = run_conformity_check_internal.s(run_id, **kwargs)
    elif config.conformity_type == ConformityTypeEnum.ETF.value:
        task = run_conformity_check_etf.s(run_id, **kwargs)
    else:
        raise ValueError(
            f"Could not check conformity. Invalid conformity type: "
            f"{config.conformity_type}.")
    task.apply_async()
    return run.pk


@shared_task(name='async_run_conformity_check_etf')
def run_conformity_check_etf(run_id: int, **kwargs):
    """Run one ETF-based conformity check and decide the run row.

    The run is read by pk and its external configuration by the foreign key
    the run already carries - both bounded indexed reads which need no
    join: the task only names the concrete configuration row, and the
    checker reads the resource, not the base configuration (#1394). As in
    the internal check, a failure leaves the run decided (``passed=False``
    with the error report) rather than an open row; the terminal write is
    the one status the run ever gets - the retired result-store writes of
    #1178/#1180 are gone (#1394).
    """
    run = ConformityCheckRun.objects.get(id=run_id)
    try:
        config_ext = ConformityCheckConfigurationExternal.objects.get(
            pk=run.config_id)
        client = EtfClient(config_ext.external_url)
        checker = QualityEtf(run, config_ext, client)
        run = checker.run()
    except Exception:
        logger.exception('ETF conformity check failure',
                         exc_info=sys.exc_info()[0])
        run.passed = False
        run.report = json.dumps({
            "Unexpected error": str(sys.exc_info())
        })
        run.report_type = ReportType.JSON.value
        run.save()
        return run.pk
    return run.pk


@shared_task(name='async_run_conformity_check_internal')
def run_conformity_check_internal(run_id: int, **kwargs):
    """Run one internal conformity check and decide the run row.

    The read joins ``config`` because ``QualityInternal`` decides the check
    from it at construction (#1394); the retention of the terminal failure
    write is as in the ETF worker.
    """
    run = ConformityCheckRun.objects.for_check_execution().get(id=run_id)
    try:
        checker = QualityInternal(run)
        run = checker.run()
    except Exception:
        logger.exception('Internal conformity check failure',
                         exc_info=sys.exc_info()[0])
        run.passed = False
        run.report = json.dumps({
            "Unexpected error": str(sys.exc_info())
        })
        run.report_type = ReportType.JSON.value
        run.save()
        return run.pk
    return run.pk
